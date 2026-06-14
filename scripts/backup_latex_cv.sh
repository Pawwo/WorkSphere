#!/usr/bin/env bash
# Snapshot LaTeX CV stack before HTML+Playwright migration (rollback source).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${ROOT}/backup/latex-cv-${STAMP}"

mkdir -p "${DEST}"

copy() {
  local src="$1"
  if [[ -e "${ROOT}/${src}" ]]; then
    mkdir -p "${DEST}/$(dirname "${src}")"
    cp -a "${ROOT}/${src}" "${DEST}/${src}"
    echo "  + ${src}"
  fi
}

echo "Backup LaTeX CV → ${DEST}"

copy app/services/cv/tex_builder.py
copy app/services/cv/tex_style.py
copy app/services/latex_service.py
copy app/services/latex_utils.py
copy app/services/apply_service.py
copy app/services/verification_service.py
copy app/services/pipeline/stages.py
copy scripts/install_latex.sh
copy requirements-latex.txt
copy tests/test_cv_tex_style.py
copy tests/test_cv_competencies.py
copy cv/main_example.tex

# Optional: latest generated Wolters artifacts for visual diff
copy cv/main_wolters_kluwer_polska_sp_z_oo.tex
copy cv/main_wolters_kluwer_polska_sp_z_oo.pdf

cat > "${DEST}/RESTORE.md" <<EOF
# Restore LaTeX CV stack

Created: ${STAMP}

## Quick rollback (code only)

\`\`\`bash
cd ${ROOT}
cp -a ${DEST}/app/services/cv/tex_builder.py app/services/cv/
cp -a ${DEST}/app/services/cv/tex_style.py app/services/cv/
cp -a ${DEST}/app/services/latex_service.py app/services/
cp -a ${DEST}/app/services/latex_utils.py app/services/
cp -a ${DEST}/app/services/apply_service.py app/services/
cp -a ${DEST}/app/services/verification_service.py app/services/
cp -a ${DEST}/app/services/pipeline/stages.py app/services/pipeline/
# Set in .env:
# CV_RENDERER=latex
\`\`\`

See docs/decisions/ADR-008-cv-html-playwright-rollback.md for full procedure.
EOF

echo ""
echo "Done. Manifest: ${DEST}/RESTORE.md"
echo "Latest symlink: ${ROOT}/backup/latex-cv-latest"
rm -f "${ROOT}/backup/latex-cv-latest"
ln -s "${DEST}" "${ROOT}/backup/latex-cv-latest"
