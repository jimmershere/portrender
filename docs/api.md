# portrender JSON API

Served by `portrender serve` (default `127.0.0.1:3070`). Same-origin, no auth. Every route
has a CLI twin in `portrender/cli.py`. Errors are `{"error": "…"}` with 4xx/5xx.

| method | route | body / query | returns |
|---|---|---|---|
| GET | `/healthz` | | `{ok, version, running[]}` |
| GET | `/api/state` | | config (non-secret), brands, templates, models/qualities/sizes/backgrounds/subjects, export_targets, running, costs, refs |
| GET | `/api/jobs` | `status, brand, limit, pending=1, starred=1, image_status, q` | `[summary]` |
| GET | `/api/jobs/<id>` | | full manifest + `log` + `running` |
| GET | `/api/jobs/<id>/log` | `n` | `{log, running}` |
| GET | `/files/<id>/<file>` · `/files/<id>/thumbs/<file>` | | image bytes |
| GET | `/refs/<name>` | | uploaded reference image |
| POST | `/api/prompt` | `{prompt?, template?, brand?, vars{}, subject?, avoid?, allow_missing?}` | `{prompt, params, vars}` — preview only |
| POST | `/api/render` | prompt fields + `n, size, quality, model, background, format, label, notes, tags[]` | `{job}` (queued; poll) |
| POST | `/api/edit` | `{source:"JOB:N"\|"ref:NAME"\|path, refs[], prompt, template?, brand?, vars{}, n, size, quality, model, background, fidelity, no_preserve, label}` | `{job}` |
| POST | `/api/review` | `{job, image\|images[], action, note?}` — action ∈ approve/approved, reject/rejected, pending, star, unstar, toggle-star, reset, note | `{job}` |
| POST | `/api/notes` | `{job, notes, tags[]}` | `{job}` |
| POST | `/api/export` | `{job, images[], to, slug?, force?, …}` — tee-empire: `text, placement, font, color, prompt`; clemtock: `category`; dir: `dir` | `{results[], job}` |
| POST | `/api/templates` | `{name, title, prompt, description, tags[], kind, subject, defaults{}, vars{}, overwrite}` | `{path, templates[]}` |
| POST | `/api/upload` | `{name, data_b64}` (data URL ok) | `{ref, path}` |
| POST | `/api/rerun` | `{job}` | `{job}` |
| POST | `/api/delete` | `{jobs[]}` | `{deleted[]}` |

`summary` = `{id, status, kind, brand, template, label, created, n, approved, rejected, starred,
model, size, quality, cost_estimate, parent, error, prompt, images[]}`; `images[i]` =
`{file, thumb, size_px, bytes, status, starred, note, revised_prompt, exports[]}`.

Example — render, wait, approve, export:

```bash
H='content-type: application/json'; B=http://127.0.0.1:3070
J=$(curl -s -X POST $B/api/render -H "$H" -d '{"template":"sticker","brand":"au2","vars":{"subject_desc":"chrome calipers gripping a wrench","headline":"Panel Gaps Crew"},"n":2}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["job"]["id"])')
until curl -s $B/api/jobs/$J | grep -q '"status": "done"'; do sleep 3; done
curl -s -X POST $B/api/review -H "$H" -d "{\"job\":\"$J\",\"image\":\"01.png\",\"action\":\"approve\"}"
curl -s -X POST $B/api/export -H "$H" -d "{\"job\":\"$J\",\"images\":[\"1\"],\"to\":\"tee-empire\",\"text\":\"EST. 2024\"}"
```
