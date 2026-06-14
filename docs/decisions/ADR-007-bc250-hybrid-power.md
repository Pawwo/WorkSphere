# ADR-007: Hybrydowy profil zasilania LLM na BC-250

## Status

Accepted

## Date

2026-06-11

## Context

Serwer `192.168.0.112` (AMD BC-250) hostuje `llama-server` (Minitron-7B Q4) i SearXNG. Model załadowany 24/7 utrzymuje GPU w stanie podwyższonego poboru (~55 W PPT). Użytkownik potrzebuje maksymalnej wydajności inferencji w czasie pracy i niskiego zużycia energii w spoczynku.

## Options Considered

### Option A: Always-on (warm VRAM)

- Pros: natychmiastowa odpowiedź LLM
- Cons: stały pobór mocy GPU

### Option B: On-demand only (manual start)

- Pros: najniższy idle power
- Cons: użytkownik musi pamiętać o `systemctl start`

### Option C: Hybrid (auto-stop + wake z aplikacji)

- Pros: oszczędność po bezczynności, automatyczne budzenie przed scrape/apply
- Cons: cold start ~20–30 s; `/health` pokazuje `llm.status: idle` gdy wyłączony

## Decision

**Option C** — profil hybrydowy:

- `bc250-llm-manager` na `:8099` (`POST /wake`, `POST /sleep`, `GET /status`)
- auto-stop po **50 min** bezczynności (`bc250-llm-idle.timer`)
- aplikacja woła `wake` przed scrape (LLM fit) i apply pipeline
- profil GPU **work**: 40/40 CU (`bc250-cu-live-manager`) + DPM `performance`
- profil GPU **idle**: DPM `auto`, `llama-server` zatrzymany

## Consequences

- `/health` zwraca `degraded` (nie `error`) gdy LLM w stanie `idle`
- Benchmarki wydajności uruchamiać po `POST /wake` lub `systemctl start llama-server-bielik`
- Regresja tg po czyszczeniu wynikała głównie z **24/40 CU** — naprawa: `enable all` + `write-service-table` (maski `0x1f`)
