"""Thin urllib client for the OpenAI Images API (generations + edits).

Only two calls are made, both documented at
https://developers.openai.com/api/reference/resources/images — no SDK, no
agent loop. Responses come back base64 for GPT image models; we decode and
return raw bytes plus the usage block so the caller can log cost.

Retries: transient failures (429, 5xx, timeouts, connection resets) are
retried with exponential backoff up to ``max_retries``. 4xx other than 429
raise immediately with the server's error message.
"""
from __future__ import annotations

import base64
import io
import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

API_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
USER_AGENT = "portrender/0.1 (+https://github.com/jimmershere)"


class ImagesError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class ImageResult:
    images: List[bytes]
    revised_prompts: List[Optional[str]]
    usage: Dict[str, object] = field(default_factory=dict)
    raw_meta: Dict[str, object] = field(default_factory=dict)


def _headers(api_key: str, content_type: str) -> Dict[str, str]:
    h = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": content_type,
        "User-Agent": USER_AGENT,
    }
    org = os.environ.get("OPENAI_ORG_ID")
    if org:
        h["OpenAI-Organization"] = org
    return h


def _request(url: str, data: bytes, headers: Dict[str, str], timeout: float,
             max_retries: int, log=None) -> Dict[str, object]:
    attempt = 0
    while True:
        attempt += 1
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
            return json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            msg = body
            try:
                msg = json.loads(body).get("error", {}).get("message", body)
            except Exception:
                pass
            retryable = e.code == 429 or 500 <= e.code < 600
            if not retryable or attempt > max_retries:
                raise ImagesError(f"HTTP {e.code}: {msg}", e.code, body) from None
            err_text = f"HTTP {e.code}: {msg[:200]}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt > max_retries:
                raise ImagesError(f"network error: {e}") from None
            err_text = f"network error: {e}"
        sleep = min(30.0, (2 ** attempt) + random.random())
        if log:
            log(f"[openai] attempt {attempt} failed ({err_text}); retrying in {sleep:.0f}s")
        time.sleep(sleep)


def _decode(data: Dict[str, object]) -> ImageResult:
    items = data.get("data") or []
    images: List[bytes] = []
    revised: List[Optional[str]] = []
    for it in items:
        b64 = it.get("b64_json") if isinstance(it, dict) else None
        if not b64:
            raise ImagesError("response item had no b64_json (set output to base64 / GPT image model)")
        images.append(base64.b64decode(b64))
        revised.append(it.get("revised_prompt") if isinstance(it, dict) else None)
    meta = {k: v for k, v in data.items() if k != "data"}
    return ImageResult(images=images, revised_prompts=revised,
                       usage=data.get("usage") or {}, raw_meta=meta)


def generate(prompt: str, *, api_key: str, model: str, n: int = 1, size: str = "1024x1024",
             quality: str = "medium", background: str = "auto", output_format: str = "png",
             moderation: Optional[str] = None, user: Optional[str] = None,
             timeout: float = 300.0, max_retries: int = 3, log=None) -> ImageResult:
    body: Dict[str, object] = {
        "model": model, "prompt": prompt, "n": int(n), "size": size,
        "quality": quality, "output_format": output_format,
    }
    if background and background != "auto":
        body["background"] = background
    if moderation:
        body["moderation"] = moderation
    if user:
        body["user"] = user
    data = _request(f"{API_BASE}/images/generations", json.dumps(body).encode("utf-8"),
                    _headers(api_key, "application/json"), timeout, max_retries, log)
    return _decode(data)


def _multipart(fields: Dict[str, str], files: Sequence[tuple]) -> tuple:
    """files: sequence of (field_name, filename, bytes, mime)."""
    boundary = "----portrender" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
    for name, filename, blob, mime in files:
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                  f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
        buf.write(blob)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode("utf-8"))
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def _mime_for(blob: bytes) -> str:
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if blob[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def edit(prompt: str, images: Sequence[bytes], *, api_key: str, model: str, n: int = 1,
         size: str = "auto", quality: str = "medium", background: str = "auto",
         output_format: str = "png", mask: Optional[bytes] = None,
         input_fidelity: Optional[str] = None, moderation: Optional[str] = None,
         user: Optional[str] = None, timeout: float = 300.0, max_retries: int = 3,
         log=None) -> ImageResult:
    """POST /images/edits as multipart. ``images[0]`` is the primary image; up to
    16 reference images are accepted by GPT image models (sent as ``image[]``)."""
    if not images:
        raise ValueError("edit() needs at least one source image")
    fields: Dict[str, str] = {
        "model": model, "prompt": prompt, "n": str(int(n)), "size": size,
        "quality": quality, "output_format": output_format,
    }
    if background and background != "auto":
        fields["background"] = background
    if input_fidelity:
        fields["input_fidelity"] = input_fidelity
    if moderation:
        fields["moderation"] = moderation
    if user:
        fields["user"] = user
    files = []
    for i, blob in enumerate(images[:16]):
        mime = _mime_for(blob)
        ext = mime.split("/")[-1].replace("jpeg", "jpg")
        files.append(("image[]", f"image{i}.{ext}", blob, mime))
    if mask:
        files.append(("mask", "mask.png", mask, "image/png"))
    data, ctype = _multipart(fields, files)
    resp = _request(f"{API_BASE}/images/edits", data, _headers(api_key, ctype),
                    timeout, max_retries, log)
    return _decode(resp)


def probe(api_key: str, timeout: float = 15.0) -> Dict[str, object]:
    """Auth-only check: list models, no generation spend."""
    req = urllib.request.Request(f"{API_BASE}/models?limit=1", headers=_headers(api_key, "application/json"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            json.loads(resp.read().decode("utf-8"))
        return {"ok": True}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": e.read().decode("utf-8", errors="replace")[:300]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
