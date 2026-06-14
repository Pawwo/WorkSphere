# ADR-008: CV HTML + Playwright — migracja i rollback

## Status

Accepted (2026-06-11)

## Kontekst

Generowanie CV PDF opiera się na LaTeX (`tex_builder` → `lualatex`/`xelatex`). Problemy: wolna kompilacja, trudna kontrola odstępów, zależność od TinyTeX. Nowa ścieżka: HTML+CSS (szablon referencyjny użytkownika) + PDF przez Playwright Chromium.

## Decyzja

1. Wprowadzić **feature flag** `CV_RENDERER=latex|html` (domyślnie `latex` do czasu pełnej walidacji).
2. Nowy stack równolegle: `html_builder`, `pdf_service` (Playwright), szablony w `app/templates/cv/`.
3. LaTeX **nie usuwać** do zakończenia Fazy 5 (testy + app #41); backup przed zmianami: `scripts/backup_latex_cv.sh`.

## Rollback

### Poziom 1 — natychmiastowy (bez zmian kodu)

W `.env` lub `config.yaml`:

```env
CV_RENDERER=latex
```

Restart aplikacji. Pipeline wraca do `build_cv_tex` + `LatexService`.

### Poziom 2 — przywrócenie plików z backupu

```bash
bash scripts/backup_latex_cv.sh   # jeśli brak świeżego backupu
cp -a backup/latex-cv-latest/app/services/cv/tex_*.py app/services/cv/
cp -a backup/latex-cv-latest/app/services/latex_service.py app/services/
cp -a backup/latex-cv-latest/app/services/latex_utils.py app/services/
cp -a backup/latex-cv-latest/app/services/apply_service.py app/services/
cp -a backup/latex-cv-latest/app/services/pipeline/stages.py app/services/pipeline/
export CV_RENDERER=latex
```

### Poziom 3 — git

```bash
git checkout HEAD -- app/services/cv/tex_builder.py app/services/cv/tex_style.py
git checkout HEAD -- app/services/latex_service.py app/services/apply_service.py
```

Usunąć (jeśli wdrożone): `app/services/cv/html_builder.py`, `app/services/pdf_service.py`, `app/templates/cv/`.

### Weryfikacja po rollbacku

1. `bash scripts/install_latex.sh` — TinyTeX dostępny.
2. `GET /health` → `latex.ok: true`.
3. Regeneracja aplikacji testowej → `pdf_cv` powstaje, checklista 17/17.
4. Porównanie PDF z `backup/latex-cv-latest/cv/*.pdf`.

## Ryzyka

| Ryzyko | Rollback |
|--------|----------|
| Playwright/Chromium brak na hoście | `CV_RENDERER=latex` |
| HTML PDF > 2 strony | Tymczasowo latex; potem trim w `CvDraftData` |
| Checklista pada na HTML | `verification_service` dual-mode lub flag latex |

## Powiązane pliki

- Backup: `scripts/backup_latex_cv.sh` → `backup/latex-cv-<timestamp>/`
- Plan migracji: `.cursor/plans/html_playwright_cv_8886eb0a.plan.md`
- Renderer factory: `app/services/cv/renderer_factory.py`
