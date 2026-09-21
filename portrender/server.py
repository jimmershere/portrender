"""Web UI + JSON API on a stdlib ``ThreadingHTTPServer``.

Binds 127.0.0.1:3070 by default. On quasimodo run ``portrender serve --host
0.0.0.0`` and open http://192.168.0.20:3070 from pop-os — LAN-only, no auth,
per fleet rule 2 (build for one operator first).

Renders are executed as subprocesses of the CLI (``portrender run JOB``) so
the UI and the terminal share one code path; the job's ``render.json`` is the
only state. Logs land in ``data/jobs/<id>.log``.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__, brands as brands_mod, config, export as export_mod, jobs, prompts

_procs: Dict[str, subprocess.Popen] = {}
_procs_lock = threading.Lock()
DRY_RUN = False


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------ job runner --

def spawn(jid: str) -> None:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    logf = open(config.JOBS_DIR / f"{jid}.log", "ab")
    args = [sys.executable, "-m", "portrender", "run", jid, "--json"]
    if DRY_RUN:
        args.append("--dry-run")
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    proc = subprocess.Popen(args, cwd=str(config.ROOT), stdout=logf, stderr=subprocess.STDOUT, env=env)
    with _procs_lock:
        _procs[jid] = proc


def _reap() -> None:
    with _procs_lock:
        for jid, p in list(_procs.items()):
            if p.poll() is not None:
                _procs.pop(jid, None)


def running() -> List[str]:
    _reap()
    with _procs_lock:
        return list(_procs.keys())


def _log_tail(jid: str, n: int = 40) -> str:
    for p in (config.JOBS_DIR / f"{jid}.log", jobs.job_dir(jid) / "job.log"):
        if p.is_file():
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                return "\n".join(lines[-n:])
            except OSError:
                pass
    return ""


# ---------------------------------------------------------------- handlers --

def api_state() -> Dict[str, Any]:
    info = config.describe()
    return {
        "version": __version__, "config": info, "dry_run": DRY_RUN,
        "brands": [b.summary() for b in brands_mod.list_brands()],
        "templates": [t.summary() for t in prompts.list_templates()],
        "models": config.KNOWN_MODELS, "qualities": config.QUALITIES, "sizes": config.SIZES,
        "backgrounds": config.BACKGROUNDS, "subjects": ["none", "cartoon_mascot", "humanoid", "animal", "typography_only", "product"],
        "export_targets": export_mod.targets_available(), "running": running(), "costs": jobs.costs(),
        "refs": sorted(p.name for p in config.REFS_DIR.glob("*") if p.is_file()) if config.REFS_DIR.is_dir() else [],
    }


def _compose_from_body(b: Dict[str, Any]):
    tpl = prompts.load(b["template"]) if b.get("template") else None
    brand = brands_mod.load(b["brand"]) if b.get("brand") else None
    user_vars = {str(k): str(v) for k, v in (b.get("vars") or {}).items()}
    raw = (b.get("prompt") or "").strip()
    if not tpl and not raw:
        raise ApiError("prompt or template required")
    if not tpl and b.get("subject"):
        user_vars.setdefault("subject", b["subject"])
    extra_avoid = [s.strip() for s in str(b.get("avoid") or "").split(",") if s.strip()]
    text, ctx, missing = prompts.render_prompt(tpl, user_vars, brand, raw_prompt=raw if (raw and not tpl) else "",
                                               extra_avoid=extra_avoid)
    if tpl and raw:
        text = f"{text}\n{raw}"
    if missing and not b.get("allow_missing"):
        raise ApiError(f"template needs: {', '.join(missing)}")
    return text, tpl, brand, user_vars


def _params_from_body(b: Dict[str, Any], tpl: Optional[prompts.Template], edit: bool = False) -> Dict[str, Any]:
    d = tpl.defaults if tpl else {}
    return {
        "model": b.get("model") or d.get("model") or (config.DEFAULT_EDIT_MODEL if edit else config.DEFAULT_MODEL),
        "n": int(b.get("n") or d.get("n") or config.DEFAULT_N),
        "size": b.get("size") or d.get("size") or ("auto" if edit else config.DEFAULT_SIZE),
        "quality": b.get("quality") or d.get("quality") or config.DEFAULT_QUALITY,
        "background": b.get("background") or d.get("background") or config.DEFAULT_BACKGROUND,
        "output_format": b.get("format") or config.DEFAULT_FORMAT,
    }


def api_prompt(b: Dict[str, Any]) -> Dict[str, Any]:
    text, tpl, brand, user_vars = _compose_from_body(b)
    return {"prompt": text, "params": _params_from_body(b, tpl), "vars": user_vars}


def api_render(b: Dict[str, Any]) -> Dict[str, Any]:
    text, tpl, brand, user_vars = _compose_from_body(b)
    p = _params_from_body(b, tpl)
    label = b.get("label") or user_vars.get("headline") or user_vars.get("subject_desc", "")[:48] or (tpl.name if tpl else text.splitlines()[0][:48])
    man = jobs.create(kind="generate", prompt=text, label=label, brand=brand.slug if brand else None,
                      template=tpl.name if tpl else None, vars=user_vars, notes=b.get("notes") or "",
                      tags=b.get("tags") or [], **p)
    spawn(man["id"])
    return {"job": jobs.summarize(man)}


def _resolve_source(ref: str) -> str:
    ref = str(ref)
    if ref.startswith("ref:"):
        p = config.REFS_DIR / Path(ref[4:]).name
        if not p.is_file():
            raise ApiError(f"no reference {ref}")
        return str(p.resolve())
    if Path(ref).is_file():
        return str(Path(ref).resolve())
    j, _, i = ref.partition(":")
    return str(jobs.image_path(j, i or 1).resolve())


def api_edit(b: Dict[str, Any]) -> Dict[str, Any]:
    src = b.get("source")
    if not src:
        raise ApiError("source required (JOB:N or ref:NAME)")
    sources = [_resolve_source(src)] + [_resolve_source(r) for r in (b.get("refs") or [])]
    parent = None
    if not str(src).startswith("ref:") and not Path(str(src)).is_file():
        j, _, i = str(src).partition(":")
        parent = {"job": j, "image": i or "1"}
    tpl = prompts.load(b["template"]) if b.get("template") else None
    brand_slug = b.get("brand") or (jobs.read(parent["job"]).get("brand") if parent else None)
    brand = brands_mod.load(brand_slug) if brand_slug else None
    user_vars = {str(k): str(v) for k, v in (b.get("vars") or {}).items()}
    raw = (b.get("prompt") or "").strip()
    if tpl:
        text, _, _ = prompts.render_prompt(tpl, user_vars, brand)
        if raw:
            text += "\n" + raw
    else:
        if not raw:
            raise ApiError("prompt (instruction) required")
        text = raw
    if not b.get("no_preserve"):
        text += "\nPreserve the existing typography, palette and composition. Only change what the instruction asks for."
    p = _params_from_body(b, tpl, edit=True)
    label = b.get("label") or (f"edit-{jobs.read(parent['job'])['label']}" if parent else f"edit-{Path(sources[0]).stem}")
    man = jobs.create(kind="edit", prompt=text, label=label, brand=brand.slug if brand else None,
                      template=tpl.name if tpl else None, vars=user_vars, parent=parent, sources=sources,
                      input_fidelity=b.get("fidelity") or None, notes=b.get("notes") or "", **p)
    spawn(man["id"])
    return {"job": jobs.summarize(man)}


def api_review(b: Dict[str, Any]) -> Dict[str, Any]:
    jid, action = b.get("job"), b.get("action")
    if not jid or not action:
        raise ApiError("job and action required")
    images = b.get("images") or ([b["image"]] if b.get("image") else [None])
    man = None
    for im in images:
        man = jobs.review(jid, im, action, note=b.get("note"))
    return {"job": jobs.summarize(man)}


def api_export(b: Dict[str, Any]) -> Dict[str, Any]:
    jid, to = b.get("job"), b.get("to")
    if not jid or to not in export_mod.TARGETS:
        raise ApiError(f"job and to ({'|'.join(export_mod.TARGETS)}) required")
    kw: Dict[str, Any] = {"slug": b.get("slug") or None, "overwrite": bool(b.get("force"))}
    if to == "tee-empire":
        kw.update(prompt=b.get("prompt"), text=b.get("text") or "", font=b.get("font") or "bold_sans",
                  color=b.get("color") or "white", placement=b.get("placement") or "back")
    elif to == "clemtock":
        kw.update(category=b.get("category") or "mascots")
    elif to == "dir":
        if not b.get("dir"):
            raise ApiError("dir required")
        kw.update(directory=Path(b["dir"]))
    results = [export_mod.export(jid, im, to, **kw) for im in (b.get("images") or ["1"])]
    return {"results": results, "job": jobs.summarize(jobs.read(jid))}


def api_templates_save(b: Dict[str, Any]) -> Dict[str, Any]:
    p = prompts.save_template(b["name"], title=b.get("title") or b["name"], prompt=b.get("prompt") or "",
                              description=b.get("description") or "", tags=b.get("tags") or [],
                              kind=b.get("kind") or "generate", subject=b.get("subject") or "none",
                              defaults=b.get("defaults") or {}, vars=b.get("vars") or {}, overwrite=bool(b.get("overwrite")))
    return {"path": str(p), "templates": [t.summary() for t in prompts.list_templates()]}


def api_upload(b: Dict[str, Any]) -> Dict[str, Any]:
    name = re.sub(r"[^\w.\-]+", "-", Path(str(b.get("name") or "ref.png")).name)
    data = b.get("data_b64") or ""
    if "," in data[:64]:
        data = data.split(",", 1)[1]
    blob = base64.b64decode(data)
    if len(blob) > 25 * 1024 * 1024:
        raise ApiError("file too large (25 MB max)")
    config.ensure_dirs()
    dst = config.REFS_DIR / name
    i = 2
    while dst.exists():
        dst = config.REFS_DIR / f"{Path(name).stem}-{i}{Path(name).suffix}"
        i += 1
    dst.write_bytes(blob)
    return {"ref": dst.name, "path": str(dst)}


def api_jobs(q: Dict[str, str]) -> List[Dict[str, Any]]:
    rows = jobs.list_jobs(status=q.get("status") or None, brand=q.get("brand") or None,
                          limit=int(q.get("limit") or 60),
                          image_status=q.get("image_status") or ("pending" if q.get("pending") else None),
                          starred=True if q.get("starred") else None, query=q.get("q") or None)
    return [jobs.summarize(m) for m in rows]


ROUTES_POST = {
    "/api/prompt": api_prompt, "/api/render": api_render, "/api/edit": api_edit,
    "/api/review": api_review, "/api/export": api_export, "/api/templates": api_templates_save,
    "/api/upload": api_upload,
    "/api/notes": lambda b: {"job": jobs.summarize(jobs.set_notes(b["job"], b.get("notes") or "", b.get("tags")))},
    "/api/delete": lambda b: {"deleted": [jobs.delete(j) or j for j in (b.get("jobs") or [])]},
    "/api/rerun": lambda b: (spawn(b["job"]), {"job": jobs.summarize(jobs.read(b["job"]))})[1],
}


class Handler(BaseHTTPRequestHandler):
    server_version = f"portrender/{__version__}"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter default log
        if os.environ.get("PORTRENDER_HTTP_LOG"):
            super().log_message(fmt, *args)

    # -- helpers
    def _json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, cache: bool = False) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=31536000, immutable" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            obj = json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            raise ApiError("body must be JSON")
        if not isinstance(obj, dict):
            raise ApiError("body must be a JSON object")
        return obj

    # -- GET
    def do_GET(self) -> None:  # noqa: N802
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        path = u.path
        try:
            if path in ("/", "/index.html"):
                return self._file(config.WEB_DIR / "index.html")
            if path == "/api/state":
                return self._json(api_state())
            if path == "/api/jobs":
                return self._json(api_jobs(q))
            m = re.fullmatch(r"/api/jobs/([\w\-]+)(/log)?", path)
            if m:
                man = jobs.read(m.group(1))
                if m.group(2):
                    return self._json({"job": m.group(1), "log": _log_tail(m.group(1), int(q.get("n") or 80)),
                                       "running": m.group(1) in running()})
                man["log"] = _log_tail(m.group(1))
                man["running"] = m.group(1) in running()
                return self._json(man)
            m = re.fullmatch(r"/files/([\w\-]+)/((?:thumbs/)?[\w\-.]+)", path)
            if m:
                return self._file(jobs.job_dir(m.group(1)) / m.group(2), cache=True)
            m = re.fullmatch(r"/refs/([\w\-.]+)", path)
            if m:
                return self._file(config.REFS_DIR / m.group(1))
            m = re.fullmatch(r"/static/([\w\-.]+)", path)
            if m:
                return self._file(config.WEB_DIR / m.group(1))
            if path == "/healthz":
                return self._json({"ok": True, "version": __version__, "running": running()})
            self.send_error(HTTPStatus.NOT_FOUND)
        except FileNotFoundError as e:
            self._json({"error": str(e)}, 404)
        except (ApiError, ValueError, KeyError) as e:
            self._json({"error": str(e)}, getattr(e, "status", 400))
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    # -- POST
    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        try:
            fn = ROUTES_POST.get(path)
            if not fn:
                return self.send_error(HTTPStatus.NOT_FOUND)
            return self._json(fn(self._body()))
        except FileNotFoundError as e:
            self._json({"error": str(e)}, 404)
        except (ApiError, ValueError, KeyError, FileExistsError) as e:
            self._json({"error": str(e)}, getattr(e, "status", 400))
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def serve(host: str = config.DEFAULT_HOST, port: int = config.DEFAULT_PORT, dry_run: bool = False) -> int:
    global DRY_RUN
    DRY_RUN = dry_run
    config.ensure_dirs()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    key = "present" if config.api_key() else "MISSING"
    print(f"portrender {__version__} serving on http://{host}:{port}  (OPENAI_API_KEY {key}"
          f"{', DRY-RUN' if dry_run else ''})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
