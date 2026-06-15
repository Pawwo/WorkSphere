# WorkSphere

Samodzielna aplikacja webowa do wyszukiwania ofert pracy w Polsce, triażu inboxu i przygotowywania aplikacji (CV, list motywacyjny, ocena dopasowania).

## Funkcje

- **Scraping** — 8 polskich portali (Pracuj, Praca.pl, JustJoin, NoFluffJobs, TheProtocol, RocketJobs, LinkedIn PL, Indeed PL)
- **Inbox & triage** — keyword/LLM fit, widełki, wymagania językowe, kolejka evaluate
- **Apply pipeline** — evaluate → draft CV → review → PDF (HTML + Playwright/Chromium)
- **Profil** — wizard setup, import CV, dokumenty, zapytania wyszukiwania
- **Narzędzia** (`/tools`) — konfiguracja LLM (lokalny serwer / OpenRouter), expand kompetencji, upskill, reset danych
- **Tracker** — status wysłanych aplikacji (SQLite)

## Wymagania

| Komponent | Uwagi |
|-----------|--------|
| **Linux** | x86_64 lub aarch64/arm64 |
| **Python** | 3.10+ |
| **[Bun](https://bun.sh)** | scrapery portalowe (instalator doinstaluje) |
| **LLM** | endpoint **OpenAI-compatible** (`/v1/chat/completions`) — llama-server, Ollama, vLLM, OpenRouter itd. |
| **Docker** | dla SearXNG — instalator próbuje doinstalować (apt) i uruchomić kontener |

Bez LLM i SearXNG aplikacja startuje w trybie **degraded** (scraping keyword-fit i UI działają; expand/upskill i pełny LLM-fit wymagają usług).

## Szybka instalacja (Linux)

```bash
git clone https://github.com/Pawwo/WorkSphere.git
cd WorkSphere
chmod +x install.sh
./install.sh
```

Skrypt `install.sh`:

- tworzy venv i instaluje zależności Python,
- instaluje Bun i scrapery (`.agents/skills/`),
- instaluje Playwright/Chromium do generowania PDF z HTML,
- tworzy lub naprawia `.env` (adresy `127.0.0.1`, `CV_RENDERER=html`),
- **instaluje Docker (apt, jeśli brak) i uruchamia SearXNG** (`deploy/searxng/setup.sh`).

### Uruchomienie

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Otwórz: **http://localhost:8080/dashboard**

Szczegóły: **[SETUP.md](SETUP.md)**

## Konfiguracja

```bash
cp .env.example .env   # opcjonalnie — install.sh tworzy .env automatycznie
```

| Zmienna | Opis |
|---------|------|
| `LLM_BASE_URL` | np. `http://127.0.0.1:8006/v1` (llama-server) lub `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | nazwa modelu na serwerze |
| `SEARXNG_BASE_URL` | `http://127.0.0.1:8888` (po `install.sh`) |
| `CV_RENDERER` | `html` — PDF przez Playwright (domyślne) |
| `DATA_DIR` | katalog danych (`./data`) |

Presety LLM w UI: **Narzędzia → LLM** (`local`, `OpenRouter`). Zapis trafia do `config.yaml` (nadpisuje odpowiadające pola z `.env`).

Większość ustawień scrape i pipeline: **`config.yaml`**.

### Przykład: lokalny LLM (llama-server)

```bash
llama-server -m /path/to/model.gguf -c 4096 --host 0.0.0.0 --port 8006
```

W `.env`: `LLM_BASE_URL=http://127.0.0.1:8006/v1`

### SearXNG — jeśli instalator pominął usługę

```bash
bash deploy/searxng/setup.sh
curl -s "http://127.0.0.1:8888/search?q=test&format=json" | head
```

## Strony

| URL | Opis |
|-----|------|
| `/dashboard` | Status LLM, SearXNG, scrapers |
| `/setup` | Wizard profilu |
| `/inbox` | Triage ofert |
| `/scrape` | Wyszukiwanie (SSE postęp) |
| `/apply` | Pipeline aplikacji |
| `/applications/{id}` | Szczegóły aplikacji, checklista, PDF |
| `/tracker` | Wysłane aplikacje |
| `/tools` | LLM, expand, upskill, reset |

## API (skrót)

| Endpoint | Opis |
|----------|------|
| `GET /health` | LLM + SearXNG + scrapers |
| `POST /api/scrape/async` | Scrape w tle |
| `POST /api/apply` | Evaluate / pełny pipeline |
| `GET /api/inbox` | Lista inbox |
| `GET /api/tools/llm` | Presety i aktualny endpoint LLM |

Pełna lista: [SETUP.md](SETUP.md).

## Struktura repozytorium

```
WorkSphere/
├── app/                 # FastAPI + UI
├── .agents/skills/      # Bun workspace — 8 portali
├── data/                # profil, oferty, SQLite (gitignore)
├── deploy/searxng/      # Docker Compose SearXNG
├── config.yaml          # scrape, LLM, pipeline
├── install.sh           # instalator Linux (+ SearXNG)
└── install-skills.sh    # tylko scrapery
```

## Wydajność

Czasy scrape/apply zależą od LLM i sprzętu. Przy słabszym lokalnym modelu w `config.yaml`: `llm.concurrency: 1`, `scrapers.llm_fit_limit: 40`, `llm.context_size: 4096`.

## Licencja

Apache License 2.0 — zobacz [LICENSE](LICENSE).
