"""Hand approved art to the sibling ventures. Every target is a *local file drop*;
nothing here talks to Printify, Etsy or a social account — those stay behind
their own human gates (fleet rule 5).

Targets
-------
tee-empire  copies ``<slug>.png`` + ``<slug>.empirespec.json`` into the tee-empire
            inbox (``EMPIRE_INBOX`` or ``/app/tee-empire/inbox``). tee-empire's
            ``empire drop`` / ``empire watch`` then fans it out into Printify
            *drafts* (still dry-run unless the operator passes ``--live``).
clemtock    copies into ``/app/clemtock/assets/<category>/<slug>.png``; the
            studio auto-rescans, or we POST /api/rescan if the server is up.
au2         copies the master PNG into ``/app/AU2/assets/img/merch/masters/``
            (masters are deliberately not in the au2 repo — .gitignore them there).
dir         copies into any directory you name.
"""
from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, jobs
from .brands import load as load_brand

TARGETS = ("tee-empire", "clemtock", "au2", "dir")


def _slug_for(man: Dict[str, Any], im: Dict[str, Any], override: Optional[str]) -> str:
    if override:
        return jobs.slugify(override, 48)
    base = jobs.slugify(man.get("label") or man["id"], 40)
    return f"{base}-{Path(im['file']).stem}"


def _copy(src: Path, dst: Path, overwrite: bool) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not overwrite:
        stem, suf, i = dst.stem, dst.suffix, 2
        while dst.exists():
            dst = dst.with_name(f"{stem}-{i}{suf}")
            i += 1
    shutil.copy2(src, dst)
    return dst


def to_tee_empire(jid: str, image: Any, *, slug: Optional[str] = None, prompt: Optional[str] = None,
                  text: str = "", font: str = "bold_sans", color: str = "white", placement: str = "back",
                  inbox: Optional[Path] = None, overwrite: bool = False) -> Dict[str, Any]:
    man = jobs.read(jid)
    im = jobs._image(man, image)
    inbox = inbox or config.TEE_EMPIRE_INBOX
    if not inbox.parent.is_dir():
        raise FileNotFoundError(f"tee-empire not found at {inbox.parent} (set TEE_EMPIRE_DIR / EMPIRE_INBOX)")
    inbox.mkdir(parents=True, exist_ok=True)
    s = _slug_for(man, im, slug)
    dst = _copy(jobs.job_dir(jid) / im["file"], inbox / f"{s}{Path(im['file']).suffix}", overwrite)
    spec = {
        "prompt": prompt if prompt is not None else (man.get("label") or ""),
        "text": text, "font": font, "color": color, "placement": placement,
        "portrender": {"job": jid, "image": im["file"], "brand": man.get("brand"),
                       "template": man.get("template"), "model": man.get("model")},
    }
    brand_slug = None
    if man.get("brand"):
        try:
            brand_slug = load_brand(man["brand"]).get("handoff.tee_empire_brand") or None
        except Exception:  # noqa: BLE001
            brand_slug = None
    if brand_slug:
        spec["brand"] = brand_slug
    sidecar = dst.with_name(dst.stem + ".empirespec.json")
    sidecar.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    _record(man, im, "tee-empire", str(dst))
    hint = f"cd {inbox.parent} && python3 -m empire drop" + (f" --brand {brand_slug}" if brand_slug else "")
    return {"target": "tee-empire", "image": str(dst), "sidecar": str(sidecar), "next": hint + "   # add --live to create Printify drafts"}


def to_clemtock(jid: str, image: Any, *, category: str = "mascots", slug: Optional[str] = None,
                clemtock_dir: Optional[Path] = None, overwrite: bool = False, rescan: bool = True) -> Dict[str, Any]:
    man = jobs.read(jid)
    im = jobs._image(man, image)
    root = clemtock_dir or config.CLEMTOCK_DIR
    assets = root / "assets"
    if not assets.is_dir():
        raise FileNotFoundError(f"clemtock assets dir not found at {assets} (set CLEMTOCK_DIR)")
    if category not in ("logos", "mascots", "characters", "creatures", "uploads"):
        raise ValueError("category must be one of logos|mascots|characters|creatures|uploads")
    s = _slug_for(man, im, slug)
    dst = _copy(jobs.job_dir(jid) / im["file"], assets / category / f"{s}{Path(im['file']).suffix}", overwrite)
    _record(man, im, "clemtock", str(dst))
    rescanned = False
    if rescan:
        try:
            req = urllib.request.Request(f"{config.CLEMTOCK_URL}/api/rescan", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5):
                rescanned = True
        except Exception:  # noqa: BLE001
            rescanned = False
    return {"target": "clemtock", "image": str(dst), "rescanned": rescanned,
            "next": None if rescanned else f"studio not reachable at {config.CLEMTOCK_URL}; it rescans every 15 min or run scripts/build-library.py"}


def to_au2(jid: str, image: Any, *, slug: Optional[str] = None, au2_dir: Optional[Path] = None,
           overwrite: bool = False) -> Dict[str, Any]:
    man = jobs.read(jid)
    im = jobs._image(man, image)
    root = au2_dir or config.AU2_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"AU2 checkout not found at {root} (set AU2_DIR)")
    masters = root / "assets" / "img" / "merch" / "masters"
    s = _slug_for(man, im, slug)
    dst = _copy(jobs.job_dir(jid) / im["file"], masters / f"{s}{Path(im['file']).suffix}", overwrite)
    _record(man, im, "au2", str(dst))
    return {"target": "au2", "image": str(dst),
            "next": "add a design entry in assets/data/products.json, derive 520/1000w JPEG+WebP into assets/img/merch/, run scripts/build-merch.py"}


def to_dir(jid: str, image: Any, *, directory: Path, slug: Optional[str] = None, overwrite: bool = False) -> Dict[str, Any]:
    man = jobs.read(jid)
    im = jobs._image(man, image)
    s = _slug_for(man, im, slug)
    dst = _copy(jobs.job_dir(jid) / im["file"], Path(directory) / f"{s}{Path(im['file']).suffix}", overwrite)
    _record(man, im, "dir", str(dst))
    return {"target": "dir", "image": str(dst)}


def _record(man: Dict[str, Any], im: Dict[str, Any], target: str, path: str) -> None:
    with jobs._lock:
        fresh = jobs.read(man["id"])
        for cand in fresh.get("images", []):
            if cand["file"] == im["file"]:
                cand.setdefault("exports", []).append({"target": target, "path": path, "at": jobs._now()})
        jobs.write(fresh)


def export(jid: str, image: Any, target: str, **kw: Any) -> Dict[str, Any]:
    if target == "tee-empire":
        return to_tee_empire(jid, image, **kw)
    if target == "clemtock":
        return to_clemtock(jid, image, **kw)
    if target == "au2":
        return to_au2(jid, image, **kw)
    if target == "dir":
        return to_dir(jid, image, **kw)
    raise ValueError(f"unknown export target {target!r}; choose {TARGETS}")


def targets_available() -> Dict[str, bool]:
    return {
        "tee-empire": config.TEE_EMPIRE_DIR.is_dir(),
        "clemtock": (config.CLEMTOCK_DIR / "assets").is_dir(),
        "au2": config.AU2_DIR.is_dir(),
        "dir": True,
    }
