#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILLS_DIR="$ROOT/.agents/skills"
PROD_PKG="$ROOT/deploy/rpi4/package.prod.json"
export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
export PATH="$BUN_INSTALL/bin:$PATH"

if [[ ! -f "$PROD_PKG" ]]; then
  echo "Missing $PROD_PKG" >&2
  exit 1
fi

echo "Installing production scraper workspace (no Indeed, no devDeps)..."
cp "$PROD_PKG" "$SKILLS_DIR/package.json"
rm -rf "$SKILLS_DIR/node_modules"
rm -f "$SKILLS_DIR/bun.lock"
(cd "$SKILLS_DIR" && bun install --production)

echo "Production skills installed."
