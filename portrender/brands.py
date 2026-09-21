"""Brand configs: ``brands/<slug>.toml`` (+ optional ``brands/<slug>/`` folder for
reference art). A brand is a bag of facts a template can interpolate as
``{{brand.field}}`` plus hand-off routing for the sibling ventures.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config


@dataclass
class Brand:
    slug: str
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    path: Optional[Path] = None

    @property
    def dir(self) -> Path:
        return (self.path.parent / self.slug) if self.path else config.BRANDS_DIR / self.slug

    def get(self, key: str, default: Any = "") -> Any:
        cur: Any = self.data
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def flat(self) -> Dict[str, str]:
        """Template-facing view: every scalar/list flattened to a string."""
        out: Dict[str, str] = {"slug": self.slug, "name": self.name}

        def walk(prefix: str, obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    walk(f"{prefix}{k}.", v) if isinstance(v, dict) else walk(f"{prefix}{k}", v)
            elif isinstance(obj, list):
                out[prefix] = ", ".join(str(x) for x in obj)
            elif obj is None:
                out[prefix] = ""
            else:
                out[prefix] = str(obj)

        walk("", self.data)
        return out

    def reference_images(self) -> List[Path]:
        refs: List[Path] = []
        for key in ("mascot.ref", "logo"):
            v = self.get(key)
            if v:
                p = Path(v)
                if not p.is_absolute():
                    p = (self.path.parent if self.path else config.BRANDS_DIR) / p
                if p.is_file():
                    refs.append(p)
        return refs

    def summary(self) -> Dict[str, Any]:
        return {
            "slug": self.slug, "name": self.name,
            "tagline": self.get("tagline"), "voice": self.get("voice"), "style": self.get("style"),
            "palette": self.get("palette", []), "mascot": self.get("mascot", {}),
            "handoff": self.get("handoff", {}), "links": self.get("links", {}),
            "reference_images": [str(p) for p in self.reference_images()],
            "notes": self.get("notes"),
        }


def load(slug: str) -> Brand:
    p = config.BRANDS_DIR / f"{slug}.toml"
    if not p.is_file():
        raise FileNotFoundError(f"no brand '{slug}' at {p}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return Brand(slug=data.get("slug", slug), name=data.get("name", slug), data=data, path=p)


def list_brands() -> List[Brand]:
    out: List[Brand] = []
    if not config.BRANDS_DIR.is_dir():
        return out
    for p in sorted(config.BRANDS_DIR.glob("*.toml")):
        try:
            out.append(load(p.stem))
        except Exception as e:  # noqa: BLE001
            out.append(Brand(slug=p.stem, name=f"{p.stem} (broken: {e})", data={}, path=p))
    return out
