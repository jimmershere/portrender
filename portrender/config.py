"""Paths, environment and defaults.

Everything is resolved relative to the repo root (the directory holding
``pyproject.toml``), so the same checkout works at ``/app/portrender`` on
pop-os and on quasimodo without any per-host path.

Secrets are never written by this package. ``OPENAI_API_KEY`` is read from the
process environment first; if absent, the ``.env``-style files listed in
``PORTRENDER_ENV_FILES`` are read (default: ``./.env`` then
``/app/tee-empire/.env`` — the key already lives there for clemtock as well).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(os.environ.get("PORTRENDER_HOME") or Path(__file__).resolve().parents[1])
DATA_DIR = Path(os.environ.get("PORTRENDER_DATA") or ROOT / "data")
RENDERS_DIR = DATA_DIR / "renders"
JOBS_DIR = DATA_DIR / "jobs"
REFS_DIR = DATA_DIR / "refs"
TEMPLATES_DIR = ROOT / "prompts" / "templates"
BRANDS_DIR = ROOT / "brands"
WEB_DIR = Path(__file__).resolve().parent / "web"

# Model names verified against the OpenAI Images API reference on 2026-09-21.
# Prices are NOT verified — see docs/DESIGN.md "Cost". Override in .env.
DEFAULT_MODEL = os.environ.get("PORTRENDER_MODEL", "gpt-image-2")
DEFAULT_EDIT_MODEL = os.environ.get("PORTRENDER_EDIT_MODEL", DEFAULT_MODEL)
KNOWN_MODELS = [
    "gpt-image-2",
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-1.5",
    "gpt-image-1",
    "gpt-image-1-mini",
    "chatgpt-image-latest",
]
DEFAULT_SIZE = os.environ.get("PORTRENDER_SIZE", "1024x1024")
DEFAULT_QUALITY = os.environ.get("PORTRENDER_QUALITY", "medium")
DEFAULT_BACKGROUND = os.environ.get("PORTRENDER_BACKGROUND", "auto")
DEFAULT_FORMAT = os.environ.get("PORTRENDER_FORMAT", "png")
DEFAULT_N = int(os.environ.get("PORTRENDER_N", "2"))
QUALITIES = ["low", "medium", "high", "xhigh", "max", "auto"]
SIZES = ["1024x1024", "1536x1024", "1024x1536", "auto"]
BACKGROUNDS = ["auto", "transparent", "opaque"]

# Web UI / API
DEFAULT_HOST = os.environ.get("PORTRENDER_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORTRENDER_PORT", "3070"))

# Sibling ventures (all optional; probed at runtime, never required)
TEE_EMPIRE_DIR = Path(os.environ.get("TEE_EMPIRE_DIR", "/app/tee-empire"))
TEE_EMPIRE_INBOX = Path(os.environ.get("EMPIRE_INBOX") or TEE_EMPIRE_DIR / "inbox")
CLEMTOCK_DIR = Path(os.environ.get("CLEMTOCK_DIR", "/app/clemtock"))
CLEMTOCK_URL = os.environ.get("CLEMTOCK_URL", "http://127.0.0.1:3053")
AU2_DIR = Path(os.environ.get("AU2_DIR", "/app/AU2"))

ENV_FILES: List[Path] = [
    Path(p) for p in os.environ.get(
        "PORTRENDER_ENV_FILES", f"{ROOT / '.env'}:/app/tee-empire/.env"
    ).split(":") if p
]

# Rough per-image USD estimates used ONLY for the running total shown in the UI.
# Unverified against the current pricing page; edit freely, or set
# PORTRENDER_PRICE_JSON to a JSON object {"model|quality": usd}.
PRICE_TABLE: Dict[str, float] = {
    "default|low": 0.02,
    "default|medium": 0.07,
    "default|high": 0.19,
    "default|xhigh": 0.25,
    "default|max": 0.30,
    "default|auto": 0.07,
}


def _parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if v[:1] in "\"'" and v[-1:] == v[:1] and len(v) >= 2:
            v = v[1:-1]
        else:
            v = v.split(" #", 1)[0].rstrip()
        if k:
            out[k] = v
    return out


def load_env(extra_files: Optional[List[Path]] = None) -> Dict[str, str]:
    """Populate os.environ from the env files (without overriding real env)."""
    loaded: Dict[str, str] = {}
    for f in list(extra_files or []) + ENV_FILES:
        for k, v in _parse_env_file(f).items():
            if k not in os.environ and v:
                os.environ[k] = v
                loaded[k] = str(f)
    return loaded


def api_key() -> Optional[str]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        load_env()
        key = os.environ.get("OPENAI_API_KEY")
    return key or None


def price_for(model: str, quality: str) -> Optional[float]:
    table = dict(PRICE_TABLE)
    raw = os.environ.get("PORTRENDER_PRICE_JSON")
    if raw:
        try:
            import json
            table.update(json.loads(raw))
        except Exception:
            pass
    return table.get(f"{model}|{quality}") or table.get(f"default|{quality}")


def ensure_dirs() -> None:
    for d in (DATA_DIR, RENDERS_DIR, JOBS_DIR, REFS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def describe() -> Dict[str, object]:
    """Non-secret snapshot for `portrender doctor` and the UI."""
    return {
        "root": str(ROOT),
        "data": str(DATA_DIR),
        "templates": str(TEMPLATES_DIR),
        "brands": str(BRANDS_DIR),
        "model": DEFAULT_MODEL,
        "edit_model": DEFAULT_EDIT_MODEL,
        "known_models": KNOWN_MODELS,
        "size": DEFAULT_SIZE,
        "quality": DEFAULT_QUALITY,
        "background": DEFAULT_BACKGROUND,
        "n": DEFAULT_N,
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "env_files": [str(p) for p in ENV_FILES],
        "tee_empire_inbox": str(TEE_EMPIRE_INBOX),
        "tee_empire_present": TEE_EMPIRE_DIR.is_dir(),
        "clemtock_dir": str(CLEMTOCK_DIR),
        "clemtock_present": CLEMTOCK_DIR.is_dir(),
        "au2_dir": str(AU2_DIR),
        "au2_present": AU2_DIR.is_dir(),
        "api_key_present": bool(api_key()),
    }
