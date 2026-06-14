#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "Usage: $0 vX.Y.Z" >&2
  exit 1
fi
if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid tag format: $TAG (expected vX.Y.Z)" >&2
  exit 1
fi

HOST="${WORKSPHERE_HOST:-192.168.0.194}"
USER="${WORKSPHERE_SSH_USER:-admin}"
PORT="${WORKSPHERE_SSH_PORT:-22}"
REMOTE_DIR="${WORKSPHERE_REMOTE_DIR:-/home/admin/worksphere}"

echo "Rolling back $HOST:$REMOTE_DIR to $TAG"
ssh -p "$PORT" "${USER}@${HOST}" "bash -s" -- "$TAG" "$REMOTE_DIR" <<'REMOTE'
set -euo pipefail
TAG="$1"
DIR="$2"
cd "$DIR"
git fetch --tags origin
git checkout "tags/${TAG}" -f
bash deploy/rpi4/install.sh
sudo systemctl restart worksphere
sleep 3
curl -sf http://127.0.0.1:8080/health >/dev/null
printf '%s\n' "$TAG" > .deployed-version
echo "Rollback to $TAG OK"
REMOTE
