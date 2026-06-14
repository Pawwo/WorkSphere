---
name: pracuj-search
version: 1.0.0
description: >
  Use this skill when searching for IT jobs in Poland on Pracuj.pl, finding Polish job
  listings, or looking up Pracuj.pl postings. Triggers on: pracuj, pracuj.pl, oferty IT,
  praca IT polska, python warszawa, developer kraków, praca zdalna polska, job search poland.
context: fork
allowed-tools: Bash(bun run .agents/skills/pracuj-search/cli/src/cli.ts *)
---

# Pracuj.pl Search Skill

Search live IT job listings from [it.pracuj.pl](https://it.pracuj.pl). Filters hybrid/remote by default.

## Commands

```bash
bun run .agents/skills/pracuj-search/cli/src/cli.ts search --query "python warszawa" --days 14 --format json
bun run .agents/skills/pracuj-search/cli/src/cli.ts detail <id|url> --format plain
```

Key flags: `--query` / `-q`, `--days`, `--page`, `--limit`, `--format json|table|plain`.

Workflow: `search` → `detail` for full descriptions.
