#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="$ROOT/VERSION"
MAIN_PY="$ROOT/app/main.py"
BUMP="${1:-patch}"

if [[ ! -f "$VERSION_FILE" ]]; then
  echo "Missing $VERSION_FILE" >&2
  exit 1
fi

read -r MAJOR MINOR PATCH < <(tr '.' ' ' < "$VERSION_FILE")

case "$BUMP" in
  patch)
    PATCH=$((PATCH + 1))
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
  *)
    echo "Usage: $0 [patch|minor|major]" >&2
    exit 1
    ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
printf '%s\n' "$NEW_VERSION" > "$VERSION_FILE"

python3 - "$NEW_VERSION" "$MAIN_PY" <<'PY'
import re
import sys

new_version, main_py = sys.argv[1], sys.argv[2]
text = open(main_py, encoding="utf-8").read()
updated, n = re.subn(r'version="[^"]+"', f'version="{new_version}"', text, count=1)
if n != 1:
    raise SystemExit(f"Could not update version in {main_py}")
open(main_py, "w", encoding="utf-8").write(updated)
PY

echo "Bumped version to $NEW_VERSION"
