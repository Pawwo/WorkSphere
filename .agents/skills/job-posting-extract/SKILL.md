---
name: job-posting-extract
description: >-
  Extracts key job requirements from posting HTML (LinkedIn "What we're looking for",
  PL "Wymagania"). Use when scraping jobs, enriching seen_jobs.json description,
  debugging quick_fit/triage on noisy postings, or parsing job board pages.
---

# Job posting extract

## Production code

`app/services/scrape/posting_extract/` — `extract_key_description()`, `description_for_storage()`.

Integrated in:

- `app/services/scrape_service.py` — on scrape save to `seen_jobs.description`
- `app/services/inbox/language_triage.py` — `ensure_posting_blob()` after HTTP fetch

## Section priority

1. Requirements (`What we're looking for`, `Wymagania`, `Qualifications`)
2. Responsibilities (`What you'll be working on`, `Obowiązki`) — only if no requirements block
3. Skip nav, cookies, sign-in, similar jobs

## Manual preview

```bash
uv run python scripts/extract_posting_preview.py "https://www.linkedin.com/jobs/view/..."
```

## Benchmark

```bash
uv run python scripts/benchmark_posting_extract.py --limit 100 --multi-portal
```
