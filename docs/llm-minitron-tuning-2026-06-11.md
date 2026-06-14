# Tuning Bielik-Minitron-7B Q4_K_M (2026-06-11)

Wygenerowano po tuningu konfiguracji serwera, aplikacji i promptów.

## Zmiany wdrożone

### llama-server (`llama-server-bielik.service`)

| Parametr | Przed | Po |
| --- | --- | --- |
| `--batch-size` | 128 | **64** |
| `--ubatch-size` | 64 | **32** |
| `--repeat-penalty` | brak | **1.1** |

### [`config.yaml`](../config.yaml)

| Parametr | Przed | Po |
| --- | --- | --- |
| `context_size` | 4096 | **8192** |
| `concurrency` | 2 (domyślnie) | **1** |
| `timeout_seconds` | 120 | **180** |

### Aplikacja

- [`BielikClient`](../app/llm/client.py): usunięty cap 4096 tokenów; dodane `top_p: 0.9`, `repeat_penalty: 1.1`
- [`quick_fit.jinja2`](../app/prompts/quick_fit.jinja2): few-shot dla `medium` (EY Delivery Manager, Capgemini Process Lead)
- [`expand_extract.jinja2`](../app/prompts/expand_extract.jinja2): jednoznaczny klucz `competencies`
- [`expand_service.py`](../app/services/expand_service.py): fallback `new_competencies` (stringi i obiekty)
- [`reviewer.jinja2`](../app/prompts/reviewer.jinja2): `overall_verdict` jako pierwsze wymagane pole
- [`apply_service.py`](../app/services/apply_service.py): reviewer `max_tokens` 384 → **512**

## Wyniki benchmarku (18 case'ów)

| Metryka | Baseline ([minitron-q4.json](../data/llm_benchmark/minitron-q4.json)) | Po tuningu |
| --- | --- | --- |
| **quality_score** | 86.2 | **100.0** |
| **JSON pass rate** | 92% | **100%** |
| `quick_fit_medium` | 0 (zwracał `low`) | **100** |
| `expand_extract` | 0 (`new_competencies`) | **100** |
| `reviewer` | 50 (brak `overall_verdict`) | **100** |
| `quick_fit_p95` | 329ms | 39113ms* |

\* Pierwszy `quick_fit_high` po restarcie modelu (cold start ~22s); kolejne quick_fit: 492–661ms.

## Per-case po tuningu

| Case | Jakość | Latencja |
| --- | --- | --- |
| quick_fit_high | 100 | 22634ms |
| quick_fit_low | 100 | 661ms |
| quick_fit_medium | 100 | 564ms |
| quick_fit_security | 100 | 492ms |
| evaluate_fit | 100 | 14653ms |
| job_posting_targets | 100 | 7173ms |
| draft_cv_header | 100 | 12298ms |
| draft_cv_experience | 100 | 6963ms |
| draft_cover | 100 | 15254ms |
| reviewer | 100 | 14951ms |
| cv_extract | 100 | 24270ms |
| cv_career_infer | 100 | 13746ms |
| job_highlights | 100 | 6064ms |
| job_parse | 100 | 1399ms |
| behavioral_synthesis | 100 | 10342ms |
| interview_prep | 100 | 15963ms |
| expand_extract | 100 | 6245ms |
| upskill_synthesis | 100 | 11034ms |

## Wnioski

1. **Główny zysk jakości** pochodzi z promptów i fallbacków JSON, nie z samych flag llama-server.
2. **`concurrency: 1`** stabilizuje odpowiedzi JSON przy jednym GPU (BC-250).
3. **`context_size: 8192`** wyrównany z `-c 8192` na serwerze — więcej miejsca na długie prompty CV/expand.
4. Scrape będzie wolniejszy (kolejkowanie LLM), ale zgodnie z priorytetem jakości (ADR-006).
