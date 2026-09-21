"""Jobs: one directory per render under ``data/renders/<job_id>/``.

    <job_id>/
      render.json      manifest — status, prompt, params, images[], review state
      prompt.txt       the exact prompt sent
      01.png 02.png …  outputs
      thumbs/01.png    small previews (only if Pillow is around)
      job.log          progress log (also mirrored to data/jobs/<id>.log by the server)

The manifest is the source of truth; there is no database. Everything is
grep-able and hand-editable, per the fleet's "operator-readable artifacts" rule.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import config, openai_images, prompts
from .brands import Brand

MANIFEST = "render.json"
_lock = threading.Lock()

IMAGE_STATUSES = ("pending", "approved", "rejected")


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def slugify(text: str, n: int = 32) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:n].rstrip("-") or "render"


def new_id(label: str) -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{slugify(label)}"
    jid, i = base, 1
    while (config.RENDERS_DIR / jid).exists():
        i += 1
        jid = f"{base}-{i}"
    return jid


def job_dir(jid: str) -> Path:
    if not re.fullmatch(r"[\w\-]+", jid or ""):
        raise ValueError(f"bad job id: {jid!r}")
    return config.RENDERS_DIR / jid


def read(jid: str) -> Dict[str, Any]:
    p = job_dir(jid) / MANIFEST
    if not p.is_file():
        raise FileNotFoundError(f"no job {jid}")
    return json.loads(p.read_text(encoding="utf-8"))


def write(man: Dict[str, Any]) -> None:
    d = job_dir(man["id"])
    d.mkdir(parents=True, exist_ok=True)
    man["updated"] = _now()
    tmp = d / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, d / MANIFEST)


def log(jid: str, msg: str) -> None:
    line = f"{_now()} {msg}"
    try:
        with open(job_dir(jid) / "job.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    if not os.environ.get("PORTRENDER_QUIET"):
        print(line, file=sys.stderr, flush=True)


def list_jobs(status: Optional[str] = None, brand: Optional[str] = None, limit: int = 200,
              image_status: Optional[str] = None, starred: Optional[bool] = None,
              query: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not config.RENDERS_DIR.is_dir():
        return out
    for d in sorted(config.RENDERS_DIR.iterdir(), reverse=True):
        p = d / MANIFEST
        if not p.is_file():
            continue
        try:
            man = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if status and man.get("status") != status:
            continue
        if brand and man.get("brand") != brand:
            continue
        if image_status and not any(im.get("status") == image_status for im in man.get("images", [])):
            continue
        if starred is not None and not any(bool(im.get("starred")) == starred for im in man.get("images", [])):
            continue
        if query:
            hay = json.dumps(man, ensure_ascii=False).lower()
            if query.lower() not in hay:
                continue
        out.append(man)
        if len(out) >= limit:
            break
    return out


def summarize(man: Dict[str, Any]) -> Dict[str, Any]:
    imgs = man.get("images", [])
    return {
        "id": man["id"], "status": man.get("status"), "kind": man.get("kind"), "brand": man.get("brand"),
        "template": man.get("template"), "label": man.get("label"), "created": man.get("created"),
        "n": len(imgs), "approved": sum(1 for i in imgs if i.get("status") == "approved"),
        "rejected": sum(1 for i in imgs if i.get("status") == "rejected"),
        "starred": sum(1 for i in imgs if i.get("starred")),
        "model": man.get("model"), "size": man.get("size"), "quality": man.get("quality"),
        "cost_estimate": man.get("cost_estimate"), "parent": man.get("parent"),
        "error": man.get("error"), "images": imgs, "prompt": man.get("prompt"),
    }


# ---------------------------------------------------------------- creation --

def create(*, kind: str, prompt: str, label: str, brand: Optional[str], template: Optional[str],
           vars: Dict[str, str], model: str, n: int, size: str, quality: str, background: str,
           output_format: str = "png", parent: Optional[Dict[str, Any]] = None,
           sources: Optional[List[str]] = None, input_fidelity: Optional[str] = None,
           notes: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
    config.ensure_dirs()
    jid = new_id(label)
    man: Dict[str, Any] = {
        "id": jid, "created": _now(), "status": "queued", "kind": kind, "label": label,
        "brand": brand, "template": template, "vars": vars, "prompt": prompt,
        "model": model, "n": int(n), "size": size, "quality": quality, "background": background,
        "output_format": output_format, "input_fidelity": input_fidelity,
        "parent": parent, "sources": sources or [], "images": [], "usage": None,
        "cost_estimate": None, "error": None, "notes": notes, "tags": tags or [],
    }
    write(man)
    (job_dir(jid) / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    return man


def _thumb(src: Path, dst: Path, max_px: int = 384) -> bool:
    try:
        from PIL import Image  # type: ignore
    except Exception:  # noqa: BLE001
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im.thumbnail((max_px, max_px))
            im.save(dst)
        return True
    except Exception:  # noqa: BLE001
        return False


def _png_size(blob: bytes) -> Optional[List[int]]:
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
        return [int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big")]
    return None


def run(jid: str, *, api_key: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Execute a queued job synchronously. Safe to call from the CLI or a subprocess."""
    man = read(jid)
    if man.get("status") == "done":
        return man
    key = api_key or config.api_key()
    if not key and not dry_run:
        man["status"] = "error"
        man["error"] = "OPENAI_API_KEY not set (env or one of PORTRENDER_ENV_FILES)"
        write(man)
        log(jid, man["error"])
        return man
    man["status"] = "running"
    man["started"] = _now()
    write(man)
    d = job_dir(jid)
    ext = man.get("output_format", "png")
    t0 = time.time()
    try:
        if dry_run:
            log(jid, "dry-run: writing placeholder PNGs, no API call")
            blobs = [_placeholder_png(f"{man['label']} #{i + 1}") for i in range(man["n"])]
            revised = [None] * len(blobs)
            usage: Dict[str, Any] = {"dry_run": True}
        elif man["kind"] == "edit":
            srcs = [Path(s).read_bytes() for s in man.get("sources", [])]
            mask = None
            if man.get("mask"):
                mask = Path(man["mask"]).read_bytes()
            log(jid, f"edit via {man['model']} n={man['n']} size={man['size']} q={man['quality']} sources={len(srcs)}")
            res = openai_images.edit(
                man["prompt"], srcs, api_key=key, model=man["model"], n=man["n"], size=man["size"],
                quality=man["quality"], background=man["background"], output_format=ext, mask=mask,
                input_fidelity=man.get("input_fidelity"), log=lambda m: log(jid, m))
            blobs, revised, usage = res.images, res.revised_prompts, res.usage
        else:
            log(jid, f"generate via {man['model']} n={man['n']} size={man['size']} q={man['quality']} bg={man['background']}")
            res = openai_images.generate(
                man["prompt"], api_key=key, model=man["model"], n=man["n"], size=man["size"],
                quality=man["quality"], background=man["background"], output_format=ext,
                log=lambda m: log(jid, m))
            blobs, revised, usage = res.images, res.revised_prompts, res.usage
        images: List[Dict[str, Any]] = []
        for i, blob in enumerate(blobs, start=1):
            fname = f"{i:02d}.{ext}"
            (d / fname).write_bytes(blob)
            has_thumb = _thumb(d / fname, d / "thumbs" / f"{i:02d}.png")
            images.append({
                "file": fname, "thumb": f"thumbs/{i:02d}.png" if has_thumb else None,
                "size_px": _png_size(blob), "bytes": len(blob), "status": "pending",
                "starred": False, "note": "", "revised_prompt": revised[i - 1] if i - 1 < len(revised) else None,
            })
        man["images"] = images
        man["usage"] = usage
        per = config.price_for(man["model"], man["quality"])
        man["cost_estimate"] = round(per * len(images), 4) if per else None
        man["status"] = "done"
        man["elapsed_s"] = round(time.time() - t0, 1)
        log(jid, f"done: {len(images)} image(s) in {man['elapsed_s']}s")
    except Exception as e:  # noqa: BLE001
        man["status"] = "error"
        man["error"] = str(e)[:2000]
        man["elapsed_s"] = round(time.time() - t0, 1)
        log(jid, f"ERROR: {man['error']}")
    write(man)
    return man


