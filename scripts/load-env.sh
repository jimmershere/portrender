#!/usr/bin/env bash
# load-env.sh — put OPENAI_API_KEY (and friends) into the CURRENT shell without
# writing anything to disk.  Must be sourced:   source scripts/load-env.sh
#
# Order: ./.env  →  /app/tee-empire/.env  →  (optional) floor2 content-machine
# env over ssh, same trick clemtock uses. Existing exports are never overridden.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then echo "source me: source scripts/load-env.sh" >&2; exit 1; fi
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for f in "$_here/.env" "${TEE_EMPIRE_DIR:-/app/tee-empire}/.env"; do
  if [ -f "$f" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in ''|'#'*) continue ;; esac
      k="${line%%=*}"; v="${line#*=}"; v="${v%%$'\r'}"
      [ -n "${!k:-}" ] && continue
      export "$k=$v"
    done <"$f"
    echo "load-env: read $f"
  fi
done
if [ -z "${OPENAI_API_KEY:-}" ] && [ -n "${PORTRENDER_FLOOR2_ENV:-}" ]; then
  _v="$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${PORTRENDER_FLOOR2_HOST:-floor2}" \
        "set -a; . '$PORTRENDER_FLOOR2_ENV' 2>/dev/null; printf '%s' \"\$OPENAI_API_KEY\"" 2>/dev/null || true)"
  [ -n "$_v" ] && export OPENAI_API_KEY="$_v" && echo "load-env: pulled OPENAI_API_KEY from floor2"
fi
[ -n "${OPENAI_API_KEY:-}" ] && echo "load-env: OPENAI_API_KEY present" || echo "load-env: WARN OPENAI_API_KEY still missing" >&2
unset _here _v
