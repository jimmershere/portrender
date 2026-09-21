#!/usr/bin/env bash
# smoke.sh — no-network end-to-end check: templates → dry-run render → review → export to temp dirs → API.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
export PORTRENDER_DATA="$(mktemp -d)"
T="$(mktemp -d)"; mkdir -p "$T/te/inbox" "$T/ct/assets/mascots" "$T/au2"
export TEE_EMPIRE_DIR="$T/te" CLEMTOCK_DIR="$T/ct" AU2_DIR="$T/au2" CLEMTOCK_URL="http://127.0.0.1:1"
python3 -m portrender templates >/dev/null
python3 -m portrender brands >/dev/null
python3 -m portrender prompt -t tee-graphic -b maddhatch --var subject_desc="a hen" --var headline="Need Some Eggs?" | grep -q 'reads exactly: "Need Some Eggs?"'
J="$(python3 -m portrender render -t sticker -b au2 --var subject_desc="calipers" -n 2 --dry-run --json | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')"
python3 -m portrender approve "$J" 1 >/dev/null
python3 -m portrender export "$J" 1 --to tee-empire --text "EST" >/dev/null
test -f "$T"/te/inbox/*.empirespec.json
python3 -m portrender export "$J" 1 --to clemtock >/dev/null
python3 -m portrender export "$J" 1 --to au2 >/dev/null
E="$(python3 -m portrender edit "$J:1" -p "chrome it" --dry-run -n 1 --json | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')"
python3 -m portrender ls | grep -q "$E"
PORT=$((20000 + RANDOM % 20000))
python3 -m portrender serve --dry-run --port "$PORT" >"$T/srv.log" 2>&1 & SP=$!
trap 'kill $SP 2>/dev/null; rm -rf "$T" "$PORTRENDER_DATA"' EXIT
sleep 1
curl -fsS "http://127.0.0.1:$PORT/api/state" | grep -q '"brands"'
curl -fsS -X POST "http://127.0.0.1:$PORT/api/render" -H 'content-type: application/json' \
  -d '{"prompt":"a lighthouse","n":1}' | grep -q '"queued"'
sleep 3
curl -fsS "http://127.0.0.1:$PORT/api/jobs?limit=1" | grep -q '"done"'
python3 -m unittest discover -s tests -t . -q
echo "smoke: OK"
