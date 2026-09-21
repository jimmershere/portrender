"""Prompt-craft rules shared by every template.

Distilled from tee-empire's ``skills/image_craft`` (itself vendored from
EvoLinkAI/awesome-gpt-image-2, wuyoscar/GPT-Image2-Skill and
mikhail-bot/stable-diffusion-negative-prompts). Kept as plain data so the
web UI, the CLI and the Claude Code skill all apply the same clauses.

The canonical prompt shape is::

    {canvas} {subject} {style} {composition} {headline_block} {avoid_clause}

Order matters — the model allocates description budget in reading order.
"""
from __future__ import annotations

from typing import Dict, List

AVOID: Dict[str, List[str]] = {
    "cartoon_mascot": [
        "extra limbs", "missing limbs", "fused limbs", "extra arms", "extra legs",
        "six fingers", "fused fingers", "mutated hand", "malformed face", "mirrored face",
        "doubled face", "two heads", "off-model anatomy", "broken silhouette",
        "floating limb", "cluttered background", "extra characters", "duplicate of the subject",
    ],
    "humanoid": [
        "extra fingers", "six fingers", "fused fingers", "mutated hand", "poorly drawn hand",
        "missing thumb", "extra elbow", "extra knee", "three legs", "missing limb",
        "floating limb", "bad anatomy", "gross proportions", "long neck", "mirrored face",
        "cloned face", "two heads", "distorted face", "asymmetric eyes", "deformed mouth",
    ],
    "animal": [
        "wrong number of legs", "three legs", "five legs", "extra tail", "two tails",
        "missing ear", "three ears", "extra eye", "three eyes", "mirrored eyes",
        "deformed paw", "malformed snout", "broken silhouette", "off-model anatomy",
    ],
    "typography_only": [
        "no people", "no faces", "no hands", "no animals", "no characters",
        "no random objects", "garbled text", "duplicated text", "misspelled headline",
        "extra characters in the text",
    ],
    "product": [
        "warped product silhouette", "impossible geometry", "floating parts",
        "melted edges", "duplicate product", "cluttered background",
    ],
    "none": [],
}

UNIVERSAL: List[str] = [
    "watermark", "signature", "artist mark", "copyright mark", "stock-photo overlay",
    "caption text outside the headline", "QR code", "jpeg compression artifacts",
    "blurry edges",
]

SUBJECTS = list(AVOID.keys())

STYLE_ANCHORS: Dict[str, str] = {
    "screenprint": "vintage screenprint, 2-color, ink-bleed texture, hand-drawn line art, 1960s comic-book aesthetic",
    "sticker": "bold cartoon sticker-style art, thick uniform outlines, bright flat color, subtle cel shading",
    "chrome": "1970s motorsport chrome lettering, dark garage backdrop, red-and-chrome palette, airbrushed highlights",
    "woodcut": "rough linocut / woodcut print, single ink color, heavy grain, folk-art proportions",
    "badge": "circular badge / patch design, thick border ring, banner ribbon, limited palette, embroidered look",
    "cold-forged": "stark monochrome with one ice-blue accent, hard edges, weathered metal and stone texture, hand-cut stencil lettering",
    "flat-vector": "clean flat vector illustration, geometric shapes, no gradients, 4-color palette",
    "photoreal-product": "photorealistic product render, softbox studio lighting, neutral seamless backdrop",
}


def avoid_clause(subject: str, extra: List[str] | None = None) -> str:
    terms: List[str] = []
    for t in AVOID.get(subject, []) + UNIVERSAL + list(extra or []):
        if t not in terms:
            terms.append(t)
    return "Avoid: " + ", ".join(terms) + "." if terms else ""


def headline_block(text: str, typography: str = "tall bold uppercase sans-serif lettering") -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return f'The headline reads exactly: "{text}" in {typography}. Spell it exactly, once.'


def single_subject_clause() -> str:
    return "single subject, no duplicates, no extra characters;"
