# pracuj-cli

CLI for [Pracuj.pl IT](https://it.pracuj.pl).

## Installation

Dependencies are installed from the **workspace root** (shared with all portal scrapers):

```bash
cd .agents/skills && bun install
# or from repo root: ./install-skills.sh
```

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search IT job listings |
| `detail <id\|url>` | Full job posting |

## Response shape (search)

```json
{
  "meta": { "total": 120, "page": 1, "perPage": 20 },
  "results": [{
    "id": "12345678",
    "title": "Python Developer",
    "company": "Acme",
    "location": "Warszawa",
    "date": "2026-06-01",
    "deadline": null,
    "salary": "15000 - 20000 PLN",
    "url": "https://it.pracuj.pl/...",
    "description": "short excerpt"
  }]
}
```

Errors: stderr `{ "error": "...", "code": "..." }`, exit `1`.
