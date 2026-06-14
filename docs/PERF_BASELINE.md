# Performance Baseline

Recorded at refactor start (2026-06-10).

## Metrics

| Metric | Baseline | Target post-refactor |
|--------|----------|----------------------|
| Python LOC `app/` | 10,289 | 8,000–8,800 |
| Largest service file | 674 LOC (`cv_builder.py`) | < 300 LOC |
| pytest tests | 47 | 70+ |
| Test coverage (services) | ~50% modules | > 80% critical |
| LLM concurrency | 1 (global lock) | 2 (semaphore) |
| LLM calls per scrape batch | 1 per new job | keyword filter + top N only |

## Known bottlenecks

1. **LLM global lock** — `app/llm/client.py` — all scrape/apply/setup serialized
2. **Per-job quick_fit** — `scrape_service.py` — N LLM calls per scrape
3. **Full JSON rewrite** — `save_seen_jobs()` rewrites entire `seen_jobs.json`
4. **LaTeX subprocess** — 2-pass compile per document (acceptable, not in hot path)
5. **Playwright scrapers** — Indeed/LinkedIn 150–180s timeouts (external)

## Scrapers (Bun) — pre-workspace baseline (2026-06-10)

| Metric | Before workspaces |
|--------|-------------------|
| Total `*/cli/node_modules` | **5.0 GB** (8 × ~631 MB; indeed ~648 MB) |
| Install model | 8× `bun install` in `install-skills.sh` |
| Duplicated heavy deps | `bun` ~177 MB, `@oven/bun-linux-*` ~258 MB, `@bunli/core` ~21 MB per portal |
| Target post-workspace | **< 800 MB** single `.agents/skills/node_modules` |

### Post-workspace (2026-06-10)

| Metric | After workspaces |
|--------|------------------|
| `.agents/skills/node_modules` | **554 MB** (was 5.0 GB) |
| Install | 1× `bun install` (~1.5 s) + Playwright chromium |
| Lockfile | single `.agents/skills/bun.lock` |

```bash
du -ch .agents/skills/*/cli/node_modules | tail -1
```

## Code dedup — baseline (pre-ADR-003, 2026-06-10)

| Area | Metric |
|------|--------|
| TS portal CLI sources | **1761 LOC** total (`cli.ts` + `commands/*` + `helpers.ts` × 8) |
| `fit_order` inline dicts | **4** occurrences (`scrape_service` ×2, `inbox_service` ×2) |
| `load_seen_jobs` / `save_seen_jobs` | **5** call sites outside `JobRepository` |
| JS files with raw `fetch(` | **9** files in `app/static/js/` |
| Martwy kod TS | `scraper-shared/src/cli_args.ts` (unused) |

Target post-dedup: TS shared modules absorb command/CLI/LD boilerplate; `fit_order` → `fit_utils`; `seen_jobs` → `JobRepository` only; service files <300 LOC.

### Post-dedup (2026-06-10)

| Area | After |
|------|-------|
| TS portal CLI sources | **~373 LOC** total (`cli.ts` 7–10 LOC × 8; was 1761) |
| `scraper-shared/src` | **~743 LOC** (+ commands, ld_fetch, listing_search, cli_factory) |
| `fit_order` inline | **0** (→ `app/services/fit_utils.py`) |
| `load_seen_jobs` call sites | delegate via `JobRepository` in `files.py` |
| `pipeline_service.py` | **292 LOC** (+ `pipeline/stages.py` 248) |
| `profile_service.py` | **292 LOC** (+ `profile/generators.py` 325) |
| `scrape_service.py` | **351 LOC** (+ `scrape/queries.py`, `scrape/fit.py`) |
| `inbox_service.py` | **404 LOC** (+ `inbox/filter.py`) |
| pytest | **58 pass** (+ `test_fit_utils`) |
| TS typecheck | all 8 portals pass |

## Measurement commands

```bash
# Coverage baseline
.venv/bin/pytest --cov=app --cov-report=term-missing -q

# LOC by module
find app -name "*.py" | xargs wc -l | sort -n | tail -20

# Scraper disk usage (workspace)
du -sh .agents/skills/node_modules
```
