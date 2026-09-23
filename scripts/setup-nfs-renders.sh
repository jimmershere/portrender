#!/usr/bin/env bash
# setup-nfs-renders.sh — make quasimodo the canonical render store (PR-2), visible on pop-os.
#
# PR-2, answered 2026-09-23: "quasimodo is canonical (854 GB free vs pop-os 611 GB, and
# Pillow installed). setup an nfs export to image output directories and have it mount
# to only pop-os for hitl visibility."
#
#   bash scripts/setup-nfs-renders.sh --check     # report only, change nothing
#   bash scripts/setup-nfs-renders.sh             # do it (needs sudo on BOTH hosts)
#   bash scripts/setup-nfs-renders.sh --undo      # unmount + remove the export
#
# Run this FROM pop-os. It drives quasimodo over ssh.
#
# What it sets up
#   quasimodo  exports /app/portrender/data  to 192.168.0.9 ONLY
#   pop-os     mounts it at /mnt/quasimodo-renders, and fstab keeps it across reboots
#
# Why rw and not ro: the human-in-the-loop gate writes approvals into
# data/renders/<job>/render.json. A read-only mount would show you the images and then
# refuse every decision you made about them.
#
# Why this is a script and not something already done for you: it edits /etc/exports and
# /etc/fstab and enables a network file service. That is worth a human reading first.
set -uo pipefail

QUASI_HOST="${QUASI_HOST:-quasimodo}"
QUASI_IP="${QUASI_IP:-192.168.0.20}"
POPOS_IP="${POPOS_IP:-192.168.0.9}"
EXPORT_DIR="${EXPORT_DIR:-/app/portrender/data}"
MOUNT_POINT="${MOUNT_POINT:-/mnt/quasimodo-renders}"
EXPORT_LINE="$EXPORT_DIR ${POPOS_IP}(rw,sync,no_subtree_check)"
FSTAB_LINE="${QUASI_IP}:${EXPORT_DIR} ${MOUNT_POINT} nfs soft,timeo=50,retrans=3,_netdev,nofail,x-systemd.automount 0 0"

MODE=run
case "${1:-}" in --check) MODE=check ;; --undo) MODE=undo ;; "") ;; *) echo "unknown arg $1" >&2; exit 2 ;; esac

say() { printf '%-26s %s\n' "$1" "$2"; }

echo "== NFS render store: ${QUASI_HOST}:${EXPORT_DIR} -> pop-os ${MOUNT_POINT} =="

# ---------- checks ----------
ssh -o BatchMode=yes -o ConnectTimeout=8 "$QUASI_HOST" true 2>/dev/null \
  || { echo "cannot ssh to $QUASI_HOST" >&2; exit 1; }

# UID/GID must line up or every file lands owned by nobody.
LOCAL_ID="$(id -u):$(id -g)"
REMOTE_ID="$(ssh "$QUASI_HOST" 'id -u; id -g' 2>/dev/null | paste -sd: -)"
say "pop-os uid:gid" "$LOCAL_ID"
say "quasimodo uid:gid" "$REMOTE_ID"
if [ "$LOCAL_ID" != "$REMOTE_ID" ]; then
  echo "  !! uid/gid differ — files will appear as 'nobody'. Fix with anonuid/anongid"
  echo "     in /etc/exports, or align the accounts, before trusting writes."
fi

if [ "$MODE" = check ]; then
  say "remote export present" "$(ssh "$QUASI_HOST" "grep -qF '$EXPORT_LINE' /etc/exports 2>/dev/null && echo yes || echo no")"
  say "remote service" "$(ssh "$QUASI_HOST" 'systemctl is-active nfs-kernel-server 2>/dev/null || true')"
  say "local mount" "$(mountpoint -q "$MOUNT_POINT" && echo mounted || echo 'not mounted')"
  say "local fstab entry" "$(grep -qF "$MOUNT_POINT" /etc/fstab 2>/dev/null && echo yes || echo no)"
  exit 0
fi

if [ "$MODE" = undo ]; then
  sudo umount "$MOUNT_POINT" 2>/dev/null && say "unmounted" "$MOUNT_POINT"
  sudo sed -i "\\|${MOUNT_POINT}|d" /etc/fstab && say "fstab" "entry removed"
  ssh "$QUASI_HOST" "sudo sed -i '\\|^${EXPORT_DIR//\//\\/} |d' /etc/exports && sudo exportfs -ra" \
    && say "remote export" "removed"
  exit 0
fi

# ---------- quasimodo: export ----------
ssh "$QUASI_HOST" "bash -s" <<REMOTE
set -u
sudo apt-get install -y -qq nfs-kernel-server </dev/null >/dev/null 2>&1 && echo "  nfs-kernel-server present"
mkdir -p "$EXPORT_DIR"
grep -qF '$EXPORT_LINE' /etc/exports 2>/dev/null || echo '$EXPORT_LINE' | sudo tee -a /etc/exports >/dev/null
sudo exportfs -ra && echo "  exports reloaded"
sudo systemctl enable --now nfs-kernel-server >/dev/null 2>&1 && echo "  service enabled"
echo "  active exports:"; sudo exportfs -v | sed 's/^/    /'
REMOTE

# ---------- pop-os: mount ----------
sudo apt-get install -y -qq nfs-common </dev/null >/dev/null 2>&1 && say "nfs-common" "present"
sudo mkdir -p "$MOUNT_POINT"
grep -qF "$MOUNT_POINT" /etc/fstab 2>/dev/null || echo "$FSTAB_LINE" | sudo tee -a /etc/fstab >/dev/null
sudo systemctl daemon-reload
mountpoint -q "$MOUNT_POINT" || sudo mount "$MOUNT_POINT"
if mountpoint -q "$MOUNT_POINT"; then
  say "mounted" "$MOUNT_POINT"
  df -h "$MOUNT_POINT" | tail -1 | sed 's/^/    /'
else
  echo "  !! mount failed — check: showmount -e $QUASI_IP" >&2
  exit 1
fi

# ---------- prove it works both ways ----------
probe="$MOUNT_POINT/.nfs-probe-$$"
if touch "$probe" 2>/dev/null && ssh "$QUASI_HOST" "test -f '$probe'"; then
  say "read-write check" "OK (pop-os wrote, quasimodo sees it)"
  rm -f "$probe"
else
  echo "  !! write from pop-os did not appear on quasimodo — check uid/gid and export flags" >&2
fi

cat <<NEXT

Done. To make portrender on pop-os work against the canonical store:

    echo 'PORTRENDER_DATA=$MOUNT_POINT' >> /app/portrender/.env
    bash /app/portrender/scripts/serve.sh restart

Leave that line out and pop-os keeps its own separate renders — which is the old
behaviour, and fine if you only want the mount for looking.
NEXT
