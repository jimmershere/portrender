"""Video jobs — a talking-character clip, reviewed in the same queue as artwork.

portrender already owns a review loop: render, look, approve/reject/star, hand off. A
draft video is the same shape of problem, so a video is a **job kind** rather than a
parallel system. The existing gallery, lightbox, approve keys and export routing all work
on it unchanged.

## portrender does not call HeyGen

It shells out to clemtock, which owns the provider code and the key:

    python3 -m clemtock avatar --provider heygen --brand <character> --text "…" --out …

That keeps two rules intact at once. portrender's LAN web UI has no auth, so it must not
hold a HeyGen or social credential. And clemtock stays the single place a video provider
is implemented, so a v3 migration or a swap to a different engine happens once.

The same delegation is the answer to publishing: portrender records the *decision* and
triggers the tool that owns the *credential*. It never posts anything itself — see
CLAUDE.md, "Nothing here publishes".
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import characters, config, jobs

ENGINES = ("heygen", "cartoon")
DEFAULT_ENGINE = os.environ.get("PORTRENDER_VIDEO_ENGINE", "heygen")


def clemtock_dir() -> Path:
    d = config.CLEMTOCK_DIR
    if not (d / "backend" / "clemtock").is_dir():
        raise RuntimeError(
            f"clemtock not found at {d} — set CLEMTOCK_DIR. portrender delegates video "
            f"rendering to it rather than holding provider keys itself.")
    return d


def create(*, character: str, text: str, engine: str = "", label: str = "",
           aspect: str = "9:16", notes: str = "") -> Dict[str, Any]:
    """Queue a video job. Nothing is rendered and nothing is spent until run()."""
    engine = (engine or DEFAULT_ENGINE).lower()
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ENGINES)}")
    char = characters.load(character)
    if not char.has_art:
        raise ValueError(f"character {character!r} has no artwork ({char.dir}/character.png)")
    if engine == "heygen" and not char.can_heygen:
        raise ValueError(f"{character!r} cannot use heygen: " + "; ".join(char.blockers()))
    if engine == "cartoon" and not char.can_local:
        raise ValueError(f"{character!r} cannot use the local engine: "
                         + "; ".join(char.blockers()))

    man = jobs.create(
        kind="video", prompt=text, label=label or text[:48], brand=character,
        template=None, vars={}, model=f"clemtock:{engine}", n=1,
        size=aspect, quality="-", background="-", output_format="mp4", notes=notes)
    man["character"] = character
    man["engine"] = engine
    man["aspect"] = aspect
    jobs.write(man)
    return man


def run(jid: str, *, dry_run: bool = False) -> Dict[str, Any]:
    """Render a queued video job by driving clemtock."""
    man = jobs.read(jid)
    if man.get("status") == "done":
        return man
    man["status"] = "running"
    man["started"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    jobs.write(man)
    d = jobs.job_dir(jid)
    out = d / "01.mp4"
    engine = man.get("engine", DEFAULT_ENGINE)
    t0 = time.time()

    try:
        if dry_run:
            jobs.log(jid, "dry-run: no clemtock call, no spend")
            out.write_bytes(b"")
        else:
            root = clemtock_dir()
            cmd = ["python3", "-m", "clemtock", "avatar",
                   "--provider", engine, "--brand", man["character"],
                   "--text", man["prompt"], "--out", str(out)]
            jobs.log(jid, "clemtock: " + " ".join(cmd[3:]))
            proc = subprocess.run(cmd, cwd=str(root / "backend"),
                                  capture_output=True, timeout=3600)
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-6:]
            for line in tail:
                jobs.log(jid, "  " + line)
            if proc.returncode != 0 or not out.is_file():
                raise RuntimeError("clemtock failed: " + (" / ".join(tail) or "no output"))

        # A poster frame, so the gallery can show the draft without playing it.
        thumb = d / "01.thumb.jpg"
        if out.stat().st_size and shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out),
                            "-frames:v", "1", "-vf", "scale=384:-1", str(thumb)],
                           capture_output=True, timeout=120)

        duration = _duration(out)
        man["images"] = [{
            "n": 1, "file": out.name, "thumb": thumb.name if thumb.is_file() else None,
            "status": "pending", "note": None, "starred": False,
            "video": True, "duration": duration,
        }]
        man["status"] = "done"
        man["elapsed"] = round(time.time() - t0, 1)
        man["duration"] = duration
        man["error"] = None
    except Exception as exc:  # noqa: BLE001
        man["status"] = "error"
        man["error"] = str(exc)[:500]
        jobs.log(jid, f"ERROR: {man['error']}")
    jobs.write(man)
    return man


def _duration(path: Path) -> Optional[float]:
    if not shutil.which("ffprobe") or not path.is_file() or not path.stat().st_size:
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(path)],
                             capture_output=True, timeout=60).stdout.decode().strip()
        return round(float(out), 2)
    except (ValueError, subprocess.SubprocessError):
        return None


def pending_review() -> List[Dict[str, Any]]:
    """Video jobs with at least one image still awaiting a verdict."""
    out = []
    for man in (jobs.read(j["id"]) for j in jobs.list_jobs(limit=500)):
        if man.get("kind") != "video":
            continue
        if any(i.get("status") == "pending" for i in man.get("images") or []):
            out.append(jobs.summarize(man))
    return out
