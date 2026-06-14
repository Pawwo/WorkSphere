# WorkSphere

Samodzielna aplikacja webowa do wyszukiwania pracy i przygotowywania aplikacji — **bez Claude Code**.

- **LLM:** Bielik-Minitron-7B Q4_K_M (`llama-server` na `127.0.0.1:8006`)
- **WebSearch:** SearXNG (`127.0.0.1:8888`)
- **Scrapery:** 8 polskich portali (Bun CLI z `.agents/skills/`)

## Wymagania

- Python 3.10+
- [Bun](https://bun.sh)
- `curl`
- Na `127.0.0.1`: llama-server (Minitron chat :8006); SearXNG na `127.0.0.1:8888`
- Opcjonalnie: LaTeX (`lualatex`, `xelatex`) — faza apply

## Instalacja

```bash
cd WorkSphere

# Środowisko Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Scrapery portalowe (Bun workspace — jeden install dla 8 portali)
./install-skills.sh
# równoważnie: cd .agents/skills && bun install

# Konfiguracja
cp .env.example .env
# edytuj .env jeśli potrzeba
```

## Uruchomienie

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Otwórz: http://localhost:8080/dashboard

Pełny przewodnik: [SETUP.md](SETUP.md)

## Strony web

| URL | Opis |
|-----|------|
| `/dashboard` | Status systemu, profil, ostatnie scrape |
| `/setup` | Wizard profilu (9 sekcji) |
| `/scrape` | Wyszukiwanie ofert z SSE progress |
| `/apply` | CV + list motywacyjny |
| `/tools` | Expand, Upskill, Reset |

## API

| Endpoint | Opis |
|----------|------|
| `GET /api/dashboard` | Podsumowanie stanu aplikacji |
| `GET /health` | Status Bielik + SearXNG + scrapers |
| `POST /api/scrape/async` | Scrape w tle → `{task_id}` |
| `GET /api/tasks/{id}` | Status zadania |
| `GET /api/tasks/{id}/stream` | SSE progress |
| `POST /api/documents/upload` | Upload do `data/documents/` |
| `GET /setup` | Wizard setup profilu (HTML) |
| `GET /api/setup/status` | Status uzupełnienia profilu |
| `GET /api/setup/wizard` | Schema 9 sekcji wizarda |
| `POST /api/setup/wizard/section` | Zapis sekcji `{section, data}` |
| `POST /api/setup/cv` | Import CV (Path B) `{cv_text}` |
| `POST /api/setup/finalize` | Generuj pliki profilu |
| `GET /api/profile/{file}` | Odczyt pliku profilu |
| `POST /api/apply` | Apply: evaluate lub pełny pipeline `{url\|text, proceed, compile_pdf}` |
| `GET /api/apply/runs` | Historia aplikacji |
| `GET /api/files/cv/{name}` | Pobierz CV .tex/.pdf |
| `GET /api/files/cover/{name}` | Pobierz list .tex/.pdf |
| `POST /api/expand/preview` | Skan kompetencji z documents/GitHub |
| `POST /api/expand/apply` | Dodaj kompetencje do profilu |
| `POST /api/upskill` | Raport luk `{mode: aggregate\|targeted}` |
| `POST /api/reset/preview` | Podgląd resetu `{scope}` |
| `POST /api/reset` | Reset z potwierdzeniem `RESET` |
| `POST /api/scrape` | Wyszukiwanie ofert |

Przykład scrape:

```bash
curl -X POST http://localhost:8080/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"query":"python developer warszawa","days":14,"limit":5}'
```

## Struktura

```
WorkSphere/
├── app/                 # FastAPI backend
├── .agents/skills/      # Bun workspace: 8 portal CLIs + scraper-shared
├── data/profile/        # Profil kandydata (markdown)
├── cv/                  # Szablony LaTeX CV
├── cover_letters/       # Szablony listów
├── config.yaml
└── install-skills.sh
```

## Roadmap

- [x] Faza 1: skeleton, health, scrape
- [x] Faza 2: setup wizard (Path B/C), prompty Jinja2
- [x] Faza 3: apply pipeline (evaluate → draft → reviewer → LaTeX)
- [x] Faza 4: expand, upskill, reset
- [x] Faza 5: dashboard, SSE scrape, upload documents, SETUP.md, testy smoke

## Testy

```bash
pytest tests/test_smoke.py -v
```
