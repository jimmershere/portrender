#!/usr/bin/env bash
# serve.sh — start/stop/status the portrender web UI as a detached process.
#   scripts/serve.sh start [--host 0.0.0.0] [--port 3070] [--dry-run]
#   scripts/serve.sh stop | status | restart | logs
# Same shape as parts-triage's ./serve.sh. For a boot-persistent service use
# scripts/install-user-service.sh instead (systemd user unit, needs linger).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID="$ROOT/data/portrender.pid"
LOG="$ROOT/data/portrender.log"
PY="${PORTRENDER_PYTHON:-$(command -v python3)}"
cmd="${1:-status}"; shift || true

running() { [[ -f "$PID" ]] && kill -0 "$(cat "$PID")" 2>/dev/null; }

case "$cmd" in
  start)
    if running; then echo "already running (pid $(cat "$PID"))"; exit 0; fi
    mkdir -p "$ROOT/data"
    cd "$ROOT"
    nohup setsid "$PY" -m portrender serve "$@" >>"$LOG" 2>&1 &
    disown || true
    sleep 1
    # setsid forks, so $! is the short-lived wrapper, not the server: resolve the
    # real pid or the pidfile goes stale the instant we write it (stop/status/
    # restart then all report "not running" while the UI is up).
    srv="$(pgrep -f "portrender serve" | head -n1 || true)"
    if [[ -n "$srv" ]]; then echo "$srv" >"$PID"; fi
    if running; then tail -n 2 "$LOG"; else echo "failed to start — see $LOG"; exit 1; fi ;;
  stop)
    if running; then kill "$(cat "$PID")" && rm -f "$PID" && echo stopped; else echo "not running"; rm -f "$PID"; fi ;;
  restart) "$0" stop; "$0" start "$@" ;;
  status)
    if running; then echo "running (pid $(cat "$PID"))"; tail -n 1 "$LOG"; else echo "not running"; exit 1; fi ;;
  logs) tail -n 50 -f "$LOG" ;;
  *) echo "usage: $0 start|stop|restart|status|logs [serve args]" >&2; exit 2 ;;
esac
