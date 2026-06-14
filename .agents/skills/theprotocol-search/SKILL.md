---
name: theprotocol-search
version: 1.0.0
description: >
  Search Polish job listings on TheProtocol.it. Use for job search in Poland,
  IT vacancies, remote/hybrid roles, and TheProtocol.it lookups.
context: fork
allowed-tools: Bash(bun run .agents/skills/theprotocol-search/cli/src/cli.ts *)
---

# TheProtocol.it Search Skill

```bash
bun run .agents/skills/theprotocol-search/cli/src/cli.ts search --query "python warszawa" --days 14 --format json
bun run .agents/skills/theprotocol-search/cli/src/cli.ts detail <id|url> --format plain
```

Workflow: `search` → `detail`.