def _placeholder_png(text: str, w: int = 512, h: int = 512) -> bytes:
    """Tiny valid PNG (solid colour) for --dry-run; uses Pillow to stamp text if present."""
    try:
        from PIL import Image, ImageDraw  # type: ignore
        im = Image.new("RGB", (w, h), (28, 28, 32))
        ImageDraw.Draw(im).text((16, 16), text, fill=(200, 200, 210))
        import io
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        import struct
        import zlib
        raw = b"".join(b"\x00" + bytes([40, 40, 48] * w) for _ in range(h))

        def chunk(t: bytes, b: bytes) -> bytes:
            c = t + b
            return struct.pack(">I", len(b)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------ review --

def _image(man: Dict[str, Any], ref: Any) -> Dict[str, Any]:
    imgs = man.get("images", [])
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        idx = int(ref) - 1
        if 0 <= idx < len(imgs):
            return imgs[idx]
    for im in imgs:
        if im.get("file") == ref or Path(str(ref)).name == im.get("file"):
            return im
    raise KeyError(f"no image {ref!r} in job {man['id']}")


def review(jid: str, image: Any, action: str, note: Optional[str] = None) -> Dict[str, Any]:
    action = {"approve": "approved", "reject": "rejected", "unapprove": "pending"}.get(action, action)
    with _lock:
        man = read(jid)
        targets = man.get("images", []) if image in (None, "*", "all") else [_image(man, image)]
        for im in targets:
            if action in IMAGE_STATUSES:
                im["status"] = action
            elif action == "star":
                im["starred"] = True
            elif action == "unstar":
                im["starred"] = False
            elif action == "toggle-star":
                im["starred"] = not im.get("starred")
            elif action == "reset":
                im["status"] = "pending"
                im["starred"] = False
            elif action == "note":
                pass
            else:
                raise ValueError(f"unknown review action {action!r}")
            if note is not None:
                im["note"] = note
            im["reviewed"] = _now()
        write(man)
        return man


def set_notes(jid: str, notes: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    with _lock:
        man = read(jid)
        man["notes"] = notes
        if tags is not None:
            man["tags"] = tags
        write(man)
        return man


def delete(jid: str) -> None:
    d = job_dir(jid)
    if d.is_dir():
        shutil.rmtree(d)


def image_path(jid: str, image: Any) -> Path:
    man = read(jid)
    return job_dir(jid) / _image(man, image)["file"]


def approved_images(jids: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    out = []
    for man in (read(j) for j in jids) if jids else list_jobs(limit=10000):
        for im in man.get("images", []):
            if im.get("status") == "approved":
                out.append({"job": man["id"], "brand": man.get("brand"), "label": man.get("label"),
                            "file": im["file"], "path": str(job_dir(man["id"]) / im["file"]),
                            "starred": im.get("starred"), "note": im.get("note")})
    return out


def costs(limit: int = 10000) -> Dict[str, Any]:
    total, n, by_brand = 0.0, 0, {}
    for man in list_jobs(limit=limit):
        c = man.get("cost_estimate") or 0.0
        total += c
        n += len(man.get("images", []))
        b = man.get("brand") or "-"
        by_brand[b] = round(by_brand.get(b, 0.0) + c, 4)
    return {"images": n, "usd_estimate": round(total, 2), "by_brand": by_brand,
            "note": "estimate from PRICE_TABLE in config.py — unverified against the live pricing page"}
