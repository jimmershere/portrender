# Setup status — 2026-09-23 (pop-os + quasimodo)

What is actually configured and verified, and what is still blocked. Supersedes
the "State right now" section of [`HANDOFF.md`](HANDOFF.md), which was written
before any of this ran.

## Verified working

| Thing | Evidence |
|---|---|
| portrender tests | 17/17 pass on pop-os **and** on quasimodo |
| `scripts/smoke.sh` | `smoke: OK` (no-network end-to-end) |
| OpenAI key | `doctor --probe` → `{"ok": true}`; `GET /v1/models` → 200 |
| portrender on pop-os | `http://127.0.0.1:3070` — `scripts/serve.sh start/stop/status` |
| portrender on quasimodo | `http://192.168.0.20:3070` — systemd **user** unit, `linger=yes`, enabled at boot |
| local81 deploy | `local81/portrender-deploy.yml`, lint-clean, applied 2026-09-23 |
| Printify | token live; shop `27415408` = *EarlBiggersDammit* (etsy channel), 113 products, 2646 blueprints readable |
| Etsy app auth | keystring + shared secret valid; `openapi-ping` → `{"application_id":1518422772535}` |
| Etsy shop id | resolved to **65833426** (`EarlBiggers`) via `findShops` |
| clemtock on pop-os | `http://127.0.0.1:3053`, reads the key chain (`ETSY_*`, `OPENAI_*`, `PRINTIFY_*` all resolve) |
| Export chain | `render --dry-run → approve → export --to tee-empire` drops PNG + `.empirespec.json` into `/app/tee-empire/inbox/` |

**Passwordless sudo is now configured on both hosts** (jimmer, 2026-09-23 — it
genuinely was not earlier in the session; `sudo -n` returned "a password is
required" on both). quasimodo's sudoers forbids `SETENV`, so
`sudo -n DEBIAN_FRONTEND=… apt-get` is refused there — drop the env var.

## Blocked — needs jimmer, not code

| # | Blocker | Effect | Fix |
|---|---|---|---|
| B-1 | **OpenAI account has no credits.** `POST /v1/images/generations` → 429 `credit_balance_exhausted`. The key itself is fine. | *Every* real render is impossible — portrender, and clemtock's stills. Only `--dry-run` works. | Add credits at platform.openai.com → billing |
| B-2 | No `ETSY_OAUTH_TOKEN` | Etsy draft listings / image upload cannot run. Printify drafts are unaffected. | `python3 /app/tee-empire/scripts/etsy_oauth.py` — needs a browser sign-in as the shop owner; cannot be automated |
| ~~B-3~~ | ~~`OPENROUTER_API_KEY` unset~~ | **RESOLVED 2026-09-23** — ollama v0.34.3 on pop-os with `qwen3:8b`; `providers/ollama_script.py` writes ad scripts locally in ~60-85s for $0. OpenRouter is now optional. | — |
| B-4 | `KIEAI_API_KEY` unset | no shorts, no video clips | fill `/app/clemtock/.env` |
| B-5 | `HEYGEN_API_KEY` unset | no spokesperson avatar / voice-over | fill `/app/clemtock/.env` |
| B-6 | `POST_BRIDGE_API_KEY` unset | no social posting | fill `/app/clemtock/.env` |
| ~~B-7~~ | ~~`node`/`npm` absent on quasimodo~~ | **PARTLY RESOLVED** — node 18.19.1, npm, chromium, python3-cryptography installed. See B-9. | — |
| ~~B-8~~ | ~~ImageMagick absent on pop-os~~ | **RESOLVED** — `imagemagick` + `python3.12-venv` installed. The thumbnailer now succeeds: 15 assets across characters, creatures, logos, mascots. `ensurepip` works, so venvs (and Chatterbox) are no longer gated. | — |
| B-9 | quasimodo has **node 18.19.1**; `playwright-core` declares `engines: node >=20` | clemtock's headless renderer may fail there. pop-os has node 22 and a faster CPU, so rendering belongs on pop-os anyway. | render on pop-os, or put node ≥20 on quasimodo (NodeSource is a third-party apt source, so it was **not** added unasked) |

Local / open-source replacements for B-1 and B-3…B-6 are researched in
[`local-ai-options.md`](local-ai-options.md). Short version: scripts, voice and
stills can all run free on pop-os; **text-to-video cannot** — neither host has a
discrete GPU.

So of the requested outputs: **merch design + characters + social stills** are
code-ready and blocked only on B-1; **ad scripts now work locally for free**;
**cartoon avatars with voice** need no GPU at all (see
[`render-pipeline.md`](../../clemtock/docs/render-pipeline.md)) and are blocked
only on building the Chatterbox + Rhubarb + ffmpeg chain, itself unblocked by
B-8; **b-roll video** goes to a rented vast.ai 4090 ($100 credit, ~$0.40/hr,
~250 GPU-hours); **social posting** still needs B-6.

## Bugs found and fixed

- **`/app/portrender/.env` held a bare `sk-proj-…` line with no `OPENAI_API_KEY=`.**
  Both `config._parse_env_file` and `scripts/load-env.sh` skip lines without `=`,
  so the key was never loaded by portrender *or* clemtock. It was also mode 664,
  not 600. Fixed both.
- **`scripts/serve.sh` (portrender *and* clemtock) wrote `$!` to the pidfile, but
  `setsid` forks** — the recorded pid was dead on arrival, so `start` reported
  failure while the server ran, and `stop`/`status`/`restart` all said "not
  running". Resolving the pid once at launch was still not enough (the server does
  not always settle on the pid visible a second later), so `running()` now trusts
  the pidfile only while it is live and otherwise re-resolves from the process
  table. Verified pidfile == the pid holding the listening socket on :3070 and
  :3053 across a full stop/start cycle.
