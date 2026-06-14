from app.models.jobs import ManualSkipReasonItem, SeenJobEntry, SkipReasonDetails
from app.services.inbox.auto_skip_reaudit import (
    evaluate_auto_skipped_job,
    is_auto_triage_skipped,
    refetch_clean_description,
)
from app.services.salary_service import SalaryService


def test_is_auto_triage_skipped():
    manual = SeenJobEntry(
        title="PM",
        company="X",
        url="https://example.com/1",
        first_seen="2026-01-01",
        status="skipped",
        skip_reason=SkipReasonDetails(
            source="manual",
            reasons=[ManualSkipReasonItem(category="other", comment="not relevant")],
        ),
    )
    auto = SeenJobEntry(
        title="PM",
        company="X",
        url="https://example.com/2",
        first_seen="2026-01-01",
        status="skipped",
        skip_reason=SkipReasonDetails(
            source="auto_triage",
            category="auto_low_fit",
            triage_score=-15,
            quick_fit="low",
        ),
    )
    assert not is_auto_triage_skipped(manual)
    assert is_auto_triage_skipped(auto)


def test_refetch_clean_description_from_blob(monkeypatch):
    job = SeenJobEntry(
        title="Chief AI Implementation Officer",
        company="Locon",
        url="https://linkedin.com/jobs/view/1",
        first_seen="2026-01-01",
        portal="linkedin-pl",
        description=(
            "LinkedIn chrome " * 30
            + "Widełki: 30.000 - 50.000 PLN B2B "
            + "AI roadmap leadership"
        ),
    )
    monkeypatch.setattr(
        "app.services.inbox.auto_skip_reaudit.fetch_posting_text_sync",
        lambda url: None,
    )
    cleaned, fetch_ok = refetch_clean_description(job)
    assert fetch_ok is False
    assert "30.000" in cleaned or "30000" in cleaned.replace(" ", "")


def test_evaluate_locon_restores_tier(monkeypatch):
    job = SeenJobEntry(
        title="Chief AI Implementation Officer",
        company="Locon Sp. z o.o.",
        url="https://pl.linkedin.com/jobs/view/chief-ai-implementation-officer-at-locon-sp-z-o-o-4425618296",
        first_seen="2026-06-10",
        portal="linkedin-pl",
        fit="low",
        status="skipped",
        description=(
            "Widełki: 30.000 - 50.000 PLN B2B "
            "Chief AI Implementation Officer AI roadmap"
        ),
        salary_b2b_monthly=20000,
        salary_source="estimated",
        salary_meets_threshold=False,
        skip_reason=SkipReasonDetails(
            source="auto_triage",
            category="auto_low_fit",
            triage_score=-15,
            quick_fit="low",
        ),
    )
    monkeypatch.setattr(
        "app.services.inbox.auto_skip_reaudit.get_fit",
        lambda *a, **k: "medium",
    )
    svc = SalaryService()
    quick_fit, score, reason, tier, assessment = evaluate_auto_skipped_job(
        job,
        salary_svc=svc,
        profile_langs=[],
        description=job.description,
        fetch_ok=False,
    )
    assert assessment.meets_threshold is True
    assert tier in ("priority", "review")
    assert quick_fit in ("medium", "high")
    assert score >= 0
    assert "salary_below" not in reason
