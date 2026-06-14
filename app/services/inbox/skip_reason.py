"""Skip reason helpers — auto triage categories and token labels."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.jobs import AutoSkipCategory, SkipReasonDetails


def resolve_auto_skip_category(
    quick_fit: str,
    triage_score: int,
) -> AutoSkipCategory:
    low_fit = quick_fit == "low"
    low_score = triage_score <= -50
    if low_fit and low_score:
        return "auto_low_fit_and_score"
    if low_fit:
        return "auto_low_fit"
    return "auto_low_score"


def build_auto_skip_reason(
    *,
    quick_fit: str,
    triage_score: int,
    triage_reason: str,
) -> SkipReasonDetails:
    return SkipReasonDetails(
        source="auto_triage",
        category=resolve_auto_skip_category(quick_fit, triage_score),
        triage_reason=triage_reason or None,
        triage_score=triage_score,
        quick_fit=quick_fit,  # type: ignore[arg-type]
        skipped_at=datetime.now(timezone.utc).isoformat(),
    )


def build_auto_english_skip_reason(
    *,
    matched: str,
    triage_score: int,
    triage_reason: str,
    quick_fit: str,
) -> SkipReasonDetails:
    return build_auto_language_skip_reason(
        language="english",
        level=matched,
        triage_score=triage_score,
        triage_reason=triage_reason or matched,
        quick_fit=quick_fit,
        matched_token=matched,
    )


def build_auto_language_skip_reason(
    *,
    language: str,
    level: str,
    triage_score: int,
    triage_reason: str,
    quick_fit: str,
    matched_token: str | None = None,
) -> SkipReasonDetails:
    token = matched_token or f"{language}_{level}"
    reason = triage_reason or token
    gap_label = f"lang_gap:{language}:{level}"
    if gap_label not in reason:
        reason = f"{reason}, {gap_label}" if reason and reason != "generic" else gap_label
    return SkipReasonDetails(
        source="auto_triage",
        category="auto_language_level",
        triage_reason=reason or None,
        triage_score=triage_score,
        quick_fit=quick_fit,  # type: ignore[arg-type]
        skipped_at=datetime.now(timezone.utc).isoformat(),
    )


def stamp_manual_skip_reason(details: SkipReasonDetails) -> SkipReasonDetails:
    return details.model_copy(
        update={
            "source": "manual",
            "skipped_at": datetime.now(timezone.utc).isoformat(),
        }
    )
