"""Inbox tier assignment — Priorytet = best fit + Pi boost."""

from __future__ import annotations

from app.services.inbox.fit_signals import strong_job_signal


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
    job_signals: dict | None = None,
) -> str:
    if quick_fit == "low" and strong_job_signal(job_signals):
        # Safety net against false-negative quick_fit.
        return "review"
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
