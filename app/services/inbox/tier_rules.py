"""Inbox tier assignment — Priorytet = best fit + Pi boost."""

from __future__ import annotations


def pi_priority_boost(pi_score: int | None, pi_verdict: str | None) -> bool:
    if pi_verdict == "✅":
        return True
    return pi_score is not None and pi_score >= 72


def assign_tier(
    *,
    quick_fit: str,
    triage_score: int,
    salary_meets_threshold: bool | None = None,
    pi_score: int | None = None,
    pi_verdict: str | None = None,
) -> str:
    if quick_fit == "low" or triage_score <= -50:
        return "skip"
    if pi_priority_boost(pi_score, pi_verdict):
        return "priority"
    if quick_fit == "high":
        return "priority"
    if quick_fit == "medium" and (triage_score >= 25 or salary_meets_threshold is True):
        return "priority"
    if quick_fit == "medium" and triage_score >= 10:
        return "review"
    return "review"
