# ADR-006: Apply pipeline aligned with upstream ai-job-search

## Status

Accepted (2026-06-10)

## Context

Fork [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) uses Claude Code `/apply` with explicit steps: evaluate → user proceed → draft tex on disk → reviewer → PDF compile → checklist.

Bielik automates this in `PipelineService` + FastAPI UI. Users reported missing CV/cover files and invisible progress.

## Decision

1. **Two-step UX** (unchanged): inbox evaluate (`proceed=false`) stops at `proceed/waiting`; user clicks „Generuj CV i list” for draft→done.
2. **Draft fallback**: `CvTailorService.tailor_application_with_fallback()` uses baseline CV+cover when LLM fails (like evaluate offline fallback).
3. **Persist `.tex` after review** (`stage_persist_tex`): matches upstream Steps 2+4; Documents tab shows files before PDF.
4. **Task events in SQLite** (`task_events`): SSE replays history after reconnect/server restart.
5. **Preflight** `GET /api/applications/{id}/preflight` + UI banner for LLM/LaTeX readiness.
6. **Health** includes `latex` tools check.

## Mapping

| Upstream | Bielik |
|----------|--------|
| Step 0 Parse | `stage_parse` |
| Step 1 Evaluate + ask | `stage_evaluate` + `stage_proceed_gate` |
| Step 2 Draft tex | `stage_draft` + `stage_persist_tex` |
| Step 3–4 Review + revise | `stage_review` + `_apply_edits` |
| Step 5 Compile PDF | `stage_pdf` |
| Step 6 Checklist | `stage_checklist` |

## Consequences

- CV/list `.tex` visible even when PDF compile fails.
- Baseline documents generated without LLM (lower quality but unblocks flow).
- `cv/main_example.tex` copied from upstream for LaTeX reference.
