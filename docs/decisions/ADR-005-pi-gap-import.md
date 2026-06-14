# ADR-005: Import luk ofert z Pi do inbox Bielika

## Status

Accepted

## Date

2026-06-10

## Context

Oferty z werdyktem ✅ lub score ≥ 72 na Pi nie występują w `seen_jobs.json`. Brak mechanizmu backfillu.

## Decision

Rozszerzenie `compare_remote_offers.py` o `--import-pi-gaps` (filtr: ✅ lub 🟨 score≥72). Import tylko nowych URL. Pola: `import_source`, `pi_score`, `pi_verdict`, `pi_app`.

## Consequences

- Priorytetowe oferty z Pi trafiają do triage bez czekania na scrape
- `--offline` używa CSV z `data/comparison_cache/`
