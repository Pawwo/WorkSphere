#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-}"
if [[ -z "$TAG" || ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Usage: remote-rollback.sh vX.Y.Z" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git fetch --tags origin
git checkout "tags/${TAG}" -f
bash deploy/rpi4/install.sh
sudo systemctl restart worksphere
sleep 3
curl -sf http://127.0.0.1:8080/health >/dev/null
printf '%s\n' "$TAG" > .deployed-version
echo "Rollback to $TAG OK"