- `core/etsy.py` sent `x-api-key: <keystring>`. This app is registered with a
  shared secret, so Etsy answers 403 *"Shared secret is required in x-api-key
  header."* until the header is `<keystring>:<shared_secret>`. Added
  `ETSY_SHARED_SECRET` + `EtsyClient.api_key_header`.
- `clemtock/scripts/probe-providers.sh` reported chromium MISSING while a
  playwright-managed chromium was installed and `CLEMTOCK_CHROMIUM` pointed at it.

## Corrections to standing docs

- **`local81` has no `plan`, `deploy` or `--scope`.** It is a playbook runner:
  `run` / `lint` / `hosts` over YAML. The `.local81/config.ini` "scope" format in
  this repo (and in clemtock and tee-empire) belongs to a tool that does not
  exist on either host. `scripts/deploy-quasimodo.sh` has a
  `command -v local81 && local81 plan --scope …` branch that would fail if
  local81 were ever put on PATH; it currently works only because it falls through
  to plain rsync. Use `local81/portrender-deploy.yml` instead.
- `/app/CLAUDE.md` says tee-empire is "not cloned on either host". It **is** at
  `/app/tee-empire` on pop-os, configured, with 113 live Printify products. It is
  absent on quasimodo (so `doctor` there reports `tee_empire_present: false`,
  which is correct, not a fault).

## Not touched — open questions, ask before acting

- **TE-10 / `floor2`.** `/app/tee-empire/.local81/config.ini` still points
  `rsync --delete` at `floor2:/home/floor2/tee-empire` (192.168.1.206), a host in
  no workspace doc and not part of the pop-os + quasimodo fleet. 16 `.206`
  references remain in tee-empire's Python. `empire drop` pushes to Mission
  Control on `.206` **by default** — pass `--no-publish`, or use the local gate
  (`core/local_approval.py`), until TE-10 is answered.
- **Creating a Printify draft has not been exercised.** tee-empire's own
  constraint allows drafts ("creating a draft is fine; `publish_product()` is
  not"), but nothing was written to the shop without a go-ahead. The gate is
  `--live`: every orchestrator path is `dry_run=not args.live`.
- PR-2 (who owns canonical `data/renders`) is unanswered; the deploy playbook
  excludes `data/` on both sides, so each host currently keeps its own.
- `/app/clemtock` still has ~19 uncommitted modified files from the previous
  session (HANDOFF step 4). Not committed here — read the diff first.
