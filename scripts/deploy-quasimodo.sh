#!/usr/bin/env bash
# deploy-quasimodo.sh — push portrender (and clemtock) from pop-os to quasimodo and bring
# both services up there. Runs from pop-os; needs `ssh quasimodo` (jimbro) to work.
#
#   scripts/deploy-quasimodo.sh                # portrender + clemtock, then start services
#   scripts/deploy-quasimodo.sh --only portrender
#   scripts/deploy-quasimodo.sh --no-start     # sync only
#
# Uses local81 when it is on PATH (house convention; scopes in each repo's .local81/config.ini),
# otherwise the equivalent rsync. Either way: code is mirrored with --delete, runtime data
# (data/, out/, uploads/, .vault/, node_modules/) and .env are never touched by the mirror.
# The OpenAI key (/app/portrender/.env) is copied separately with scp, mode 600.
set -euo pipefail
HOST="${QUASI_ALIAS:-quasimodo}"
ONLY=""; START=1
while [ $# -gt 0 ]; do case "$1" in
  --only) ONLY="$2"; shift 2 ;; --no-start) START=0; shift ;;
  *) echo "unknown arg $1" >&2; exit 2 ;; esac; done

ssh -o BatchMode=yes -o ConnectTimeout=8 "$HOST" true || { echo "cannot ssh to $HOST" >&2; exit 1; }
ssh "$HOST" 'mkdir -p /app/portrender /app/clemtock'

sync_one() {  # $1 = repo dir, $2 = extra excludes (space separated)
  local dir="$1" ex="$2" name; name="$(basename "$dir")"
  if command -v local81 >/dev/null 2>&1 && [ -f "$dir/.local81/config.ini" ]; then
    ( cd "$dir" && local81 plan --scope "$name" && local81 deploy --latest --scope "$name" --allow-drift )
  else
    local args=(-az --delete --exclude .git --exclude .local81 --exclude .env --exclude __pycache__)
    for e in $ex; do args+=(--exclude "$e"); done
    rsync "${args[@]}" "$dir/" "$HOST:$dir/"
  fi
  echo "==> synced $name"
}

if [ -z "$ONLY" ] || [ "$ONLY" = portrender ]; then
  sync_one /app/portrender "data .venv"
  if [ -f /app/portrender/.env ]; then
    scp -q /app/portrender/.env "$HOST:/app/portrender/.env" && ssh "$HOST" 'chmod 600 /app/portrender/.env'
    echo "==> copied /app/portrender/.env (600)"
  else
    echo "!! /app/portrender/.env not found on this box — quasimodo will have no OPENAI_API_KEY" >&2
  fi
fi
if [ -z "$ONLY" ] || [ "$ONLY" = clemtock ]; then
  sync_one /app/clemtock "out uploads .vault node_modules"
  [ -f /app/clemtock/.env ] && scp -q /app/clemtock/.env "$HOST:/app/clemtock/.env" && ssh "$HOST" 'chmod 600 /app/clemtock/.env' && echo "==> copied /app/clemtock/.env (600)"
fi

[ "$START" = 1 ] || exit 0
ssh "$HOST" 'bash -s' <<'REMOTE'
set -u
echo "== quasimodo: $(python3 --version 2>&1)  linger=$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo ?)"
cd /app/portrender && python3 -m portrender doctor 2>/dev/null | grep -E '"api_key_present"|"clemtock_present"|"tee_empire_present"|"au2_present"' || true
if systemctl --user is-enabled portrender.service >/dev/null 2>&1; then systemctl --user restart portrender.service; else bash scripts/install-user-service.sh --host 0.0.0.0 --port 3070 || scripts/serve.sh start --host 0.0.0.0; fi
if [ -d /app/clemtock/backend ]; then
  cd /app/clemtock
  [ -d node_modules/playwright-core ] || echo "!! clemtock: run bash scripts/quasimodo-setup.sh once (apt packages + npm install)"
  if systemctl --user is-enabled clemtock.service >/dev/null 2>&1; then systemctl --user restart clemtock.service; else bash scripts/install-user-service.sh --host 0.0.0.0 --port 3053 || scripts/serve.sh start; fi
fi
sleep 2
for p in 3070 3053; do printf 'http://%s:%s -> %s\n' "$(hostname -I | awk '{print $1}')" "$p" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/ || echo down)"; done
REMOTE
