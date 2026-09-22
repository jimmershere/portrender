#!/usr/bin/env bash
# load-env.sh — put OPENAI_API_KEY (and friends) into the CURRENT shell without
# writing anything to disk.  Must be sourced:   source scripts/load-env.sh
#
# Order: ./.env  →  /app/tee-empire/.env  (existing exports are never overridden).
# The Python side (config.load_env) reads the same files, so this is only for
# interactive shells / other tools. Everything is local to this host; no ssh.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then echo "source me: source scripts/load-env.sh" >&2; exit 1; fi
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_files="${PORTRENDER_ENV_FILES:-$_here/.env:${TEE_EMPIRE_DIR:-/app/tee-empire}/.env}"
IFS=: read -r -a _list <<<"$_files"
for f in "${_list[@]}"; do
  [ -f "$f" ] || continue
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    line="${line#export }"
    k="${line%%=*}"; v="${line#*=}"; v="${v%%$'\r'}"
    case "$v" in \"*\") v="${v#\"}"; v="${v%\"}" ;; \'*\') v="${v#\'}"; v="${v%\'}" ;; *) v="${v%% #*}" ;; esac
    [ -z "$k" ] || [ -z "$v" ] && continue
    [ -n "${!k:-}" ] && continue
    export "$k=$v"
  done <"$f"
  echo "load-env: read $f"
done
[ -n "${OPENAI_API_KEY:-}" ] && echo "load-env: OPENAI_API_KEY present" || echo "load-env: WARN OPENAI_API_KEY still missing" >&2
unset _here _files _list f line k v
