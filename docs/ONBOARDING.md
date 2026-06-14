# Codebase Onboarding — WorkSphere

## Quick Start

1. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. `cp .env.example .env` — ustaw `LLM_BASE_URL`, `SEARXNG_BASE_URL`
3. `./install-skills.sh` — jeden `bun install` w workspace `.agents/skills/` (8 portali)
4. `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080`
5. Otwórz `http://localhost:8080/inbox`

## Architecture

```
app/main.py          → FastAPI, 16 API routers, 10 HTML pages
app/api/             → routes_* (thin HTTP layer)
app/services/        → business logic (~65% LOC)
app/storage/         → files.py (JSON/CSV), db.py (SQLite)
app/llm/             → BielikClient (OpenAI-compatible)
app/scrapers/        → bun_cli.py (subprocess wrapper)
app/ui/              → server-rendered HTML pages
app/static/          → vanilla JS + CSS
.agents/skills/      → Bun workspace: scraper-shared + 8 portal CLIs
```

**Data flow:** Scrape → `seen_jobs.json` → Triage → Evaluate queue → Apply pipeline → SQLite `applications` + LaTeX PDFs.

## Data Models

| Store | Path | Contents |
|-------|------|----------|
| seen_jobs.json | `data/job_scraper/seen_jobs.json` | Inbox state (fit, status, highlights) |
| triage_result.json | `data/job_scraper/triage_result.json` | Tier rankings |
| evaluate_queue.json | `data/job_scraper/evaluate_queue.json` | Top-10 evaluate URLs |
| app.db | `data/app.db` | applications, tasks, scrape_runs |
| job_search_tracker.csv | `data/job_search_tracker.csv` | Legacy tracker (migrating to SQLite) |

## API Reference

- `/api/inbox` — unified inbox (list, counts, triage, evaluate queue)
- `/api/jobs`, `/api/workflow/*` — legacy aliases (deprecated)
- `/api/scrape`, `/api/apply`, `/api/applications`, `/api/tasks` (SSE)
- `/health` — LLM + app health

## Deployment

- Local: uvicorn on `:8080`
- LLM: llama-server (Bielik) on `:8000` or `:8005`
- LaTeX: TinyTeX via `scripts/install_latex.sh`

## Key Files

- `app/services/scrape_service.py` — portal orchestration
- `app/services/pipeline_service.py` — apply stage machine
- `app/services/inbox_service.py` — unified inbox
- `app/storage/job_repository.py` — job persistence abstraction
- `config.yaml` + `app/config.py` — settings merge
