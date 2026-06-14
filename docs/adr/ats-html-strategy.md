# ADR: ATS HTML strategy (in-repo)

## Status

Accepted — 2026-06-11

## Context

Job applications need CVs that parse reliably in Applicant Tracking Systems (2023–2026):
semantic keyword matching, single-column layout, and no fabricated tools in bullets.

The project already renders CVs as HTML + Playwright PDF. External ATS scanners add cost,
opaque scoring, and break the audit trail from master CV → LLM tailoring → PDF.

## Decision

1. **HTML-only CV surface** — `cv.html.jinja2` + inline CSS; no layout tables, grid, or floats.
   `page-break-inside: avoid` only on `header` and `article` (not whole `section`) to avoid huge PDF gaps.
2. **Truth guard (rule 4.5)** — `SkillTruthIndex` from master CV + profile; post-LLM `sanitize_dict`
   replaces watchlist tools (e.g. Zapier, SAP) not present in allowed facts.
3. **Keyword coverage in-repo** — `ats_keyword_coverage()` on plain-text extract; threshold from
   `config.yaml` → `ats.min_keyword_coverage` (default 0.70).
4. **Verification scoring** — `verification_service` adds ATS checklist items and `ats_score` (0–100)
   in `verification.json`; no third-party API.
5. **Prompt persona** — shared `ats_system.jinja2` included in targets/header/experience/cover prompts.

## Consequences

- Positive: reproducible pipeline, pytest gates, no external dependency for ATS checks.
- Positive: hallucinated technologies are stripped before HTML/PDF.
- Trade-off: `ats_score` is heuristic (parser simulation + coverage), not a vendor match score.
- Future: optional JSON schema for `job_posting_targets` on llama-server for stabler keywords.

## Alternatives considered

- **LaTeX CV** — kept as legacy renderer; worse ATS parse fidelity for many portals.
- **External ATS APIs** — rejected (plan scope: in-repo only).
- **ChatGPT one-off CV** — rejected; loses truth index and versioned pipeline.
