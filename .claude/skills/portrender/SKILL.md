---
name: portrender
description: Drive portrender (Portwright image render/review/hand-off) from Claude Code — compose brand-aware prompts, render via the OpenAI Images API, review with the operator, iterate with edits, and hand approved art to tee-empire / clemtock / AU2. Use for any merch, character, theme or social-still artwork for Madd Hatchery, Appearance Unlimited, Ice and Stone or Earl Biggers.
---

# portrender skill

portrender lives at `/app/portrender` (git repo; same path on pop-os and quasimodo).
Everything below is `python3 -m portrender …` (or `portrender …` if installed with pip -e).
Run from the repo root so `prompts/` and `brands/` resolve.

## When to use

- jimmer asks for merch art, a character/mascot, a theme/collection board, a logo,
  a sticker, a mug wrap, a social still — for **maddhatch, au2, icenstone, earl_biggers**.
- jimmer wants to expand the reusable prompt library, or onboard a new brand.
- jimmer wants a batch of variations reviewed and the good ones pushed onward.

## The loop (human in the loop, always)

1. **Pick brand + template.** `portrender templates` · `portrender brands`.
   Free-form prompts are fine (`-p`), but prefer a template so the canvas → subject →
   style → composition → headline → avoid scaffold is applied (see prompt-craft.md).
2. **Preview before spending:** `portrender prompt -t tee-graphic -b maddhatch --var subject_desc="…" --var headline="…"`
   Read the final prompt back to jimmer if it is his first render on this idea.
3. **Render small first:** `-n 2 --quality low` for exploration, then `--quality high` / `xhigh` for the keeper.
   Each call costs money; never fan out more than `-n 4` without asking.
4. **Review is jimmer's call.** Point him at the UI (`http://<host>:3070`, keys a/x/s/e/v/t) or
   run `portrender ls --pending` and let him say which to approve. Do not approve on his behalf.
   You *may* describe images to him (Read the PNG) and recommend.
5. **Iterate with edits, not re-rolls:** `portrender edit JOB:2 -p "make the hen wink" --fidelity high`
   or `-t edit-cleanup` for anatomy/text fixes, `-t edit-restyle -b au2` to move art into a brand.
6. **Hand off only approved images:**
   - tee-empire (Printify drafts, still gated there): `portrender export JOB 1 --to tee-empire --text "EST. 2024" --placement back`
     then in `/app/tee-empire`: `python3 -m empire drop --brand <slug>` (dry-run) → `--live` creates **drafts** only.
   - clemtock ad library: `portrender export JOB 1 --to clemtock --category mascots`
   - AU2 merch masters: `portrender export JOB 1 --to au2`
   Nothing in portrender publishes to Etsy/Printify-live/social. Keep it that way.

## Expanding the prompt library

- `portrender templates new NAME --title "…" --prompt-file p.txt --subject cartoon_mascot --var subject_desc --var headline= --bg transparent`
  or POST `/api/templates`, or write `prompts/templates/NAME.toml` by hand (format in `portrender/prompts.py` docstring).
- Keep templates **brand-agnostic**: pull look-and-feel from `{{brand.style}}`, `{{brand.palette}}`, `{{brand.voice}}`.
- Every character/mascot/animal template must set `subject` so the Avoid clause is appended.
- Commit new templates: they are the product. `git add prompts/templates && git commit -m "prompts: add NAME"`.

## Onboarding a brand

1. `brands/<slug>.toml` — copy `brands/maddhatch.toml`; fill voice / style / palette / mascot / handoff from the
   customer's repo or site (cite where each fact came from in a comment). Unknown = leave blank, don't invent.
2. If the brand will sell via tee-empire: `python /app/tee-empire/scripts/onboard_brand.py intake.json` (its ONBOARDING.md).
3. First renders: `-t character-concept` → pick one → `-t mascot-sheet` → set `mascot.ref` to the approved sheet.

## Rules inherited from /app/CLAUDE.md

- portrender is the **one granted exception** to "no image/LLM API calls in app code": it calls the OpenAI
  Images API and nothing else. No LLM prompt-writing inside the app — *you* write prompts, from templates.
- No auth, localhost/LAN only, no deploy scaffolding beyond `scripts/` + the local81 scope.
- Every claim about a brand needs a source; uncertainty is stated in the TOML comments.
- Secrets: `OPENAI_API_KEY` from env / `.env` / `/app/tee-empire/.env`. Never print it, never commit it.

## Where things are

| | |
|---|---|
| CLI | `portrender/cli.py` — one subcommand per UI action |
| API + UI | `portrender/server.py`, `portrender/web/index.html` (`portrender serve`) |
| Prompt engine | `portrender/prompts.py` (+ `craft.py` avoid vocab, style anchors) |
| Renders | `data/renders/<job>/render.json` + PNGs — the only state |
| Fleet | `.local81/config.ini` scope → `quasimodo:/app/portrender`; `docs/quasimodo.md` |
