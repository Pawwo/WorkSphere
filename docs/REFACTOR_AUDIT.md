# Refactor Audit (reviewing-code)

## Must fix

| File | Issue | Fix |
|------|-------|-----|
| `jobs_service.py` + `workflow_service.py` | Dual inbox APIs, circular sync | Merge into `InboxService` |
| `app/llm/client.py` | Global `asyncio.Lock` serializes all LLM | `Semaphore` with configurable limit |
| `scrape_service.py` | Per-job `quick_fit` LLM on every new job | Keyword triage first, LLM for top N |
| `cv_builder.py` + `apply_service.py` | Duplicated `_escape_latex()` | `latex_utils.py` |
| `config.py` vs `config.yaml` | LLM port 8005 vs 8000 | Single default via YAML merge |

## Should fix

| File | Issue | Fix |
|------|-------|-----|
| `cv_builder.py` (674 LOC) | God class | Split into `app/services/cv/` |
| `profile_service.py` (595 LOC) | God class | Split into `app/services/profile/` |
| `pipeline_service.py` (536 LOC) | God class | Split into `app/services/pipeline/` |
| `scrape_service.py` (471 LOC) | God class | Split into `app/services/scrape/` |
| `files.py` | Full read/write `seen_jobs.json` | Incremental upsert via `JobRepository` |
| `inbox.js`, `setup.js`, `application.js` | Duplicated `apiFetch` | `api.js` shared module |
| Dead files | `jobs_page.py`, `app.js`, `salary_lookup.py` | Remove |

## Nit

- Mixed PL/EN comments — keep Polish UI strings, English code comments
- `layout.py` legacy `WORKFLOW_NAV` — remove unused exports
