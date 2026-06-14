---
name: indeed-pl-search
version: 1.0.0
description: >
  Search Polish job listings on Indeed Poland. Use for job search in Poland,
  IT vacancies, remote/hybrid roles, and Indeed Poland lookups.
context: fork
allowed-tools: Bash(bun run .agents/skills/indeed-pl-search/cli/src/cli.ts *)
---

# Indeed Poland Search Skill

```bash
bun run .agents/skills/indeed-pl-search/cli/src/cli.ts search --query "python warszawa" --days 14 --format json
bun run .agents/skills/indeed-pl-search/cli/src/cli.ts detail <id|url> --format plain
```

Workflow: `search` → `detail`.
