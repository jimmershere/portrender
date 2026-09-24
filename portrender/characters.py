"""The character roster — reusable people/mascots that appear across many designs.

A *brand* is facts (voice, palette, shop ids). A *character* is a face: art plus the
derived pieces needed to make it talk. Jimmer shows up in Appearance Unlimited work and
Ice & Stone work alike, and every new customer arrives with one of their own, so the
roster is keyed on the character rather than nested under a single brand.

A character lives in ``brands/<slug>/`` (gitignored — art is private, PR-5):

    character.png      the artwork.                                  required
    character.json     geometry: mouth position, written by
                       clemtock's sprites-from-character.py          optional
    mouths/A..X.png    sprite set for the free local lip-sync        optional
    heygen.json        cached talking_photo_id for HeyGen            optional
    voice.json         {"voice_id": …} for HeyGen, or a reference
                       WAV path for a local Chatterbox clone         optional

Nothing here talks to an API or costs anything — it reads the directory and reports what
each character can currently do. "Can this character be rendered right now, and by which
engine" is a question the UI asks constantly, so it has to be cheap.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

IMAGE_NAMES = ("character.png", "character.jpg", "character.jpeg", "character.webp")
MOUTH_SHAPES = tuple("ABCDEFGHX")
# A-F is a complete mouth; G/H/X are polish and degrade to the nearest shape.
MOUTH_REQUIRED = tuple("ABCDEF")


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@dataclass
class Character:
    slug: str
    dir: Path
    image: Optional[Path] = None
    geometry: Dict[str, Any] = field(default_factory=dict)
    mouths: List[str] = field(default_factory=list)
    heygen: Dict[str, Any] = field(default_factory=dict)
    voice: Dict[str, Any] = field(default_factory=dict)

    # ---------- capability ----------
    @property
    def name(self) -> str:
        return str(self.geometry.get("name") or self.slug.replace("_", " ").replace("-", " ").title())

    @property
    def has_art(self) -> bool:
        return self.image is not None

    @property
    def can_local(self) -> bool:
        """Free CPU lip-sync needs a usable sprite set."""
        return all(s in self.mouths for s in MOUTH_REQUIRED)

    @property
    def can_heygen(self) -> bool:
        """HeyGen needs art (the id is uploaded on demand) and a voice."""
        return self.has_art and bool(self.voice_id)

    @property
    def voice_id(self) -> str:
        return str(self.voice.get("voice_id") or "")

    @property
    def talking_photo_id(self) -> str:
        return str(self.heygen.get("talking_photo_id") or "")

    @property
    def engines(self) -> List[str]:
        out = []
        if self.can_heygen:
            out.append("heygen")
        if self.can_local:
            out.append("cartoon")
        return out

    @property
    def ready(self) -> bool:
        return bool(self.engines)

    def blockers(self) -> List[str]:
        """Plain-English reasons this character cannot be rendered yet."""
        out: List[str] = []
        if not self.has_art:
            out.append(f"no artwork — put one at {self.dir / 'character.png'}")
            return out
        if not self.can_local:
            missing = [s for s in MOUTH_REQUIRED if s not in self.mouths]
            out.append("no mouth sprites for local render (missing "
                       + ", ".join(f"{m}.png" for m in missing)
                       + ") — run clemtock's sprites-from-character.py")
        if not self.voice_id:
            out.append("no voice — add {\"voice_id\": \"…\"} to "
                       f"{self.dir / 'voice.json'} (list them with clemtock)")
        return out

    def summary(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "dir": str(self.dir),
            "has_art": self.has_art,
            "image": str(self.image) if self.image else None,
            "mouths": self.mouths,
            "mouth_count": len(self.mouths),
            "can_local": self.can_local,
            "can_heygen": self.can_heygen,
            "voice_id": self.voice_id,
            "talking_photo_id": self.talking_photo_id,
            "engines": self.engines,
            "ready": self.ready,
            "blockers": self.blockers(),
        }


def load(slug: str, brands_dir: Optional[Path] = None) -> Character:
    root = (brands_dir or config.BRANDS_DIR) / slug
    img = next((root / n for n in IMAGE_NAMES if (root / n).is_file()), None)
    mouths_dir = root / "mouths"
    mouths = ([s for s in MOUTH_SHAPES
               if any((mouths_dir / f"{s}{e}").is_file()
                      for e in (".png", ".webp", ".jpg", ".jpeg"))]
              if mouths_dir.is_dir() else [])
    return Character(
        slug=slug, dir=root, image=img,
        geometry=_read_json(root / "character.json"),
        mouths=mouths,
        heygen=_read_json(root / "heygen.json"),
        voice=_read_json(root / "voice.json"),
    )


def roster(brands_dir: Optional[Path] = None) -> List[Character]:
    """Every character directory that holds artwork, ready ones first."""
    root = brands_dir or config.BRANDS_DIR
    if not root.is_dir():
        return []
    chars = [load(d.name, root) for d in sorted(root.iterdir()) if d.is_dir()]
    chars = [c for c in chars if c.has_art]
    return sorted(chars, key=lambda c: (not c.ready, c.slug))
