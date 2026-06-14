# ADR-006: Pełny quick_fit lokalnym LLM w batch

## Status

Accepted

## Date

2026-06-11

## Context

`batch_fit_mode: fast` i `scrape_llm_fit_limit: 5` powodowały domyślne `medium` bez LLM. Lokalny Bielik nie generuje kosztów API; priorytetem jest jakość zakładki Inbox Priorytet.

## Decision

- `batch_fit_mode: llm`
- `llm_fit_limit: 0` (bez limitu slotów)
- Równoległość przez `llm_concurrency` + `fit_cache`

## Consequences

- +1–2 min na batch przy ~30 nowych ofertach
- Wszystkie nowe oferty mają realny `quick_fit`
