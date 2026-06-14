---
name: justjoin-search
version: 1.0.0
description: >
  Search Polish job listings on JustJoin.it. Use for job search in Poland,
  IT vacancies, remote/hybrid roles, and JustJoin.it lookups.
context: fork
allowed-tools: Bash(bun run .agents/skills/justjoin-search/cli/src/cli.ts *)
---

# JustJoin.it Search Skill

```bash
bun run .agents/skills/justjoin-search/cli/src/cli.ts search --query "python warszawa" --days 14 --format json
bun run .agents/skills/justjoin-search/cli/src/cli.ts detail <id|url> --format plain
```

Workflow: `search` → `detail`.
