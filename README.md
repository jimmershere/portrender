# portrender

> **New here?** Read [`/app/START-HERE.md`](../START-HERE.md) first — it covers all four
> tools in one page and tells you which one you want.

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

## Defaults

House default since 2026-09-23 (PR-1) is **`gpt-image-2.5-flare` at `quality=high`**, with
`gpt-image-2.5-sunburst` for edits. That is a deliberate "we have credit, spend it on
quality" choice — override per render with `--quality low` or per host in `.env`.

The spend counter in the UI is an **estimate from an unverified price table**. Correct
`PRICE_TABLE` (or set `PORTRENDER_PRICE_JSON`) once you have a real invoice.

## Quick start

```bash
cd /app/portrender
bash scripts/bootstrap-repo.sh              # first time only: restores .git history + .claude/skills from portrender.bundle
cp .env.example .env && chmod 600 .env      # OPENAI_API_KEY lives here (shared with clemtock); /app/tee-empire/.env is the fallback
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
| `character-concept` `mascot-sheet` | characters / mascots (model sheet → `brand.mascot.ref`; also how you draw the A–F mouth set clemtock needs for talking avatars) |
| `theme-board` | 2×2 directions for a new theme or drop |
| `logo-lockup` `product-shot` `social-square` | brand marks, listing/ad stills |
| `edit-refine` `edit-cleanup` `edit-restyle` `edit-place-art` | edits: instruction · fix anatomy/text · move into a brand style · put art on a product shot |

## Layout

```
portrender/            package (cli, server, web/index.html, openai_images, prompts, craft, brands, jobs, export, config)
prompts/templates/     the reusable prompt library (TOML)
brands/<slug>.toml     brand FACTS — voice, palette, lanes. Public, in git.
brands/<slug>/         brand ART — mascot sheets, refs, mouth sprite sets.
                       GITIGNORED and private (PR-5/PR-10): this repo is public.
data/                  renders, job logs, uploaded refs (gitignored)
scripts/               serve.sh · load-env.sh · install-user-service.sh · deploy-quasimodo.sh · smoke.sh
systemd/               user-unit template
.local81/              local81 scope: pop-os → quasimodo:/app/portrender (+ post-deploy hook)
.claude/skills/        the Claude Code skill that drives this tool
docs/                  SETUP-STATUS.md (what works / what's blocked) · DESIGN.md · api.md
                       quasimodo.md · local-ai-options.md
tests/                 unittest, no network
```

## Fleet

Code of record is this git repo (pop-os), published at
<https://github.com/jimmershere/portrender>. To copy it to quasimodo:

```bash
/app/poplab/bin/local81 run local81/portrender-deploy.yml            # dry run — read this
/app/poplab/bin/local81 run local81/portrender-deploy.yml --apply    # do it
```

`.env` and `data/` are never synced. **`local81` has no `plan`/`deploy`/`--scope`
subcommands** — it is a playbook runner (`run`/`lint`/`hosts`); the `.local81/config.ini`
"scope" format here belongs to a tool that exists on neither host. `scripts/deploy-quasimodo.sh`
still contains that dead branch and works only because it falls through to plain rsync.

**quasimodo is canonical for `data/renders` (PR-2)** — it has more disk and Pillow. To make
pop-os see the same renders, run `scripts/setup-nfs-renders.sh` (it edits `/etc/exports` and
`/etc/fstab`, so read it first; `--check` reports without changing anything).
