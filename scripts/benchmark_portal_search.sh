#!/usr/bin/env bash
# Benchmark portal search CLIs (wall-clock). Run from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS="$ROOT/.agents/skills"
QUERY='COO warszawa'
LIMIT=20

echo "=== praca.pl listing-only (default) ==="
/usr/bin/time -f 'elapsed=%e sec' bun run "$SKILLS/praca-pl-search/cli/src/cli.ts" search \
  --query "$QUERY" --days 2 --limit "$LIMIT" --format json \
  --listing-only true 2>/dev/null | head -c 200
echo ""

echo "=== praca.pl detail mode ==="
/usr/bin/time -f 'elapsed=%e sec' bun run "$SKILLS/praca-pl-search/cli/src/cli.ts" search \
  --query "$QUERY" --days 2 --limit 5 --format json \
  --listing-only false 2>/dev/null | head -c 200
echo ""

echo "=== justjoin listing-only ==="
/usr/bin/time -f 'elapsed=%e sec' bun run "$SKILLS/justjoin-search/cli/src/cli.ts" search \
  --query "$QUERY" --listing-only true --limit "$LIMIT" --format json 2>/dev/null | head -c 200
echo ""
