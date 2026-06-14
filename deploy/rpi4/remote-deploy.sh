#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

git fetch origin main
git checkout main
git pull --ff-only origin main

bash deploy/rpi4/install.sh

sudo systemctl restart worksphere
sleep 3
curl -sf http://127.0.0.1:8080/health >/dev/null

git describe --tags --always > .deployed-version
echo "Deployed $(cat .deployed-version)"
