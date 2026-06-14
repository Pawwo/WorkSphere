# ADR-004: Wyłączenie smart portal routing dla pełnego pokrycia

## Status

Accepted

## Date

2026-06-10

## Context

Porównanie z aplikacjami na Pi (2026-06-10) wykazało **691 ofert** pobranych na Pi w 48h, których nie ma w Bieliku. Główna przyczyna: `smart_portal_routing` w [`app/services/scrape/portal_routing.py`](../../app/services/scrape/portal_routing.py) usuwa portale `justjoin`, `nofluffjobs`, `rocketjobs`, `theprotocol` dla zapytań executive (COO, dyrektor, operations…), mimo że profil `full` w [`config.yaml`](../../config.yaml) definiuje 7 portali.

## Decision

**Option A** — `smart_portal_routing: false` w `config.yaml`. Pojedynczy scrape używa profilu `full` (jak batch).

## Consequences

- Batch i single scrape odpytują wszystkie 7 portali z profilu `full`
- Czas batchu wzrośnie; mitigacja: `parallel_limit`, circuit breaker RocketJobs
- Routing można przywrócić: `SCRAPERS_SMART_PORTAL_ROUTING=true`
