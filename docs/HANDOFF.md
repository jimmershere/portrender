# Handoff → Claude Code on pop-os (2026-09-23)

Everything this chat session decided lives in files, not in the chat. Open Claude Code in
`/app` (or `/app/portrender`) and it has the same context: `/app/CLAUDE.md` (fleet rules),
`/app/portrender/CLAUDE.md`, `.claude/skills/portrender/`, `docs/`, and the clemtock repo.

## State right now

- `/app/portrender` — git repo, 5 commits, clean after `bash scripts/bootstrap-repo.sh`
  (run it once more if `git log -1` is not `fleet is pop-os + quasimodo…`).
- `/app/clemtock` — your existing checkout with 19 files rewritten for quasimodo
  (**uncommitted**; `git status` / `git diff` show them). No floor2 references remain.
- OpenAI key: `/app/portrender/.env` (600). clemtock reads it too.
- Nothing has been run on quasimodo yet. Nothing has made a live render yet.

## What Claude Code should do first (in order)

1. `cd /app/portrender && python3 -m unittest discover -s tests -t . && bash scripts/smoke.sh`
2. `python3 -m portrender doctor --probe` — confirms the key with an auth-only call.
3. One cheap live render to validate the API shape (multipart edits especially):
   `python3 -m portrender render -p "a plain grey circle on transparent" --quality low -n 1 --bg transparent`
   then `python3 -m portrender edit <JOB>:1 -p "make it blue" -n 1`. If edits 4xx, switch
   `openai_images.edit()` to the JSON `images:[{image_url: data-url}]` form (CLAUDE.md, "Facts verified vs. assumed").
4. `cd /app/clemtock && git add -A && git commit -m "run on quasimodo: local env files, no floor2"` — after reading the diff.
5. `bash /app/portrender/scripts/deploy-quasimodo.sh` — pushes both repos, copies the key, starts services, curls :3070/:3053.
6. `ssh quasimodo 'cd /app/clemtock && bash scripts/quasimodo-setup.sh'` — apt + npm install + provider probe.
7. Fix whatever those print (quasimodo's Python version, ufw, linger, missing kie/HeyGen keys), then commit.

## Rules that still apply
Fleet constraints in `/app/CLAUDE.md`; portrender's Images-API exception is recorded in its CLAUDE.md.
Nothing publishes without a human. Never `rsync --delete` toward a host holding the only copy of data.
Open questions PR-1…PR-5 in `/app/portrender/CLAUDE.md` — ask, don't guess.
