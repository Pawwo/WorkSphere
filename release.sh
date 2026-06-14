#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BUMP="${1:-patch}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "=== Running tests ==="
pytest

echo "=== Bumping version ($BUMP) ==="
bash scripts/bump_version.sh "$BUMP"
VERSION="$(tr -d '[:space:]' < VERSION)"
TAG="v${VERSION}"

git add -A

if git diff --cached --name-only | grep -qE '^\.env$|\.env$'; then
  echo "Refusing to commit .env — check .gitignore" >&2
  exit 1
fi

if git diff --cached --quiet; then
  echo "No changes to commit after version bump." >&2
  exit 1
fi

git commit -m "chore(release): ${TAG}"

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag $TAG already exists" >&2
  exit 1
fi

git tag -a "$TAG" -m "Release ${TAG}"

echo "=== Pushing to origin ==="
git push origin main
git push origin "$TAG"

echo "Release ${TAG} complete."
echo "Deploy: ./deploy/rpi4/deploy-ssh.sh"
