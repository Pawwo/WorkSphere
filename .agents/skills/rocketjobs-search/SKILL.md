---
name: rocketjobs-search
version: 1.1.0
description: >
  Search Polish job listings on RocketJobs.pl. Use for job search in Poland,
  IT vacancies, remote/hybrid roles, and RocketJobs.pl lookups.
context: fork
allowed-tools: Bash(bun run .agents/skills/rocketjobs-search/cli/src/cli.ts *)
---

# RocketJobs.pl Search Skill

Jedyny skill RocketJobs w projekcie (mapowany w `app/scrapers/bun_cli.py`).

**Wzorzec implementacji:** [`justjoin-search`](../justjoin-search/SKILL.md) — `scraper-shared` + `listing-only`, tokenizacja zapytania, fallback przez `extractLinks`.

**Źródło danych (kolejność):**
1. `api.rocketjobs.pl` — publiczne API (primary, szybkie)
2. HTML listing `oferty-pracy/wszystkie-lokalizacje?search=…` — fallback

```bash
bun run .agents/skills/rocketjobs-search/cli/src/cli.ts search --query "python warszawa" --days 14 --format json
bun run .agents/skills/rocketjobs-search/cli/src/cli.ts detail <id|url> --format plain
```

Workflow: `search` → `detail`. W batchu zawsze `--listing-only true` (bez per-offer fetch).
