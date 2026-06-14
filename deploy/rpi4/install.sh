#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "=== WorkSphere RPi4 install ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r deploy/rpi4/requirements-prod.txt

if ! command -v bun >/dev/null 2>&1; then
  echo "Installing Bun..."
  curl -fsSL https://bun.sh/install | bash
fi

export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
export PATH="$BUN_INSTALL/bin:$PATH"

bash deploy/rpi4/install-skills-prod.sh

if [[ ! -f .env ]]; then
  echo "Creating .env from env.production.example..."
  cp deploy/rpi4/env.production.example .env
fi

echo "=== Install complete ==="
echo "Next: sudo cp deploy/rpi4/worksphere.service /etc/systemd/system/"
echo "      sudo systemctl enable --now worksphere"
