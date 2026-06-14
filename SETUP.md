# Setup — WorkSphere

Przewodnik instalacji i pierwszego uruchomienia na własnym hoście (Linux x86_64 lub ARM).

## 1. Wymagania

| Komponent | Wersja / uwagi |
|-----------|----------------|
| Python | 3.10+ |
| Bun | [bun.sh](https://bun.sh) — scrapery portalowe |
| curl | healthchecki |
| Docker | opcjonalnie — tylko dla SearXNG |
| LLM | serwer **OpenAI-compatible** (`/v1/chat/completions`) |

CV generowane są jako **HTML → PDF** (Playwright/Chromium). Ustaw `CV_RENDERER=html` w `.env` (domyślne po `install.sh`). Renderer LaTeX jest opcjonalny i legacy.

## 2. Instalacja automatyczna

```bash
git clone https://github.com/Pawwo/WorkSphere.git
cd WorkSphere
chmod +x install.sh
./install.sh
```

Instalator obsługuje **x86_64** i **aarch64/arm64**. Instaluje Python venv, Bun, scrapery, Playwright oraz — gdy Docker jest dostępny — **SearXNG** z `deploy/searxng/`.

## 3. Instalacja ręczna

```bash
cd WorkSphere
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./install-skills.sh
bash scripts/install_playwright.sh
cp .env.example .env
```

Scrapery to **Bun workspace** — uruchamiaj `bun install` tylko w `.agents/skills/`, nie w pojedynczych `*/cli/`.

### SearXNG

```bash
cd deploy/searxng
docker compose up -d
```

Sprawdzenie:

```bash
curl -s "http://127.0.0.1:8888/search?q=test&format=json" | head
```

W `.env`: `SEARXNG_BASE_URL=http://127.0.0.1:8888`

## 4. Konfiguracja LLM

### Domyślny profil: Bielik (lokalnie)

WorkSphere jest optymalizowany pod polski model **[Bielik](https://huggingface.co/speakleash)** w formacie GGUF, serwowany przez **llama-server** (llama.cpp):

```bash
llama-server -m /ścieżka/do/modelu.gguf -c 4096 --host 0.0.0.0 --port 8006
```

```env
LLM_BASE_URL=http://127.0.0.1:8006/v1
LLM_MODEL=nazwa-pliku-modelu.gguf
LLM_API_KEY=unused
```

### Inne serwery OpenAI-compatible

| Serwer | Przykład `LLM_BASE_URL` |
|--------|-------------------------|
| Ollama | `http://127.0.0.1:11434/v1` |
| vLLM / LocalAI | `http://127.0.0.1:8000/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` (+ `LLM_API_KEY`) |

Ustaw `LLM_MODEL` na identyfikator modelu używanego przez dany endpoint.

### Opcjonalnie: wake / idle (lokalny GPU)

Jeśli masz własny manager usypiania LLM (np. skrypt wake/sleep), ustaw:

```env
LLM_WAKE_URL=http://127.0.0.1:8099
LLM_WAKE_ENABLED=true
```

Domyślnie po instalacji: `LLM_WAKE_ENABLED=false`.

### Przykładowa wydajność (lokalny LLM na GPU)

Poniższe wartości są **przykładem** z setupu referencyjnego (AMD local GPU, Vulkan, Minitron-Bielik-7B Q4_K_M, llama.cpp). Nie są wymagane do działania aplikacji.

| Metryka | Przykład |
|---------|----------|
| Prompt processing (pp128) | ~208 tok/s |
| Token generation (tg128) | ~42 tok/s |
| `quick_fit` ×40 | ~35 s |
| Pełny apply | ~2–4 min |

Sugerowane ustawienia w `config.yaml` przy jednym workerze LLM:

| Klucz | Wartość |
|-------|---------|
| `llm.context_size` | 4096 |
| `llm.concurrency` | 1 |
| `scrapers.llm_fit_limit` | 40 |
| `scrapers.highlights_max_per_run` | 10 |

Szczegóły tuningu GPU: [docs/local-llm-llm-power-baseline.md](docs/local-llm-llm-power-baseline.md).

## 5. Uruchomienie

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Otwórz: http://localhost:8080/dashboard

Healthcheck: http://localhost:8080/health

## 6. Pierwsze kroki

### A. Setup profilu

1. Wizard — http://localhost:8080/setup
2. Import CV — `POST /api/setup/cv` z `cv_text`
3. Dokumenty — `data/documents/` lub `POST /api/documents/upload`
4. Finalizacja — `POST /api/setup/finalize`

### B. Wyszukiwanie ofert

- UI: http://localhost:8080/scrape
- API: `POST /api/scrape` lub `POST /api/scrape/async`

```bash
curl -X POST http://localhost:8080/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"query":"python developer warszawa","days":14,"limit":5}'
```

### C. Aplikacja na ofertę

- UI: http://localhost:8080/apply
- Pipeline: evaluate → draft → reviewer → PDF (HTML)

### D. Inbox i tracker

- `/inbox` — triage, skip, evaluate
- `/tracker` — status wysłanych aplikacji

### E. Rozwój kompetencji

- **Expand** — `/tools`
- **Upskill** — `POST /api/upskill`
- **Reset** — `POST /api/reset` z potwierdzeniem `RESET`

## 7. Testy

```bash
source .venv/bin/activate
pytest -m "not integration"
```

## 8. Struktura danych

```
data/
├── profile/          # Profil kandydata (markdown)
├── documents/        # CV, LinkedIn, dyplomy
├── job_scraper/      # seen_jobs.json (lokalne, nie w git)
├── setup/            # wizard_state.json
└── app.db            # SQLite: zadania, aplikacje
```

## 9. Produkcja (opcjonalnie)

Deploy na serwer Linux (systemd, bez Dockera dla aplikacji): [docs/CI_CD.md](docs/CI_CD.md).
