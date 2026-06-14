# ADR-003: Code deduplication strategy

## Status

Accepted

## Date

2026-06-10

## Context

After Bun workspaces (ADR-002) deduplicated npm dependencies (5.0 GB → 554 MB), source-level duplication remains across:

- 8 portal scrapers (identical CLI, ~85% shared commands, repeated JSON-LD helpers)
- Python `seen_jobs` I/O via both `JobRepository` and `storage/files.py`
- `fit_order` dict repeated 4× in scrape/inbox services
- Large service files (>300 LOC): `pipeline_service`, `profile_service`, `scrape_service`, `inbox_service`
- Frontend raw `fetch` vs `window.api`, duplicated apply-async flow

## Decision

1. **Scrapers:** Incremental extraction to `scraper-shared` (commands factory, ld_fetch, links, listing_search) — not a single `scrapers-cli` monorepo.
2. **Python storage:** `JobRepository` as the single write path for `seen_jobs.json`; `load_seen_jobs`/`save_seen_jobs` become thin wrappers.
3. **Python constants:** `fit_utils.FIT_SORT_KEY` replaces inline `fit_order` dicts.
4. **Service size:** Split files >300 LOC into subpackages per [`.cursor/rules/refactor-conventions.mdc`](../../.cursor/rules/refactor-conventions.mdc).
5. **Frontend:** `window.api` for HTTP/SSE; shared `apply-flow.js` for async apply redirect.

## Consequences

- Portal CLIs shrink to portal-specific selectors/URLs (~40–80 LOC each).
- One place to fix scraper command boilerplate and JSON-LD fetch logic.
- Easier testing of shared TS helpers and Python storage.
- Legacy `/api/jobs` and `/api/workflow` routes remain aliases; facades kept.

## Alternatives rejected

- **Single `scrapers-cli` package** — higher regression risk; deferred unless incremental shared modules prove insufficient.
