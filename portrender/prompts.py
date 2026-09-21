"""Reusable prompt templates: ``prompts/templates/<name>.toml``.

A template is a TOML file::

    name = "tee-graphic"
    title = "T-shirt graphic"
    description = "..."
    tags = ["merch", "apparel"]
    kind = "generate"            # or "edit" (needs a source image)
    subject = "cartoon_mascot"   # avoid-vocabulary selector, see craft.py
    size = "1024x1024"           # optional defaults, override per render
    quality = "medium"
    background = "transparent"
    prompt = '''
    Print-ready t-shirt graphic on a {{bg}} background.
    {{subject_desc}}
    Style: {{style}}.
    {{#headline}}{{headline_block}}{{/headline}}
    '''

    [vars.bg]
    default = "black"
    help = "shirt colour the art sits on"
    [vars.subject_desc]
    required = true
    [vars.style]
    default = "{{brand.style}}"

Substitution is deliberately tiny (no Jinja, no logic):
  {{var}}              a variable, brand field ({{brand.style}}) or builtin
  {{#var}}...{{/var}}  emitted only when var is non-empty
  {{^var}}...{{/var}}  emitted only when var is empty
Builtins: headline_block, avoid, single_subject, today.
The avoid clause for ``subject`` is appended automatically unless the template
sets ``avoid = false`` or the prompt already contains "Avoid:".
"""
from __future__ import annotations

import datetime as _dt
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, craft
from .brands import Brand

_VAR = re.compile(r"{{\s*([\w.\-]+)\s*}}")
_SECTION = re.compile(r"{{([#^])\s*([\w.\-]+)\s*}}(.*?){{/\s*\2\s*}}", re.S)


@dataclass
class Template:
    name: str
    title: str
    prompt: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    kind: str = "generate"
    subject: str = "none"
    avoid: bool = True
    defaults: Dict[str, str] = field(default_factory=dict)  # size/quality/background/model/n
    vars: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    path: Optional[Path] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name, "title": self.title, "description": self.description,
            "tags": self.tags, "kind": self.kind, "subject": self.subject,
            "defaults": self.defaults, "vars": self.vars, "prompt": self.prompt,
        }


def _parse(name: str, text: str, path: Optional[Path] = None) -> Template:
    d = tomllib.loads(text)
    if "prompt" not in d:
        raise ValueError(f"template {name}: missing 'prompt'")
    defaults = {k: str(d[k]) for k in ("size", "quality", "background", "model", "n", "input_fidelity") if k in d}
    vars_: Dict[str, Dict[str, Any]] = {}
    for k, v in (d.get("vars") or {}).items():
        vars_[k] = dict(v) if isinstance(v, dict) else {"default": str(v)}
    return Template(
        name=d.get("name", name), title=d.get("title", name), prompt=d["prompt"].strip(),
        description=d.get("description", ""), tags=list(d.get("tags", [])),
        kind=d.get("kind", "generate"), subject=d.get("subject", "none"),
        avoid=bool(d.get("avoid", True)), defaults=defaults, vars=vars_, path=path,
    )


def load(name: str) -> Template:
    p = config.TEMPLATES_DIR / f"{name}.toml"
    if not p.is_file():
        raise FileNotFoundError(f"no template '{name}' at {p}")
    return _parse(name, p.read_text(encoding="utf-8"), p)


def list_templates() -> List[Template]:
    out: List[Template] = []
    if not config.TEMPLATES_DIR.is_dir():
        return out
    for p in sorted(config.TEMPLATES_DIR.glob("*.toml")):
        try:
            out.append(load(p.stem))
        except Exception as e:  # noqa: BLE001
            out.append(Template(name=p.stem, title=f"{p.stem} (broken: {e})", prompt="", path=p))
    return out


