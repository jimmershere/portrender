# Running portrender on quasimodo

quasimodo (192.168.0.20, user `jimbro`, `ssh quasimodo` / `quasimodo-lan` from pop-os)
is where the web UI should live so it is reachable from any machine on the LAN. pop-os
runs no sshd, so everything is pushed *to* quasimodo, never pulled from pop-os.

> Unverified at authoring time (built in a sandbox without SSH to the fleet): quasimodo's
> Python version, whether `systemctl --user` + linger are available, and whether outbound
> HTTPS to api.openai.com works from that box. Each step below prints what it found.

## 1. First deploy (from pop-os)

One command does portrender + clemtock + the key + services:

```bash
/app/portrender/scripts/deploy-quasimodo.sh
```

Step by step, if you prefer:

```bash
cd /app/portrender
local81 plan --scope portrender
local81 deploy --latest --scope portrender        # rsync -az --delete, excludes data/ .env .git
```

or, without local81:

```bash
rsync -az --delete --exclude .git --exclude data --exclude .env --exclude __pycache__ \
      /app/portrender/ quasimodo:/app/portrender/
```

Either way `data/` and `.env` on quasimodo are never touched.

## 2. First run (on quasimodo)

```bash
ssh quasimodo
cd /app/portrender
python3 --version                      # need ≥ 3.11 (tomllib). If older: python3.11/3.12 from the distro.
python3 -m portrender doctor           # shows env files, sibling ventures, key presence
```

Key: portrender reads `OPENAI_API_KEY` from env, then `/app/portrender/.env`, then
`/app/tee-empire/.env`. The key lives in `/app/portrender/.env` on pop-os (chmod 600); it is
**excluded from the local81 push**, so copy it to quasimodo once by hand:

```bash
scp /app/portrender/.env quasimodo:/app/portrender/.env && ssh quasimodo chmod 600 /app/portrender/.env
```

clemtock on the same host reads that same file (`config.load_env_files()`), so one key serves both.

```bash
python3 -m portrender doctor --probe   # auth-only call, no spend
python3 -m portrender render -p "smoke" --dry-run -n 1
```

## 3. Serve on the LAN

Quick:

```bash
scripts/serve.sh start --host 0.0.0.0 --port 3070     # nohup/setsid, pid in data/portrender.pid
scripts/serve.sh status
```

Persistent (survives logout once `sudo loginctl enable-linger jimbro` has been run):

```bash
loginctl show-user "$USER" -p Linger          # want Linger=yes; else: sudo loginctl enable-linger $USER
scripts/install-user-service.sh --host 0.0.0.0 --port 3070
systemctl --user status portrender
```

Open **http://192.168.0.20:3070** from pop-os. If nothing answers, check ufw / firewalld on
quasimodo for ports 3070 (portrender) and 3053 (clemtock).

## 4. Update loop

pop-os edits → `git commit` → `local81 deploy --scope portrender` → the post-deploy hook
(`.local81/hooks/post-deploy.sh`) restarts the user service and curls `/healthz`. If the
nested-ssh restart misbehaves (it did for clemtock), `ssh quasimodo systemctl --user restart portrender`.

## 5. clemtock next door

clemtock runs on quasimodo too (`/app/clemtock`, studio on :3053). Its setup is
`bash /app/clemtock/scripts/quasimodo-setup.sh` (ffmpeg, chromium, node, npm install, probe);
it reads the OpenAI key from `/app/portrender/.env`. portrender's `export --to clemtock`
drops PNGs into `/app/clemtock/assets/<category>/` and POSTs `/api/rescan`.

## 6. Where the renders live

Each host keeps its own `data/renders/` (PR-2 in CLAUDE.md). To bring quasimodo's renders back
to pop-os use rsync **without** `--delete`, quasimodo → pop-os direction only:

```bash
rsync -az quasimodo:/app/portrender/data/renders/ /app/portrender/data/renders/
```

Exports (`--to tee-empire|clemtock|au2`) are local file copies, so run them on the host that
holds the target checkout. On quasimodo all three live under `/app` (`/app/tee-empire`,
`/app/clemtock`, `/app/AU2`), which is the point of running portrender there. From pop-os,
`--to clemtock` needs `CLEMTOCK_DIR` pointing at a local checkout and `CLEMTOCK_URL=http://192.168.0.20:3053`
for the rescan poke; the plain file copy does not cross hosts.
