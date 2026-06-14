# ADR-001: Job inbox storage strategy

## Status

Accepted

## Date

2026-06-10

## Context

Job state lives in three places: `seen_jobs.json`, `triage_result.json`, and SQLite `applications`.
Dual services (`JobsService`, `WorkflowService`) read/write JSON with ad-hoc sync.

## Decision

- **`JobRepository`** abstracts all `seen_jobs.json` access with incremental upsert (no full-dict rewrite on single updates).
- **`InboxService`** is the single inbox API; triage/queue JSON files remain for tier rankings.
- SQLite stays source of truth for **applications**; JSON for **scrape inbox** until a future migration.
- Legacy routes `/api/jobs` and `/api/workflow` delegate to `/api/inbox`.

## Consequences

- One code path for list/update/skip operations.
- Easier testing via `JobRepository` mock.
- CSV tracker deprecated; rows append only for backward compat.
