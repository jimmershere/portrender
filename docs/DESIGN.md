# portrender — design

## Goal

One operator (jimmer), many brands, lots of images. The expensive step is a network call
that costs money per image; the scarce resource is his attention. So the tool optimises
three things: **prompts that don't waste renders**, **review that takes a keystroke**, and
**hand-off that is a file copy** the downstream tool already understands.

## Principles (inherited from /app and clemtock)

- **Stdlib-first.** `urllib` for the API, `ThreadingHTTPServer` for the UI, `tomllib` for
  configs. pop-os has no pip; quasimodo's Python is unverified. Pillow is opportunistic.
- **Operator-readable artifacts.** Every job is a directory with `render.json`,
  `prompt.txt` and the PNGs. `grep`, `ls`, `rm -r` are valid admin tools.
- **Human ↔ agent parity.** Every button in the UI is a subcommand and a JSON route. Claude
  Code drives it through `.claude/skills/portrender`; jimmer drives it through the browser.
- **Honesty over magic.** Unverified facts are labelled (CLAUDE.md "Facts verified vs. assumed").
  Dry-run mode writes placeholders; it never pretends a render happened.
- **Nothing publishes.** Exports are local drops. Printify/Etsy/social remain behind
  tee-empire's `--live` and clemtock's `--execute`.

## Pipeline

```
brands/<slug>.toml ─┐
prompts/templates/<t>.toml ─┼─▶ prompts.render_prompt() ─▶ final prompt (+Avoid clause)
--var k=v / UI form ────────┘                                   │
                                                                ▼
                       jobs.create() → data/renders/<id>/render.json (queued)
                                                                │
      CLI: jobs.run() in-process     UI: subprocess `portrender run <id>`
                                                                ▼
                openai_images.generate() | edit()  ──▶ 01.png … + usage + cost estimate
                                                                ▼
                 review: approve / reject / star / note   (CLI or UI, optimistic, keyboard)
                                                                ▼
                 export.to_tee_empire() | to_clemtock() | to_au2() | to_dir()
```

### Job manifest (`render.json`)

```jsonc
{
  "id": "20260921-105452-need-some-eggs", "created": "…", "status": "done",   // queued|running|done|error
  "kind": "generate",                    // or "edit" (then: parent {job,image}, sources[], mask, input_fidelity)
  "label": "Need Some Eggs?", "brand": "maddhatch", "template": "tee-graphic", "vars": {…},
  "prompt": "…exact text sent…", "model": "gpt-image-2", "n": 2, "size": "1024x1024",
  "quality": "medium", "background": "transparent", "output_format": "png",
  "images": [{"file": "01.png", "thumb": "thumbs/01.png", "size_px": [1024,1024], "bytes": 812345,
              "status": "approved", "starred": true, "note": "keeper", "revised_prompt": null,
              "exports": [{"target": "tee-empire", "path": "/app/tee-empire/inbox/need-some-eggs-01.png", "at": "…"}]}],
  "usage": {"input_tokens": …, "output_tokens": …}, "cost_estimate": 0.14, "elapsed_s": 21.3,
  "error": null, "notes": "", "tags": []
}
```

Lineage: an edit job carries `parent: {job, image}`; the UI shows "↳ from JOB:img". Nothing is
ever overwritten — every edit is a new job, so the whole tree is reviewable.

### Prompt engine

Deliberately tiny mustache subset: `{{var}}`, `{{brand.x}}`, `{{#var}}…{{/var}}`,
`{{^var}}…{{/var}}`, builtins `headline_block`, `single_subject`, `avoid`, `today`. No
logic, no loops, no LLM. The Avoid clause (`craft.py`) is appended per `subject`; templates
opt out with `avoid = false`. Style anchors live in `craft.STYLE_ANCHORS` for prompt writers.

### Web server

`ThreadingHTTPServer`, JSON API, one static HTML file. Renders run as **subprocesses of the
CLI** (`portrender run <id> --json`) so a crash in a render can't take the server down and
the log of every job is a file. Polling, not websockets — 4 s while anything is running.

### Cost

`config.PRICE_TABLE` maps `model|quality → USD/image`. **Placeholder numbers.** The API returns
token usage (`usage.input_tokens/output_tokens`) which is stored verbatim; once real invoices
exist, replace the table (or set `PORTRENDER_PRICE_JSON`) and the spend counter becomes honest.

### Where it runs

- **pop-os**: git checkout, `portrender serve` on 127.0.0.1 for local work.
- **quasimodo**: `local81 deploy --scope portrender` target; `serve --host 0.0.0.0` (or the
  systemd user unit) → http://192.168.0.20:3070 from pop-os. See `quasimodo.md`.
- No GPU, no local model. Any box with Python 3.11+ and outbound HTTPS to api.openai.com works.

## Integration contracts

| target | what we write | what happens next (their side) |
|---|---|---|
| tee-empire | `inbox/<slug>.png` + `<slug>.empirespec.json` `{prompt,text,font,color,placement,brand,portrender{…}}` | `empire drop [--brand] [--live]` fans out to Printify **drafts**; `mc-poll --live` publishes only on approval |
| clemtock | `assets/<category>/<slug>.png`; `POST /api/rescan` if the studio is up | library rebuild; asset appears as hero/character/logo in recipes |
| AU2 | `assets/img/merch/masters/<slug>.png` (gitignore in au2) | human adds the design to `products.json`, derives web sizes, `build-merch.py` |
| dir | `<dir>/<slug>.png` | anything |

## Not in scope (yet)

- Other image providers (kie.ai, FLUX via OpenRouter, ComfyUI). tee-empire has them; if portrender
  needs a second backend, add `providers/` with the same `generate/edit` signature — not before.
- Automatic judging / scoring. tee-empire's `judge.py` calls Anthropic from app code (TE-4);
  portrender leaves judging to Claude Code reading the PNGs, or to jimmer.
- Multi-user, auth, remote access beyond the LAN.
