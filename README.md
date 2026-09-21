# portrender

**Render → review → hand off.** A one-operator tool that turns a brand-aware prompt into
artwork via the OpenAI Images API (ChatGPT Images), lets you approve / reject / edit the
results in seconds from a terminal or a LAN web UI, and drops the keepers into the sibling
Portwright tools — **tee-empire** (Printify drafts → Etsy), **clemtock** (social ads) and the
**AU2** site — without ever publishing anything itself.

Built for the fleet in `/app`: stdlib-only Python (no pip needed on pop-os), the same
checkout runs on pop-os and quasimodo, state is plain files, human gate before anything
leaves the machine.

```
prompt template + brand ──▶ OpenAI Images API ──▶ data/renders/<job>/*.png
                                                        │
                       terminal (portrender ls/approve) │ web UI (a/x/s/e/v/t keys)
                                                        ▼
                     approved ──▶ tee-empire inbox ──▶ Printify DRAFT ──▶ (human) Etsy
                              ──▶ clemtock assets/ ──▶ ad scenes
                              ──▶ AU2 merch masters ──▶ products.json (human)
```

## Quick start

```bash
cd /app/portrender
cp .env.example .env && chmod 600 .env      # add OPENAI_API_KEY — or skip: /app/tee-empire/.env is read as a fallback
python3 -m portrender doctor --probe        # config, key, sibling ventures, auth-only API check

python3 -m portrender brands                # maddhatch · au2 · icenstone · earl_biggers
python3 -m portrender templates             # 17 reusable prompts (tee-graphic, sticker, mascot-sheet, …)

# preview the exact prompt (free), then render (costs money)
python3 -m portrender prompt -t tee-graphic -b maddhatch --var subject_desc="a smug cartoon hen in tie-dye overalls hugging a jar of jam" --var headline="Need Some Eggs?"
python3 -m portrender render -t tee-graphic -b maddhatch --var subject_desc="…" --var headline="Need Some Eggs?" -n 2 --quality low

# review from the terminal …
python3 -m portrender ls --pending
python3 -m portrender approve 20260921-105452-need-some-eggs 1 --note "keeper"
python3 -m portrender edit 20260921-105452-need-some-eggs:1 -p "make the hen wink" --fidelity high

# … or from the browser
python3 -m portrender serve                 # http://127.0.0.1:3070  (quasimodo: --host 0.0.0.0)

# hand off (local file drops only — publishing stays gated in the target tool)
python3 -m portrender export JOB 1 --to tee-empire --text "EST. 2024" --placement back
python3 -m portrender export JOB 1 --to clemtock --category mascots
python3 -m portrender export JOB 1 --to au2
```

No key yet? Everything works with `--dry-run` (placeholder PNGs): `portrender render -p "test" --dry-run`, `portrender serve --dry-run`.

## The web UI

Three panes: **Render** (brand, template with auto-built variable inputs, params, preview,
save-as-template, reference uploads) · **Gallery** (jobs newest first, filters, live polling,
spend counter) · **Review lightbox** (checkerboard for transparent PNGs).

Keys: `j`/`k` next/prev image · `J`/`K` next/prev job · `a` approve · `x` reject · `p` pending ·
`s` star · `e` edit · `v` 4 variants · `t` export · `n` note · `/` search · `r` prompt · `?` help.
Approve/reject auto-advance to the next pending image. Everything the UI does is a CLI command
and a JSON endpoint (`docs/api.md`).

## Prompt library

`prompts/templates/*.toml`. A template is the canvas → subject → style → composition →
headline → avoid scaffold with `{{vars}}`; brand facts (`{{brand.style}}`, `{{brand.palette}}`,
`{{brand.voice}}`, mascot description) come from `brands/<slug>.toml`. Anatomy/text "Avoid:"
vocabulary is appended automatically per `subject`. Add templates with
`portrender templates new`, the UI's *Save as template*, or by hand — then commit them.

| template | for |
|---|---|
| `tee-graphic` `typography-tee` `sticker` `badge-patch` `mug-wrap` `bottle-label` `poster` | merch art |
| `character-concept` `mascot-sheet` | characters / mascots (model sheet → `brand.mascot.ref`) |
| `theme-board` | 2×2 directions for a new theme or drop |
| `logo-lockup` `product-shot` `social-square` | brand marks, listing/ad stills |
| `edit-refine` `edit-cleanup` `edit-restyle` `edit-place-art` | edits: instruction · fix anatomy/text · move into a brand style · put art on a product shot |

## Layout

```
portrender/            package (cli, server, web/index.html, openai_images, prompts, craft, brands, jobs, export, config)
prompts/templates/     the reusable prompt library (TOML)
brands/                brand facts (TOML) — maddhatch, au2, icenstone, earl_biggers
data/                  renders, job logs, uploaded refs (gitignored)
scripts/               serve.sh · load-env.sh · install-user-service.sh · smoke.sh
systemd/               user-unit template
.local81/              local81 scope: pop-os → quasimodo:/app/portrender (+ post-deploy hook)
.claude/skills/        the Claude Code skill that drives this tool
docs/                  DESIGN.md · api.md · quasimodo.md
tests/                 unittest, no network
```

## Fleet

Code of record is this git repo (pop-os). `local81 plan --scope portrender && local81 deploy --latest --scope portrender`
pushes to `quasimodo:/app/portrender` (excludes `data/`, `.env`, `.git`). See `docs/quasimodo.md` for
the first run there and the systemd user service. Renders stay on whichever host made them (PR-2).
