# ADR-002: Bun workspaces for portal scrapers

## Status

Accepted

## Date

2026-06-10

## Context

Eight portal scrapers under `.agents/skills/*/cli/` each had its own `package.json`, `bun.lock`, and `node_modules` (~631 MB each, **5.0 GB** total). Dependencies were identical except `playwright` on Indeed. `install-skills.sh` ran `bun install` eight times.

Alternatives considered:

1. **Bun workspaces** (chosen) — hoist shared deps to `.agents/skills/node_modules`; each portal keeps its own `cli.ts` and SKILL.
2. **Monorepo single CLI** — one `scrapers-cli` with subcommands per portal; maximum code dedup but larger refactor and higher regression risk.

## Decision

- Add root [`.agents/skills/package.json`](../.agents/skills/package.json) with workspaces: `scraper-shared`, `*-search/cli`.
- Pin `@bunli/core@0.9.1` and `zod@^3.25.76`; use `workspace:*` for `scraper-shared`.
- Shared devDependencies at workspace root: `typescript`, `bun-types`, `@types/bun`.
- [`install-skills.sh`](../../install-skills.sh): single `bun install` at workspace root; Playwright chromium only for indeed.
- [`app/scrapers/bun_cli.py`](../../app/scrapers/bun_cli.py): subprocess `cwd` = `skills_path`; healthcheck verifies `workspace_modules`.

## Consequences

- Disk usage **5.0 GB → 554 MB** (~89% reduction).
- Faster onboarding: one install command.
- Portal-specific code unchanged; Python `PORTAL_SKILLS` mapping unchanged.
- Developers must run `bun install` from `.agents/skills/`, not per-portal `cli/` directories.
- Future option: exclude npm `bun` runtime package via overrides if `@bunli/core` allows system Bun only.
