---
name: linkedin-pl-search
version: 1.0.0
description: >
  Search Polish job listings on LinkedIn Poland. Use for job search in Poland,
  IT vacancies, remote/hybrid roles, and LinkedIn Poland lookups.
context: fork
allowed-tools: Bash(bun run .agents/skills/linkedin-pl-search/cli/src/cli.ts *)
---

# LinkedIn Poland Search Skill

```bash
bun run .agents/skills/linkedin-pl-search/cli/src/cli.ts search --query "python warszawa" --days 14 --format json
bun run .agents/skills/linkedin-pl-search/cli/src/cli.ts detail <id|url> --format plain
```

Workflow: `search` → `detail`.
