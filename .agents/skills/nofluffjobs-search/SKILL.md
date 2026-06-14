---
name: nofluffjobs-search
version: 1.0.0
description: >
  Search Polish job listings on NoFluffJobs. Use for job search in Poland,
  IT vacancies, remote/hybrid roles, and NoFluffJobs lookups.
context: fork
allowed-tools: Bash(bun run .agents/skills/nofluffjobs-search/cli/src/cli.ts *)
---

# NoFluffJobs Search Skill

```bash
bun run .agents/skills/nofluffjobs-search/cli/src/cli.ts search --query "python warszawa" --days 14 --format json
bun run .agents/skills/nofluffjobs-search/cli/src/cli.ts detail <id|url> --format plain
```

Workflow: `search` → `detail`.
