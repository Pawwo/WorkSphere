# Setup — WorkSphere

Przewodnik uruchomienia **bez Claude Code**.

## 1. Wymagania

| Komponent | Wersja / uwagi |
|-----------|----------------|
| Python | 3.10+ |
| Bun | [bun.sh](https://bun.sh) — scrapery portalowe |
| curl | healthchecki |
| LaTeX | opcjonalnie: `lualatex`, `xelatex` — generowanie PDF w apply |

### Infrastruktura na `127.0.0.1`

- **Chat LLM** — `llama-server-bielik` (Minitron-7B Q4_K_M) na porcie `8006` (OpenAI `/v1`)
- **Embeddings** — `llama-server-jina-embed` (Jina v3) na porcie `8007` (inne projekty RAG)
- **SearXNG** — Docker na `127.0.0.1`, port `8888` (`deploy/searxng/`)

```bash
curl -s http://127.0.0.1:8006/v1/models
curl -s "http://127.0.0.1:8888/search?q=test&format=json" | head
```

**Wydajność (local GPU Vulkan, Minitron-7B Q4_K_M, llama.cpp 9596, 2026-06-12):**

| Metryka | Typowa wartość |
|---------|----------------|
| Prompt processing (pp128) | **~208 tok/s** |
| Token generation (tg128) | **~42 tok/s** (24/40 CU, jakość OK) |

**24/40 CU** (stock dispatch) — wymagane na tym boardzie: `enable all` (40 CU) powoduje degenerację ESC. Awaryjny CPU: `llama-server-bielik-cpu.service`.

**Aplikacja (optymalizacja pod local GPU, `config.yaml`):**

| Ustawienie | Wartość | Efekt |
|------------|---------|-------|
| `llm.context_size` | 4096 | Zgodne z `-c` na serwerze |
| `llm.concurrency` | 1 | Jedna kolejka = `-np 1` |
| `scrapers.llm_fit_limit` | 40 | Cap `quick_fit` na batch scrape |
| `scrapers.highlights_max_per_run` | 10 | Max highlights LLM per scrape |
| `llm.inference_probe_enabled` | true | `/health` + scrape: probe jakości (ESC) |

Szacunki czasu przy ~42 tok/s: `quick_fit` ×40 ≈ **~35 s** LLM; pełny apply (evaluate+draft+review) ≈ **2–4 min**. Cache fit: `data/fit_cache.json`.

**Profil hybrydowy (oszczędność energii):**

| Usługa | Port | Rola |
|--------|------|------|
| `local-llm-llm-manager` | **8099** | `POST /wake`, `POST /sleep`, `GET /status` |
| `local-llm-llm-idle.timer` | — | auto-stop LLM po 50 min bezczynności |

Aplikacja (`config.yaml`: `llm.wake_url`, `wake_enabled: true`) budzi LLM przed scrape i apply. Port **8099/tcp** otwarty w firewall LAN. W spoczynku `/health` może pokazać `llm.status: idle`.

**Produkcja (2026-06-12):** `llama-server-bielik.service` (Vulkan `-ngl 999`, port **8006**). Gate A/C PASS po formacie + coopmat2 build. Tuning: `scripts/local-llm_llm_gate.sh`, skill `.cursor/skills/local-llm-vulkan-tuning/`.

Po restarcie: binaria w `/usr/local` (build **9596** / `18ef86ece`, `deploy/local-llm/build-llama-vulkan.sh --coopmat2`). Jina (`:8007`) na CPU (`-ngl 0`).

Szczegóły: [docs/local-llm-llm-power-baseline.md](docs/local-llm-llm-power-baseline.md), [ADR-007](docs/decisions/ADR-007-local-llm-hybrid-power.md).

## 2. Instalacja

```bash
cd WorkSphere
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./install-skills.sh   # cd .agents/skills && bun install (+ Playwright dla Indeed)
cp .env.example .env
```

Edytuj `.env` jeśli potrzeba (adresy LLM, SearXNG, ścieżka do `bun`).

Scrapery to **Bun workspace** — nie uruchamiaj `bun install` w pojedynczych katalogach `*/cli/`; zależności są współdzielone w `.agents/skills/node_modules/`.

## 3. Uruchomienie

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Otwórz: http://localhost:8080/dashboard

## 4. Pierwsze kroki

### A. Setup profilu

1. **Wizard** — http://localhost:8080/setup (9 sekcji)
2. **Import CV** — `POST /api/setup/cv` z `cv_text`
3. **Dokumenty** — wrzuć pliki do `data/documents/` lub `POST /api/documents/upload`
4. **Finalizacja** — `POST /api/setup/finalize`

### B. Wyszukiwanie ofert

- UI: http://localhost:8080/scrape (SSE progress)
- API: `POST /api/scrape` lub `POST /api/scrape/async`

### C. Aplikacja na ofertę

- UI: http://localhost:8080/apply
- Pipeline: evaluate → draft → reviewer → LaTeX

### D. Rozwój kompetencji

- **Expand** — `/tools` lub `POST /api/expand/preview`
- **Upskill** — `POST /api/upskill`
- **Reset** — `POST /api/reset` z potwierdzeniem `RESET`

## 5. Testy

```bash
source .venv/bin/activate
pytest tests/test_smoke.py -v
```

## 6. Struktura danych

```
data/
├── profile/          # Profil kandydata (markdown)
├── documents/        # CV, LinkedIn, dyplomy (Path A setup)
├── job_scraper/      # seen_jobs.json
├── upskill/          # Raporty luk kompetencyjnych
├── setup/            # wizard_state.json
└── app.db            # SQLite: scrape_runs, apply_runs, tasks
```

## 7. Workflow (mapowanie z Claude)

| Było (Claude) | Jest (Bielik app) |
|---------------|-------------------|
| `/setup` | `/setup` + `/api/setup/*` |
| `/scrape` | `/scrape` + `/api/scrape` |
| `/apply` | `/apply` + `/api/apply` |
| `/expand` | `/tools` + `/api/expand/*` |
| `/upskill` | `/api/upskill` |
| `/reset` | `/api/reset` |
