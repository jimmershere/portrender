#!/usr/bin/env bash
# Runs after `local81 deploy --scope portrender`: restart the UI on quasimodo and smoke it.
# (Nested-ssh restarts were flaky for clemtock; prefer the systemd user service — this
# hook just restarts it if present and prints the health check.)
set -euo pipefail
HOST="${PORTRENDER_HOST_ALIAS:-quasimodo}"
ssh -o BatchMode=yes "$HOST" 'bash -s' <<'REMOTE'
set -e
cd /app/portrender
if systemctl --user is-enabled portrender.service >/dev/null 2>&1; then
  systemctl --user restart portrender.service && echo "restarted portrender.service"
else
  echo "no user service installed — run scripts/install-user-service.sh on this host (or scripts/serve.sh start --host 0.0.0.0)"
fi
sleep 1
curl -fsS "http://127.0.0.1:${PORTRENDER_PORT:-3070}/healthz" || echo "healthz not reachable"
REMOTE
