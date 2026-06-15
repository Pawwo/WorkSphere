# WorkSphere

Samodzielna aplikacja webowa do wyszukiwania ofert pracy w Polsce, triażu inboxu i przygotowywania aplikacji (CV, list motywacyjny, ocena dopasowania).

## Funkcje

- **Scraping** — 8 polskich portali (Pracuj, Praca.pl, JustJoin, NoFluffJobs, TheProtocol, RocketJobs, LinkedIn PL, Indeed PL)
- **Inbox & triage** — automatyczny fit, języki, widełki, kolejka apply
- **Apply pipeline** — evaluate → draft CV → review → PDF (HTML + Playwright)
- **Profil** — wizard setup, import CV, dokumenty, search queries
- **Narzędzia** — expand kompetencji, upskill, tracker aplikacji

## Wymagania

| Komponent | Uwagi |
|-----------|--------|
| **Linux** | x86_64 lub aarch64/arm64 |
| **Python** | 3.10+ |
| **[Bun](https://bun.sh)** | scrapery portalowe (instalator doinstaluje) |
| **LLM** | endpoint **OpenAI-compatible** (`/v1/chat/completions`) |
| **SearXNG** | wyszukiwanie web (opcjonalnie Docker — instalator uruchamia) |
| **Docker** | tylko dla SearXNG (opcjonalnie, ręcznie) |

### LLM

Aplikacja wymaga **dowolnego API zgodnego z OpenAI** (`/v1/chat/completions`). Dobrze sprawdza się polski model [Bielik](https://huggingface.co/speakleash) przez **llama.cpp** (`llama-server`), ale działa też Ollama, vLLM, LocalAI, OpenRouter itp.

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
- instaluje Playwright/Chromium do generowania PDF z HTML (`CV_RENDERER=html`),
- tworzy `.env` z lokalnymi adresami,
- uruchamia **SearXNG** w Dockerze, jeśli Docker jest dostępny.

### Uruchomienie

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Otwórz: **http://localhost:8080/dashboard**

Szczegóły konfiguracji LLM, SearXNG i pierwsze kroki: **[SETUP.md](SETUP.md)**

## Konfiguracja

Skopiuj i edytuj środowisko:

```bash
cp .env.example .env
```

| Zmienna | Opis |
|---------|------|
| `LLM_BASE_URL` | np. `http://127.0.0.1:8006/v1` (llama-server) lub URL OpenRouter |
| `LLM_MODEL` | nazwa modelu na serwerze |
| `SEARXNG_BASE_URL` | np. `http://127.0.0.1:8888` |
| `CV_RENDERER` | `html` (domyślne, Playwright) lub `latex` (legacy) |
| `DATA_DIR` | katalog danych (`./data`) |

Większość ustawień scrape/ATS jest w **`config.yaml`**.

### SearXNG (ręcznie)

```bash
cd deploy/searxng
docker compose up -d
curl -s "http://127.0.0.1:8888/search?q=test&format=json" | head
```

### Przykład: lokalny LLM (llama-server)

```bash
llama-server -m /path/to/bielik.gguf -c 4096 --host 0.0.0.0 --port 8006
```

W `.env`: `LLM_BASE_URL=http://127.0.0.1:8006/v1`

## Strony

| URL | Opis |
|-----|------|
| `/dashboard` | Status systemu, profil, ostatnie scrape |
| `/setup` | Wizard profilu |
| `/inbox` | Triage ofert |
| `/scrape` | Wyszukiwanie z postępem SSE |
| `/apply` | Pipeline aplikacji |
| `/tracker` | Śledzenie wysłanych aplikacji |
| `/tools` | Expand, Upskill, Reset |

## API (skrót)

| Endpoint | Opis |
|----------|------|
| `GET /health` | LLM + SearXNG + scrapers |
| `POST /api/scrape/async` | Scrape w tle |
| `POST /api/apply` | Evaluate / pełny pipeline |
| `GET /api/inbox` | Lista inbox |

Pełna lista endpointów i przykłady `curl`: [SETUP.md](SETUP.md).

## Struktura repozytorium

```
WorkSphere/
├── app/                 # FastAPI + UI
├── .agents/skills/      # Bun workspace — 8 portali
├── data/                # profil, oferty, SQLite (gitignore na dane osobiste)
├── deploy/searxng/      # Docker Compose SearXNG
├── config.yaml          # scrape, LLM, ATS
├── install.sh           # instalator Linux
└── install-skills.sh    # tylko scrapery
```

## Wydajność

Czasy scrape/apply zależą od wybranego LLM i sprzętu. Przy słabszym lokalnym modelu warto w `config.yaml` ustawić: `llm.concurrency: 1`, `scrapers.llm_fit_limit: 40`, `llm.context_size: 4096`.

## Testy

```bash
source .venv/bin/activate
pytest -m "not integration"
```

Testy `integration` wymagają działającego LLM i SearXNG (opcjonalnie).

## Licencja

Apache License 2.0 — zobacz [LICENSE](LICENSE).
