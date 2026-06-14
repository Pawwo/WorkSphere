#!/usr/bin/env bash
# Install Playwright Python package browsers for HTML→PDF CV generation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [[ -x "${ROOT}/.venv/bin/pip" ]]; then
  PIP="${ROOT}/.venv/bin/pip"
  PLAYWRIGHT="${ROOT}/.venv/bin/playwright"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PIP="${ROOT}/.venv/bin/python -m pip"
  PLAYWRIGHT="${ROOT}/.venv/bin/python -m playwright"
else
  PIP="pip"
  PLAYWRIGHT="playwright"
fi

echo "Installing playwright Python package..."
${PIP} install 'playwright>=1.49'

echo "Installing Chromium for Playwright..."
${PLAYWRIGHT} install chromium

echo "Playwright ready for CV PDF generation (CV_RENDERER=html)."
