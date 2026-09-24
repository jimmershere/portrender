"""``portrender`` command-line interface. Every web-UI action has a CLI twin here
(human ↔ agent parity, same convention as clemtock's studio).

    portrender doctor
    portrender brands | brands show maddhatch
    portrender templates | templates show tee-graphic | templates new NAME --prompt-file f.txt
    portrender prompt  -t tee-graphic -b maddhatch --var subject_desc="…"      # preview only
    portrender render  -t tee-graphic -b maddhatch --var subject_desc="…" -n 4
    portrender render  -p "free-form prompt" --size 1536x1024 --quality high --bg transparent
    portrender edit    JOB:2 -p "make the chicken wink" -n 2 --fidelity high
    portrender ls [--status done] [--brand au2] [--pending] [--starred]
    portrender show JOB
    portrender approve JOB 1 3   |  reject JOB 2  |  star JOB 1  |  note JOB 1 "…"
    portrender export JOB 1 --to tee-empire [--text "EST. 2024" --placement back]
    portrender costs
    portrender serve [--host 0.0.0.0] [--port 3070]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import (__version__, brands as brands_mod, characters, config,
               export as export_mod, jobs, openai_images, prompts, video as video_mod)


def _kv(pairs: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--var expects key=value, got {p!r}")
        k, _, v = p.partition("=")
        if v.startswith("@"):
            v = Path(v[1:]).read_text(encoding="utf-8").strip()
        out[k.strip()] = v
    return out


def _emit(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    elif isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(obj)


def _split_ref(ref: str) -> Tuple[str, Optional[str]]:
    """JOB, JOB:2, JOB/02.png → (job, image)."""
    if ":" in ref:
        j, _, i = ref.partition(":")
        return j, i
    if "/" in ref and not Path(ref).is_file():
        j, _, i = ref.partition("/")
        return j, i
    return ref, None


def _resolve_sources(refs: List[str]) -> List[str]:
    out: List[str] = []
    for r in refs:
        p = Path(r)
        if p.is_file():
            out.append(str(p.resolve()))
            continue
        j, i = _split_ref(r)
        out.append(str(jobs.image_path(j, i or 1).resolve()))
    return out


# --------------------------------------------------------------- commands --

def cmd_doctor(a: argparse.Namespace) -> int:
    info = config.describe()
    info["version"] = __version__
    info["python"] = sys.version.split()[0]
    info["pillow"] = _has_pillow()
    info["templates_count"] = len(prompts.list_templates())
    info["brands_count"] = len(brands_mod.list_brands())
    info["export_targets"] = export_mod.targets_available()
    if a.probe:
        key = config.api_key()
        info["probe"] = openai_images.probe(key) if key else {"ok": False, "error": "no key"}
    _emit(info, True)
    problems = []
    if not info["api_key_present"]:
        problems.append("OPENAI_API_KEY missing — export it or put it in .env (never commit it)")
    if a.probe and not info.get("probe", {}).get("ok"):
        problems.append("API probe failed — see 'probe' above")
    for p in problems:
        print(f"!! {p}", file=sys.stderr)
    return 1 if problems else 0


def _has_pillow() -> bool:
    try:
        import PIL  # type: ignore # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def cmd_characters(a: argparse.Namespace) -> int:
    """The reusable face roster — who can be made to talk, and by which engine."""
    if a.sub == "show":
        _emit(characters.load(a.name).summary(), True)
        return 0
    rows = characters.roster()
    if a.json:
        _emit([c.summary() for c in rows], True)
        return 0
    if not rows:
        print("no characters yet — put artwork at brands/<slug>/character.png")
        return 0
    for c in rows:
        engines = ",".join(c.engines) or "-"
        mark = "OK " if c.ready else "!! "
        print(f"{mark}{c.slug:14} {c.name:24} engines: {engines:16} mouths: {len(c.mouths)}/9")
        for b in c.blockers():
            print(f"     - {b}")
    return 0


def cmd_video(a: argparse.Namespace) -> int:
    """Queue (and by default run) a talking-character video job."""
    try:
        man = video_mod.create(character=a.character, text=a.text, engine=a.engine,
                               label=a.label or "", aspect=a.aspect)
    except (ValueError, RuntimeError) as e:
        print(f"portrender video: {e}", file=sys.stderr)
        return 2
    print(f"queued {man['id']}  character={man['character']} engine={man['engine']}",
          file=sys.stderr)
    if a.queue_only:
        _emit(jobs.summarize(man), a.json)
        return 0
    man = video_mod.run(man["id"], dry_run=a.dry_run)
    _emit(jobs.summarize(man), a.json)
    return 0 if man.get("status") == "done" else 1


def cmd_brands(a: argparse.Namespace) -> int:
    if a.sub == "show":
        _emit(brands_mod.load(a.name).summary(), True)
        return 0
    rows = brands_mod.list_brands()
    if a.json:
        _emit([b.summary() for b in rows], True)
    else:
        for b in rows:
            print(f"{b.slug:14} {b.name:26} {b.get('tagline', '')}")
    return 0


def cmd_templates(a: argparse.Namespace) -> int:
    if a.sub == "show":
        _emit(prompts.load(a.name).summary(), True)
        return 0
    if a.sub == "new":
        body = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else (a.prompt or "")
        if not body.strip():
            raise SystemExit("templates new: give --prompt or --prompt-file")
        vars_ = {}
        for v in a.var or []:
            k, _, d = v.partition("=")
            vars_[k] = {"default": d} if d else {"required": True}
        p = prompts.save_template(a.name, title=a.title or a.name, prompt=body, description=a.description or "",
                                  tags=a.tags.split(",") if a.tags else [], kind=a.kind, subject=a.subject,
                                  defaults={k: v for k, v in (("size", a.size), ("quality", a.quality),
                                                              ("background", a.bg)) if v},
                                  vars=vars_, overwrite=a.force)
        print(f"wrote {p}")
        return 0
    rows = prompts.list_templates()
    if a.json:
        _emit([t.summary() for t in rows], True)
    else:
        for t in rows:
            req = [k for k, s in t.vars.items() if s.get("required")]
            print(f"{t.name:22} {t.kind:8} {t.subject:15} {t.title}" + (f"   needs: {', '.join(req)}" if req else ""))
    return 0


def _compose(a: argparse.Namespace) -> Tuple[str, Optional[prompts.Template], Optional[brands_mod.Brand], Dict[str, str]]:
    tpl = prompts.load(a.template) if getattr(a, "template", None) else None
    brand = brands_mod.load(a.brand) if getattr(a, "brand", None) else None
    user_vars = _kv(getattr(a, "var", None) or [])
    raw = getattr(a, "prompt", None) or ""
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    if not tpl and not raw.strip():
        raise SystemExit("give --prompt/-p or --template/-t")
    extra_avoid = [s.strip() for s in (getattr(a, "avoid", None) or "").split(",") if s.strip()]
    if not tpl and getattr(a, "subject", None):
        user_vars.setdefault("subject", a.subject)
    text, ctx, missing = prompts.render_prompt(tpl, user_vars, brand, raw_prompt=raw if (raw.strip() and not tpl) else "",
                                               extra_avoid=extra_avoid)
    if tpl and raw.strip():
        # template + free text: free text is appended as extra direction
        text = f"{text}\n{raw.strip()}"
    if missing and not getattr(a, "allow_missing", False):
        raise SystemExit(f"template '{tpl.name}' needs --var for: {', '.join(missing)}")
    return text, tpl, brand, user_vars


def _params(a: argparse.Namespace, tpl: Optional[prompts.Template]) -> Dict[str, Any]:
    d = tpl.defaults if tpl else {}
    return {
        "model": a.model or d.get("model") or config.DEFAULT_MODEL,
        "n": int(a.n or d.get("n") or config.DEFAULT_N),
        "size": a.size or d.get("size") or config.DEFAULT_SIZE,
        "quality": a.quality or d.get("quality") or config.DEFAULT_QUALITY,
        "background": a.bg or d.get("background") or config.DEFAULT_BACKGROUND,
        "output_format": a.format or config.DEFAULT_FORMAT,
    }


def cmd_prompt(a: argparse.Namespace) -> int:
    text, tpl, brand, user_vars = _compose(a)
    if a.json:
        _emit({"prompt": text, "template": tpl.name if tpl else None, "brand": brand.slug if brand else None,
               "vars": user_vars, "params": _params(a, tpl)}, True)
    else:
        print(text)
    return 0


def _label(a: argparse.Namespace, tpl: Optional[prompts.Template], user_vars: Dict[str, str], text: str) -> str:
    if a.label:
        return a.label
    for k in ("headline", "title", "name", "subject_desc", "concept"):
        if user_vars.get(k):
            return user_vars[k][:48]
    if tpl:
        return tpl.name
    return text.splitlines()[0][:48]


def cmd_render(a: argparse.Namespace) -> int:
    text, tpl, brand, user_vars = _compose(a)
    p = _params(a, tpl)
    man = jobs.create(kind="generate", prompt=text, label=_label(a, tpl, user_vars, text),
                      brand=brand.slug if brand else None, template=tpl.name if tpl else None,
                      vars=user_vars, notes=a.notes or "", tags=a.tags.split(",") if a.tags else [], **p)
    if a.queue_only:
        _emit(man if a.json else f"queued {man['id']}", a.json)
        return 0
    man = jobs.run(man["id"], dry_run=a.dry_run)
    _emit(jobs.summarize(man) if a.json else _fmt_done(man), a.json)
    return 0 if man["status"] == "done" else 1


def cmd_edit(a: argparse.Namespace) -> int:
    sources = _resolve_sources([a.source] + (a.ref or []))
    parent = None
    j, i = _split_ref(a.source)
    if not Path(a.source).is_file():
        parent = {"job": j, "image": i or "1"}
    tpl = prompts.load(a.template) if a.template else None
    brand = brands_mod.load(a.brand) if a.brand else (brands_mod.load(jobs.read(j)["brand"]) if parent and jobs.read(j).get("brand") else None)
    user_vars = _kv(a.var or [])
    raw = a.prompt or ""
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    if tpl:
        text, _, missing = prompts.render_prompt(tpl, user_vars, brand)
        if raw.strip():
            text += "\n" + raw.strip()
    else:
        if not raw.strip():
            raise SystemExit("edit needs --prompt/-p (the instruction) or --template")
        text = raw.strip()
    if not a.no_preserve:
        text += "\nPreserve the existing typography, palette and composition. Only change what the instruction asks for."
    p = _params(a, tpl)
    if not a.size and not (tpl and tpl.defaults.get("size")):
        p["size"] = "auto"
    p["model"] = a.model or (tpl.defaults.get("model") if tpl else None) or config.DEFAULT_EDIT_MODEL
    label = a.label or (f"edit-{jobs.read(j)['label']}" if parent else f"edit-{Path(a.source).stem}")
    man = jobs.create(kind="edit", prompt=text, label=label, brand=brand.slug if brand else None,
                      template=tpl.name if tpl else None, vars=user_vars, parent=parent, sources=sources,
                      input_fidelity=a.fidelity, notes=a.notes or "", **p)
    if a.mask:
        man["mask"] = str(Path(a.mask).resolve())
        jobs.write(man)
    if a.queue_only:
        _emit(man if a.json else f"queued {man['id']}", a.json)
        return 0
    man = jobs.run(man["id"], dry_run=a.dry_run)
    _emit(jobs.summarize(man) if a.json else _fmt_done(man), a.json)
    return 0 if man["status"] == "done" else 1


def cmd_run(a: argparse.Namespace) -> int:
    # Video jobs are rendered by clemtock, not by the Images API — dispatch on kind so
    # `run` works the same from the CLI and from the web UI's background spawn.
    if jobs.read(a.job).get("kind") == "video":
        man = video_mod.run(a.job, dry_run=a.dry_run)
    else:
        man = jobs.run(a.job, dry_run=a.dry_run)
    _emit(jobs.summarize(man) if a.json else _fmt_done(man), a.json)
    return 0 if man["status"] == "done" else 1


def _fmt_done(man: Dict[str, Any]) -> str:
    d = jobs.job_dir(man["id"])
    if man["status"] != "done":
        return f"{man['id']}: {man['status']} — {man.get('error')}"
    lines = [f"{man['id']}  ({len(man['images'])} image(s), {man.get('elapsed_s')}s, ~${man.get('cost_estimate')})"]
    for im in man["images"]:
        lines.append(f"  {d / im['file']}")
    lines.append(f"review: portrender approve {man['id']} 1   |   portrender edit {man['id']}:1 -p \"…\"")
    return "\n".join(lines)


def cmd_ls(a: argparse.Namespace) -> int:
    rows = jobs.list_jobs(status=a.status, brand=a.brand, limit=a.limit,
                          image_status="pending" if a.pending else ("approved" if a.approved else None),
                          starred=True if a.starred else None, query=a.grep)
    if a.json:
        _emit([jobs.summarize(m) for m in rows], True)
        return 0
    for m in rows:
        s = jobs.summarize(m)
        marks = f"{s['approved']}✓ {s['rejected']}✗ {s['starred']}★"
        print(f"{s['id']:44} {s['status']:7} {s['brand'] or '-':11} {s['n']}img {marks:12} {s['label']}")
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    _emit(jobs.read(a.job), True)
    return 0


def cmd_review(a: argparse.Namespace) -> int:
    action = a.action
    images = a.images or ["all"]
    man = None
    for im in images:
        man = jobs.review(a.job, im if im != "all" else None, action, note=a.note)
    _emit(jobs.summarize(man) if a.json else f"{a.job}: {action} {' '.join(images)}", a.json)
    return 0


def cmd_note(a: argparse.Namespace) -> int:
    if a.image:
        jobs.review(a.job, a.image, "note", note=a.text)
    else:
        jobs.set_notes(a.job, a.text)
    print("ok")
    return 0


def cmd_export(a: argparse.Namespace) -> int:
    kw: Dict[str, Any] = {"slug": a.slug, "overwrite": a.force}
    if a.to == "tee-empire":
        kw.update(prompt=a.prompt, text=a.text or "", font=a.font, color=a.color, placement=a.placement)
    elif a.to == "clemtock":
        kw.update(category=a.category)
    elif a.to == "dir":
        if not a.dir:
            raise SystemExit("--to dir needs --dir PATH")
        kw.update(directory=Path(a.dir))
    results = [export_mod.export(a.job, im, a.to, **kw) for im in (a.images or ["1"])]
    _emit(results, True)
    return 0


def cmd_open(a: argparse.Namespace) -> int:
    d = jobs.job_dir(a.job)
    print(d)
    if a.gui:
        opener = shutil.which("xdg-open") or shutil.which("open")
        if opener:
            subprocess.Popen([opener, str(d)])
    return 0


def cmd_costs(a: argparse.Namespace) -> int:
    _emit(jobs.costs(), True)
    return 0


def cmd_delete(a: argparse.Namespace) -> int:
    if not a.yes:
        raise SystemExit("delete is destructive; re-run with --yes")
    for j in a.jobs:
        jobs.delete(j)
        print(f"deleted {j}")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    from .server import serve
    return serve(host=a.host, port=a.port, dry_run=a.dry_run)


# ------------------------------------------------------------------ parser --

def _add_render_params(p: argparse.ArgumentParser) -> None:
    p.add_argument("-n", type=int, help=f"images per call (default {config.DEFAULT_N})")
    p.add_argument("--size", help="1024x1024 | 1536x1024 | 1024x1536 | auto | WxH (÷16)")
    p.add_argument("--quality", choices=config.QUALITIES)
    p.add_argument("--model", help=f"default {config.DEFAULT_MODEL}; known: {', '.join(config.KNOWN_MODELS)}")
    p.add_argument("--bg", choices=config.BACKGROUNDS, help="transparent needs png/webp")
    p.add_argument("--format", choices=["png", "jpeg", "webp"])
    p.add_argument("--label", help="short human label (defaults to headline/template)")
    p.add_argument("--notes", help="free-text note stored on the job")
    p.add_argument("--tags", help="comma-separated tags")
    p.add_argument("--dry-run", action="store_true", help="no API call; writes placeholder PNGs")
    p.add_argument("--queue-only", action="store_true", help="create the job but do not run it")
    p.add_argument("--json", action="store_true")


def _add_compose(p: argparse.ArgumentParser) -> None:
    p.add_argument("-p", "--prompt", help="free-form prompt, or @file.txt")
    p.add_argument("-t", "--template", help="template name from prompts/templates/")
    p.add_argument("-b", "--brand", help="brand slug from brands/")
    p.add_argument("--var", action="append", metavar="KEY=VALUE", help="template variable (value may be @file)")
    p.add_argument("--subject", choices=["cartoon_mascot", "humanoid", "animal", "typography_only", "product", "none"],
                   help="avoid-vocabulary for free-form prompts")
    p.add_argument("--avoid", help="extra comma-separated avoid terms")
    p.add_argument("--allow-missing", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="portrender", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"portrender {__version__}")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("doctor", help="config, key presence, sibling ventures"); p.add_argument("--probe", action="store_true", help="auth-only API call"); p.set_defaults(fn=cmd_doctor)

    p = sp.add_parser("video", help="render a talking-character video (delegates to clemtock)")
    p.add_argument("-c", "--character", required=True, help="character slug, e.g. jimmer")
    p.add_argument("-t", "--text", required=True, help="what they say")
    p.add_argument("--engine", default="", choices=["", "heygen", "cartoon"],
                   help="heygen = paid, professional; cartoon = free, local")
    p.add_argument("--aspect", default="9:16")
    p.add_argument("--label", default="")
    p.add_argument("--queue-only", action="store_true", help="create the job, do not render")
    p.add_argument("--dry-run", action="store_true", help="no clemtock call, no spend")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_video)

    p = sp.add_parser("characters", help="list reusable characters (jimmer, …) and what can render them")
    p.add_argument("sub", nargs="?", choices=["show"]); p.add_argument("name", nargs="?")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_characters)

    p = sp.add_parser("brands", help="list brands"); p.add_argument("sub", nargs="?", choices=["show"]); p.add_argument("name", nargs="?"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_brands)

    p = sp.add_parser("templates", help="list / show / new prompt templates")
    p.add_argument("sub", nargs="?", choices=["show", "new"]); p.add_argument("name", nargs="?")
    p.add_argument("--json", action="store_true"); p.add_argument("--prompt"); p.add_argument("--prompt-file")
    p.add_argument("--title"); p.add_argument("--description"); p.add_argument("--tags"); p.add_argument("--kind", default="generate", choices=["generate", "edit"])
    p.add_argument("--subject", default="none"); p.add_argument("--size"); p.add_argument("--quality"); p.add_argument("--bg")
    p.add_argument("--var", action="append", help="KEY (required) or KEY=default"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_templates)

    p = sp.add_parser("prompt", help="preview the final prompt without rendering"); _add_compose(p); _add_render_params(p); p.set_defaults(fn=cmd_prompt)

    p = sp.add_parser("render", help="generate images"); _add_compose(p); _add_render_params(p); p.set_defaults(fn=cmd_render)

    p = sp.add_parser("edit", help="edit an existing image (JOB:N, JOB/02.png or a file path)")
    p.add_argument("source"); p.add_argument("--ref", action="append", help="extra reference image(s): JOB:N or path")
    p.add_argument("--mask", help="PNG mask (transparent = area to replace)")
    p.add_argument("--fidelity", choices=["high", "low"], help="input_fidelity")
    p.add_argument("--no-preserve", action="store_true", help="skip the 'preserve typography/palette' guard clause")
    _add_compose(p); _add_render_params(p); p.set_defaults(fn=cmd_edit)

    p = sp.add_parser("run", help="run a queued job"); p.add_argument("job"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_run)

    p = sp.add_parser("ls", help="list jobs"); p.add_argument("--status", choices=["queued", "running", "done", "error"]); p.add_argument("--brand")
    p.add_argument("--pending", action="store_true"); p.add_argument("--approved", action="store_true"); p.add_argument("--starred", action="store_true")
    p.add_argument("--grep"); p.add_argument("--limit", type=int, default=50); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_ls)

    p = sp.add_parser("show", help="dump a job manifest"); p.add_argument("job"); p.set_defaults(fn=cmd_show)

    for name in ("approve", "reject", "star", "unstar", "reset"):
        p = sp.add_parser(name, help=f"{name} image(s) of a job (default: all)")
        p.add_argument("job"); p.add_argument("images", nargs="*", help="1 2 … or file names; omit for all")
        p.add_argument("--note"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_review, action=name)
    p = sp.add_parser("review", help="generic review action"); p.add_argument("job"); p.add_argument("action", choices=["approve", "reject", "pending", "star", "unstar", "toggle-star", "reset", "note"])
    p.add_argument("images", nargs="*"); p.add_argument("--note"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_review)

    p = sp.add_parser("note", help="attach a note to a job or an image"); p.add_argument("job"); p.add_argument("text"); p.add_argument("--image"); p.set_defaults(fn=cmd_note)

    p = sp.add_parser("export", help="hand an image to tee-empire / clemtock / au2 / a directory")
    p.add_argument("job"); p.add_argument("images", nargs="*"); p.add_argument("--to", required=True, choices=export_mod.TARGETS)
    p.add_argument("--slug"); p.add_argument("--force", action="store_true"); p.add_argument("--dir")
    p.add_argument("--prompt", help="tee-empire: seed prompt for title/description"); p.add_argument("--text", help="tee-empire: back/under stamp text")
    p.add_argument("--font", default="bold_sans"); p.add_argument("--color", default="white"); p.add_argument("--placement", default="back", choices=["back", "underneath", "left_sleeve", "right_sleeve", "neck"])
    p.add_argument("--category", default="mascots", help="clemtock: logos|mascots|characters|creatures|uploads")
    p.set_defaults(fn=cmd_export)

    p = sp.add_parser("open", help="print (and optionally open) a job folder"); p.add_argument("job"); p.add_argument("--gui", action="store_true"); p.set_defaults(fn=cmd_open)
    p = sp.add_parser("costs", help="running spend estimate"); p.set_defaults(fn=cmd_costs)
    p = sp.add_parser("delete", help="delete job folders"); p.add_argument("jobs", nargs="+"); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_delete)

    p = sp.add_parser("serve", help="web UI + JSON API")
    p.add_argument("--host", default=config.DEFAULT_HOST); p.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    p.add_argument("--dry-run", action="store_true", help="server renders placeholders instead of calling the API")
    p.set_defaults(fn=cmd_serve)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    config.load_env()
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        return int(a.fn(a) or 0)
    except (FileNotFoundError, KeyError, ValueError, FileExistsError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
