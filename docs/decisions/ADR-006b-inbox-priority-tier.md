# ADR-006b: Priorytet inboxu z quick_fit i Pi boost

## Status

Accepted

## Date

2026-06-11

## Decision

Tier `priority` w `run_triage` gdy: `quick_fit == high`, `medium` + salary/triage boost, lub `pi_score >= 72` / ✅. Reguły w `app/services/inbox/tier_rules.py`.

## Consequences

Zakładka Priorytet odzwierciedla best fit, nie tylko keyword score.
