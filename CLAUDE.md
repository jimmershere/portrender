# CLAUDE.md — portrender (`/app/portrender`)

Image render → review → hand-off automation for the Portwright ventures, on the
OpenAI Images API ("ChatGPT Images"). Fleet context and constraints:
[`../CLAUDE.md`](../CLAUDE.md). Design: [`docs/DESIGN.md`](docs/DESIGN.md).
Running it on quasimodo: [`docs/quasimodo.md`](docs/quasimodo.md).
Agent workflow: [`.claude/skills/portrender/SKILL.md`](.claude/skills/portrender/SKILL.md).

## What is here

| | |
|---|---|
| Runtime | Python ≥ 3.11, **stdlib only** (pop-os has no pip). Pillow optional for thumbnails. |
| CLI | `python3 -m portrender …` — `render`, `edit`, `ls`, `approve/reject/star`, `export`, `serve`, `doctor` |
| Web UI | `portrender serve [--host 0.0.0.0] [--port 3070]` — LAN-only, no auth, keyboard-driven review |
| Prompts | `prompts/templates/*.toml` — 17 reusable templates; brand facts in `brands/*.toml` |
| Brands | `maddhatch`, `au2`, `icenstone`, `earl_biggers` |
| State | `data/renders/<job>/render.json` + PNGs. No database. `data/` is gitignored. |
| Tests | `python3 -m unittest discover -s tests -t .` (17, no network) · `scripts/smoke.sh` |
| Hand-offs | `export --to tee-empire` (inbox + `.empirespec.json`), `--to clemtock` (assets library), `--to au2` (merch masters), `--to dir` |

## Granted exception to fleet rule 1 — recorded, not hidden

Fleet rule 1 says no LLM/image API calls in application code. portrender's whole
job is calling `POST /v1/images/generations` and `/v1/images/edits`; jimmer asked
for exactly that on 2026-09-21 ("no restrictions related to integration with our
other products"). Scope of the exception: **the Images API only**. There is no LLM
call, no prompt-chain library, no agent loop in this repo — prompts are
deterministic templates, and the *thinking* happens in Claude Code via the skill.
If that ever changes, it is a design decision to raise, not a patch.

## Facts verified vs. assumed

- Model names (`gpt-image-2`, `gpt-image-2.5-sunburst`, `gpt-image-2.5-flare`, `gpt-image-1.5`,
  `gpt-image-1`, `gpt-image-1-mini`, `chatgpt-image-latest`) and parameters (`quality` low→max,
  custom sizes ÷16, `background=transparent`, `input_fidelity`) — **read from the OpenAI API
  reference on 2026-09-21**. Not exercised live: no key in the build sandbox.
- **Prices in `config.PRICE_TABLE` are placeholders.** The UI's spend counter is an estimate. Fix
  the table (or `PORTRENDER_PRICE_JSON`) after the first real invoice.
- `/images/edits` is sent as multipart `image[]` — the shape gpt-image-1 accepted and tee-empire
  uses today. The reference now also documents a JSON `images:[{image_url}]` form; if multipart
  is ever rejected, switch `openai_images.edit` to that.
- Brand facts come from the maddhatch / au2 GitHub repos and tee-empire's `brand.yaml`s, cited in
  each TOML. `icenstone.grok.me` returned 403, so that brand is jimmer's brief only.
- The tee-empire sidecar fields (`prompt,text,font,color,placement`) were read from
  `core/ingest.py`; the extra `portrender`/`brand` keys are ignored by tee-empire today.

## Constraints (inherited — non-negotiable)

- **Nothing here publishes.** Exports are local file drops; Printify/Etsy/social stay behind
  tee-empire's and clemtock's own gates. Never add a `publish` verb to this repo.
- No auth, no multi-user, no Docker/k8s. `scripts/serve.sh` + a systemd *user* unit is the ceiling.
- Secrets only via env / `/app/portrender/.env` (the OpenAI key lives here, shared with clemtock) / `/app/tee-empire/.env`; `.env` is gitignored and excluded from the local81 push; a key in history is an incident.
- The fleet is **pop-os + quasimodo only**. There is no other render host; anything that names one is stale.
- Keep this file under 200 lines; put detail in `docs/`.

## Open questions — do not guess

| # | Question |
|---|---|
| PR-1 | Which model/quality is the house default once real cost data exists? (`PORTRENDER_MODEL`, `PRICE_TABLE`) |
| PR-2 | Does quasimodo hold the canonical `data/renders`, or does each host keep its own? (local81 scope excludes `data/` either way) |
| PR-3 | Should `au2` / `icenstone` become tee-empire brands (`scripts/onboard_brand.py`), so `--to tee-empire` routes to a real shop? |
| PR-4 | Publish this repo to GitHub (`jimmershere/portrender`)? Add it to `poplab/local81/playbooks/repo-sync.yml` only after `repo-guard.sh` passes. |
| PR-5 | Reference-image edits for mascot consistency need `brands/<slug>/` art checked in — is that OK for a public repo, or keep refs under `data/refs/`? |
