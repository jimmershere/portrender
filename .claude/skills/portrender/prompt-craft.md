# Prompt craft for GPT-image models (portrender edition)

Condensed from tee-empire `skills/image_craft/` (sources: EvoLinkAI/awesome-gpt-image-2,
wuyoscar/GPT-Image2-Skill, mikhail-bot/stable-diffusion-negative-prompts). `portrender/craft.py`
encodes the mechanical parts; this file is for the human/agent writing the *subject* lines.

## Shape (order matters — description budget is spent in reading order)

```
{canvas} {subject} {style} {composition} {headline_block} {avoid_clause}
```

- **canvas** first: "Print-ready t-shirt graphic isolated on a transparent background…"
- **subject**: one line, concrete nouns, one verb, one prop. "a smug cartoon hen in tie-dye overalls
  hugging a jar of jam" beats "a fun farm chicken design".
- **style**: narrow band from one era/medium — the brand TOML's `style` is already this.
  Never mix "vintage screenprint" with "8K cinematic render".
- **composition**: a structural anchor — centered chest-print · headline above/illustration below ·
  rule-of-thirds lower-right · badge/roundel · full-bleed.
- **headline**: exact words **in quotes** — `The headline reads exactly: "Do It Tired"`. Templates do this
  via `{{headline_block}}`. Never let the model paraphrase copy.
- **avoid**: appended automatically per `subject` (cartoon_mascot / humanoid / animal / typography_only / product).

## Day-to-day rules

1. One subject per design; templates add "single subject, no duplicates". Plural nouns invite sidekicks.
2. Transparent background (`--bg transparent`) for anything that goes on a product; opaque for posters/socials.
3. `1024x1024` for chest prints and stickers, `1536x1024` for mug wraps / model sheets, `1024x1536` for bottles/posters.
4. Explore at `--quality low -n 2`; commit at `high`/`xhigh` with `-n 1`. `max` only for the final master.
5. For edits, always keep the guard clause ("Preserve the existing typography, palette and composition") unless
   the point *is* a restyle. Use `--fidelity high` when the source must stay recognisable (mascots, logos).
6. Character consistency: render a `mascot-sheet`, approve it, set `brand.mascot.ref`, then pass it as `--ref`
   to edits (`portrender edit product-shot-JOB:1 --ref maddhatch-sheet-JOB:1 -t edit-place-art`).
7. Three rounds max on one idea before changing the prompt, not the seed.
8. For complex multi-system shots, write the prompt as a labelled JSON config block (CANVAS / STYLE /
   SUBJECT / HEADLINE / COMPOSITION / AVOID) — models follow schemas better than 600-char paragraphs.

## Per-brand cheat sheet

| brand | subject vocabulary | headline type | palette rule |
|---|---|---|---|
| maddhatch | hens, chicks, jam jars, Trish (curly red hair, glasses, headset, tie-dye), possums, porch goblins | chunky rounded uppercase | teal/plum logo colors + amber, cream base |
| au2 | calipers, panel gaps, the SS, cooler, open toolbox, chrome, pace car | Oswald-style condensed uppercase | red + chrome on near-black |
| icenstone | Mitten/U.P. silhouettes, ice shelf, Petoskey stone, split firewood, lighthouse | stencil / condensed grotesque | monochrome + one ice-blue accent |
| earl_biggers | typographic, deadpan, "*" asterisk gags | tall bold uppercase sans | white/one accent on black |