def save_template(name: str, *, title: str, prompt: str, description: str = "", tags: List[str] | None = None,
                  kind: str = "generate", subject: str = "none", defaults: Dict[str, str] | None = None,
                  vars: Dict[str, Dict[str, Any]] | None = None, overwrite: bool = False) -> Path:
    """Write a template TOML by hand (tomllib is read-only). Names are slugs."""
    slug = re.sub(r"[^a-z0-9\-]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError("template name is empty after slugging")
    config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    p = config.TEMPLATES_DIR / f"{slug}.toml"
    if p.exists() and not overwrite:
        raise FileExistsError(f"template '{slug}' exists; pass overwrite")

    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

    lines = [f"name = {q(slug)}", f"title = {q(title or slug)}", f"description = {q(description)}",
             "tags = [" + ", ".join(q(t) for t in (tags or [])) + "]", f"kind = {q(kind)}", f"subject = {q(subject)}"]
    for k, v in (defaults or {}).items():
        lines.append(f"{k} = {q(str(v))}")
    body = prompt.strip().replace("'''", "'' '")
    lines.append("prompt = '''\n" + body + "\n'''")
    for k, spec in (vars or {}).items():
        lines.append(f"\n[vars.{k}]")
        for sk, sv in spec.items():
            lines.append(f"{sk} = {q(str(sv)) if not isinstance(sv, bool) else str(sv).lower()}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _lookup(key: str, ctx: Dict[str, str]) -> str:
    return str(ctx.get(key, ""))


def substitute(text: str, ctx: Dict[str, str]) -> str:
    def sec(m: re.Match) -> str:
        mode, key, inner = m.group(1), m.group(2), m.group(3)
        val = _lookup(key, ctx).strip()
        show = bool(val) if mode == "#" else not val
        return substitute(inner, ctx) if show else ""

    prev = None
    while prev != text:
        prev = text
        text = _SECTION.sub(sec, text)
    return _VAR.sub(lambda m: _lookup(m.group(1), ctx), text)


def build_context(tpl: Optional[Template], user_vars: Dict[str, str], brand: Optional[Brand]) -> Dict[str, str]:
    ctx: Dict[str, str] = {}
    if brand:
        for k, v in brand.flat().items():
            ctx[f"brand.{k}"] = v
    ctx["today"] = _dt.date.today().isoformat()
    if tpl:
        for k, spec in tpl.vars.items():
            ctx[k] = str(spec.get("default", ""))
    for k, v in user_vars.items():
        ctx[k] = str(v)
    # resolve brand refs inside defaults (e.g. default = "{{brand.style}}")
    for _ in range(3):
        for k, v in list(ctx.items()):
            if "{{" in v:
                ctx[k] = substitute(v, ctx)
    ctx["headline_block"] = craft.headline_block(ctx.get("headline", ""), ctx.get("headline_type") or
                                                 "tall bold uppercase sans-serif lettering")
    ctx["single_subject"] = craft.single_subject_clause()
    subject = (tpl.subject if tpl else ctx.get("subject", "none")) or "none"
    ctx["avoid"] = craft.avoid_clause(subject)
    return ctx


def render_prompt(tpl: Optional[Template], user_vars: Dict[str, str], brand: Optional[Brand],
                  raw_prompt: str = "", extra_avoid: List[str] | None = None) -> Tuple[str, Dict[str, str], List[str]]:
    """Return (final_prompt, context, missing_required_vars)."""
    ctx = build_context(tpl, user_vars, brand)
    missing: List[str] = []
    if tpl:
        for k, spec in tpl.vars.items():
            if spec.get("required") and not ctx.get(k, "").strip():
                missing.append(k)
    source = raw_prompt.strip() if raw_prompt.strip() else (tpl.prompt if tpl else "")
    text = substitute(source, ctx)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    want_avoid = (tpl.avoid if tpl else True) and "avoid:" not in text.lower()
    subject = (tpl.subject if tpl else user_vars.get("subject", "none")) or "none"
    clause = craft.avoid_clause(subject, extra_avoid)
    if want_avoid and clause and subject != "none":
        text = f"{text}\n{clause}"
    elif extra_avoid and "avoid:" in text.lower():
        text = f"{text} Also avoid: {', '.join(extra_avoid)}."
    return text, ctx, missing
