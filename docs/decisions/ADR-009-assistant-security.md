# ADR-009: In-app AI assistant security model

## Status

Accepted

## Date

2026-06-13

## Context

WorkSphere needs a sidebar AI assistant that answers user questions using system data and performs user-equivalent actions. The assistant must never modify application source code or system configuration files.

Constraints:

- Single-user local deployment
- LLM via existing BielikClient (`/tools` endpoint settings)
- Inbox tracker protection: jobs with `status=evaluated` must not be auto-skipped
- No authentication layer

## Options Considered

### Option A: HTTP loopback to all API routes

- Pros: Reuses OpenAPI surface verbatim
- Cons: Harder to enforce denylists; agent could call `/api/reset` or `PUT /api/tools/llm` if prompt hallucinates paths

### Option B: Whitelist ToolRegistry calling domain services directly (chosen)

- Pros: Explicit allow-list; no filesystem/shell access; audit log per tool run
- Cons: Each action needs a registered tool handler

### Option C: Give LLM file write access to `data/` only

- Rejected: Bypasses business rules (e.g. `seen_jobs.json` triage sync)

## Decision

Implement **Option B**:

1. `ToolRegistry` with static handler map — no dynamic registration
2. Blocked capabilities have **no tool** (code edit, shell, git, LLM endpoint change)
3. Destructive actions (`start_full_apply`, `reset_data`, `expand_apply_profile`) require UI confirmation via `assistant_tool_runs.status=pending`
4. `skip_inbox_job` rejects `status=evaluated` and non-`new` jobs
5. Long-term memory in SQLite `assistant_memory`; conversation in `assistant_messages`
6. All tool invocations logged in `assistant_tool_runs`

## Consequences

- New features exposed to users need an explicit tool + tests to be assistant-callable
- Agent shares `llm_concurrency` semaphore with pipeline — may queue under load
- Bielik 7B JSON tool-calling is fragile; `extract_json` + retry mitigates parse failures
