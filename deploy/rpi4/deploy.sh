#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE="${WORKSPHERE_REMOTE:-admin@192.168.0.194}"
REMOTE_DIR="${WORKSPHERE_REMOTE_DIR:-/home/admin/worksphere}"
EXCLUDE="$ROOT/deploy/rpi4/rsync-exclude.txt"

MODE="${1:---code-only}"

rsync_args=(
  -avz
  --exclude-from="$EXCLUDE"
)

case "$MODE" in
  --initial)
    echo "Initial deploy to $REMOTE:$REMOTE_DIR"
    ssh "$REMOTE" "mkdir -p $REMOTE_DIR"
    rsync "${rsync_args[@]}" "$ROOT/" "$REMOTE:$REMOTE_DIR/"
    echo "Run on Pi: cd ~/worksphere && bash deploy/rpi4/install.sh"
    ;;
  --code-only)
    echo "Code-only sync to $REMOTE:$REMOTE_DIR"
    rsync "${rsync_args[@]}" "$ROOT/" "$REMOTE:$REMOTE_DIR/"
    ;;
  *)
    echo "Usage: $0 [--initial|--code-only]" >&2
    exit 1
    ;;
esac

echo "Rsync done."
