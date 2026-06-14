#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$ROOT/.agents/skills"

echo "Installing scraper workspace dependencies (single bun install)..."
(cd "$SKILLS_DIR" && bun install)

echo "Installing Playwright Chromium for indeed-pl-search..."
(cd "$SKILLS_DIR/indeed-pl-search/cli" && bunx playwright install chromium)

echo "All skills installed."
