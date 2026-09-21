#!/usr/bin/env bash
# bootstrap-repo.sh — turn this working tree into the real git repo, from portrender.bundle.
#
# Why: the files were delivered through the Claude desktop bridge, which refuses to
# write into .git/ and .claude/. The bundle carries the full history (3 commits) and
# the .claude/skills/portrender files; this script restores both. Run ONCE:
#
#   cd /app/portrender && bash scripts/bootstrap-repo.sh
#
# Idempotent: re-running on an initialised repo just fetches and reports.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
BUNDLE="${1:-$ROOT/portrender.bundle}"
[ -f "$BUNDLE" ] || { echo "no bundle at $BUNDLE" >&2; exit 1; }
if [ ! -d .git ]; then
  git init -q -b main
  echo "==> initialised .git"
fi
git bundle verify "$BUNDLE" >/dev/null
git config user.name  >/dev/null 2>&1 || git config user.name  "jimmer"
git config user.email >/dev/null 2>&1 || git config user.email "jimmershere@gmail.com"

git fetch -q "$BUNDLE" main
if git rev-parse --verify -q main >/dev/null; then
  git merge -q --ff-only FETCH_HEAD || { echo "!! local main has diverged from the bundle; resolve by hand" >&2; exit 1; }
else
  git reset -q --mixed FETCH_HEAD          # point HEAD at the bundle's tip, keep the working files
fi
git checkout -q -- .claude                  # restore the Claude Code skill (bridge could not write it)
[ -x scripts/serve.sh ] || chmod +x scripts/*.sh .local81/hooks/*.sh 2>/dev/null || true

echo "==> HEAD: $(git log -1 --oneline)"
if [ -z "$(git status --porcelain)" ]; then
  echo "==> working tree matches the bundle exactly — repo ready."
else
  echo "==> repo ready; these files differ from the bundle (expected if you edited them):"
  git status --short
fi
echo "    next: cp .env.example .env && chmod 600 .env   # or rely on /app/tee-empire/.env"
echo "          python3 -m portrender doctor --probe"
echo "    (the bundle can be deleted: rm portrender.bundle)"
