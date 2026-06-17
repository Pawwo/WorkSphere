"""Re-audit jobs skipped by auto-triage after posting extract / salary fixes."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Literal

from app.config import Settings, get_settings
from app.models.jobs import SeenJobEntry
from app.services.fit_cache import get_fit
from app.services.inbox.language_levels import language_gap, load_candidate_languages
from app.services.inbox.language_triage import (
    extract_language_requirements,
    fetch_posting_text_sync,
)
from app.services.inbox.tier_rules import assign_tier
from app.services.keyword_triage import keyword_fit_hint
from app.services.salary_service import SalaryAssessment, SalaryService
from app.services.scrape.posting_extract import description_for_storage
from app.services.workflow.triage import salary_triage_penalty, score_job
from app.storage.job_repository import JobRepository

logger = logging.getLogger(__name__)

FitLevel = Literal["high", "medium", "low"]


@dataclass
class ReauditRow:
    key: str
    url: str
    title: str
    company: str
    skip_category: str | None
    old_triage_score: int | None
    old_fit: FitLevel
    new_triage_score: int
    new_fit: FitLevel
    new_tier: str
    would_restore: bool
    fetch_ok: bool
    desc_len_before: int
    desc_len_after: int
    salary_before: int | None
    salary_after: int | None
    salary_meets_before: bool | None
    salary_meets_after: bool | None
    salary_source_after: str | None
    triage_reason: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def refetch_clean_description(job: SeenJobEntry) -> tuple[str, bool]:
    """Return cleaned description and whether HTTP fetch succeeded."""
    url = job.url or ""
    portal = job.portal or ""
    fetched = fetch_posting_text_sync(url) if url else None
    if fetched:
        cleaned = description_for_storage(fetched, portal=portal, url=url)
        if cleaned.strip():
            return cleaned, True
    existing = (job.description or "").strip()
    if existing:
        reextracted = description_for_storage(existing, portal=portal, url=url)
        if len(reextracted.strip()) >= 80:
            return reextracted, False
        return existing, False
    return "", False


def _posting_blob(job: SeenJobEntry, description: str) -> str:
    parts = [job.title or "", job.salary_raw or "", description]
    return " ".join(p.strip() for p in parts if p.strip())


def _language_gaps(requirements, profile_langs) -> list:
    if not profile_langs:
        return []
    return [
        req
        for req in requirements
        if language_gap(profile_langs, language=req.language, level=req.level)
    ]


def evaluate_auto_skipped_job(
    job: SeenJobEntry,
    *,
    salary_svc: SalaryService,
    profile_langs,
    description: str | None = None,
    fetch_ok: bool | None = None,
) -> tuple[FitLevel, int, str, str, SalaryAssessment]:
    """Simulate triage as if job.status were new; return fit, score, reason, tier, assessment."""
    if description is None:
        description, fetch_ok = refetch_clean_description(job)
    fetch_ok = bool(fetch_ok)

    assessment = salary_svc.assess(
        title=job.title,
        salary=job.salary_raw,
        description=description,
    )
    low_hint = keyword_fit_hint(job.title, job.company or "")
    if low_hint:
        base_fit: FitLevel = "low"
    else:
        base_fit = get_fit(job.url or "", job.title, job.company or "") or job.fit  # type: ignore[assignment]
    quick_fit = salary_svc.adjust_fit(base_fit, assessment, salary_svc.threshold_pln)  # type: ignore[arg-type]

    triage_score, reason = score_job(job.title, job.company or "")
    job_data = {
        "salary_b2b_monthly": assessment.monthly_b2b_median,
        "salary_meets_threshold": assessment.meets_threshold,
        "salary_source": assessment.source,
    }
    sal_pen, sal_reason = salary_triage_penalty(job_data, salary_svc)
    triage_score += sal_pen
    if sal_reason:
        reason = f"{reason}, {sal_reason}" if reason != "generic" else sal_reason

    blob = _posting_blob(job, description)
    from app.services.inbox.fit_signals import extract_job_signals
    job_signals = extract_job_signals(title=job.title, description=blob)
    requirements = extract_language_requirements(blob)
    lang_gaps = _language_gaps(requirements, profile_langs)
    if lang_gaps:
        tier = "skip"
    else:
        tier = assign_tier(
            quick_fit=quick_fit,
            triage_score=triage_score,
            salary_meets_threshold=assessment.meets_threshold,
            pi_score=job.pi_score,
            pi_verdict=job.pi_verdict,
            job_signals=job_signals,
        )

    note = "fetch_ok" if fetch_ok else "reextract_only" if description else "no_description"
    return quick_fit, triage_score, reason, tier, assessment


def is_auto_triage_skipped(job: SeenJobEntry) -> bool:
    if job.status != "skipped":
        return False
    sr = job.skip_reason
    return sr is not None and sr.source == "auto_triage"


def reaudit_auto_skipped_jobs(
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    categories: set[str] | None = None,
) -> dict:
    settings = settings or get_settings()
    repo = JobRepository(settings.seen_jobs_path)
    salary_svc = SalaryService(settings)
    profile_langs = load_candidate_languages(settings)

    rows: list[ReauditRow] = []
    restored = 0
    still_skipped = 0
    fetch_ok_count = 0
    errors = 0

    candidates: list[tuple[str, SeenJobEntry]] = []
    for key, job in repo.all().items():
        if not is_auto_triage_skipped(job):
            continue
        cat = job.skip_reason.category if job.skip_reason else None
        if categories and cat not in categories:
            continue
        candidates.append((key, job))

    candidates.sort(key=lambda x: x[1].first_seen or "", reverse=True)
    if limit is not None:
        candidates = candidates[:limit]

    for idx, (key, job) in enumerate(candidates, start=1):
        try:
            desc_before = job.description or ""
            description, fetch_ok = refetch_clean_description(job)
            if fetch_ok:
                fetch_ok_count += 1

            quick_fit, triage_score, reason, tier, assessment = evaluate_auto_skipped_job(
                job,
                salary_svc=salary_svc,
                profile_langs=profile_langs,
                description=description,
                fetch_ok=fetch_ok,
            )
            would_restore = tier != "skip"
            note = "restore" if would_restore else "keep_skipped"

            row = ReauditRow(
                key=key,
                url=job.url or key,
                title=job.title,
                company=job.company or "",
                skip_category=job.skip_reason.category if job.skip_reason else None,
                old_triage_score=job.skip_reason.triage_score if job.skip_reason else None,
                old_fit=job.fit,
                new_triage_score=triage_score,
                new_fit=quick_fit,
                new_tier=tier,
                would_restore=would_restore,
                fetch_ok=fetch_ok,
                desc_len_before=len(desc_before),
                desc_len_after=len(description),
                salary_before=job.salary_b2b_monthly,
                salary_after=assessment.monthly_b2b_median,
                salary_meets_before=job.salary_meets_threshold,
                salary_meets_after=assessment.meets_threshold,
                salary_source_after=assessment.source,
                triage_reason=reason,
                note=note,
            )
            rows.append(row)

            if would_restore:
                restored += 1
                if not dry_run:
                    repo.upsert(
                        key,
                        job.model_copy(
                            update={
                                "status": "new",
                                "skip_reason": None,
                                "description": description or job.description,
                                "fit": quick_fit,
                                "salary_raw": assessment.salary_raw or job.salary_raw,
                                "salary_b2b_monthly": assessment.monthly_b2b_median,
                                "salary_source": assessment.source,
                                "salary_meets_threshold": assessment.meets_threshold,
                            }
                        ),
                    )
            else:
                still_skipped += 1
                if not dry_run and (
                    description != job.description
                    or assessment.monthly_b2b_median != job.salary_b2b_monthly
                    or assessment.meets_threshold != job.salary_meets_threshold
                ):
                    repo.upsert(
                        key,
                        job.model_copy(
                            update={
                                "description": description or job.description,
                                "salary_raw": assessment.salary_raw or job.salary_raw,
                                "salary_b2b_monthly": assessment.monthly_b2b_median,
                                "salary_source": assessment.source,
                                "salary_meets_threshold": assessment.meets_threshold,
                            }
                        ),
                    )
        except Exception as exc:
            errors += 1
            logger.exception("Reaudit failed for %s: %s", key, exc)
            rows.append(
                ReauditRow(
                    key=key,
                    url=job.url or key,
                    title=job.title,
                    company=job.company or "",
                    skip_category=job.skip_reason.category if job.skip_reason else None,
                    old_triage_score=job.skip_reason.triage_score if job.skip_reason else None,
                    old_fit=job.fit,
                    new_triage_score=0,
                    new_fit=job.fit,
                    new_tier="skip",
                    would_restore=False,
                    fetch_ok=False,
                    desc_len_before=len(job.description or ""),
                    desc_len_after=0,
                    salary_before=job.salary_b2b_monthly,
                    salary_after=None,
                    salary_meets_before=job.salary_meets_threshold,
                    salary_meets_after=None,
                    salary_source_after=None,
                    triage_reason="",
                    note=f"error:{exc}",
                )
            )

        if idx % 25 == 0 or idx == len(candidates):
            logger.info(
                "Reaudit progress %s/%s — restore candidates: %s",
                idx,
                len(candidates),
                restored,
            )

    if not dry_run:
        repo.flush()

    return {
        "candidates": len(candidates),
        "restored": restored,
        "still_skipped": still_skipped,
        "fetch_ok": fetch_ok_count,
        "errors": errors,
        "dry_run": dry_run,
        "rows": [r.to_dict() for r in rows],
    }
