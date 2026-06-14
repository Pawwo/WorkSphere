#!/usr/bin/env bash
# Install TinyTeX (user-local, no sudo) + packages for CV/cover PDF generation.
set -euo pipefail

ARCH="$(uname -m)"
TINYTEX_BIN="${HOME}/.TinyTeX/bin/${ARCH}-linux"
export PATH="${TINYTEX_BIN}:${PATH}"

if [[ ! -x "${TINYTEX_BIN}/lualatex" ]]; then
  echo "Installing TinyTeX to ~/.TinyTeX ..."
  curl -sL "https://yihui.org/tinytex/install-unx.sh" | sh
fi

echo "Installing LaTeX packages (CV article template + cover.cls deps) ..."
tlmgr update --self || true
tlmgr install \
  fancyhdr luatexbase \
  textpos titlesec cite xltxtra xunicode realscripts metalogo \
  geometry hyperref xcolor fontspec enumitem tex-gyre extsizes \
  || true

# TeX Gyre Heros (preferred CV body font; falls back to Latin Modern Sans)
tlmgr install tex-gyre || true

echo "LaTeX ready:"
"${TINYTEX_BIN}/lualatex" --version | head -1
"${TINYTEX_BIN}/xelatex" --version | head -1
echo ""
echo "Add to .env (optional):"
echo "LATEX_BIN_DIR=${TINYTEX_BIN}"
