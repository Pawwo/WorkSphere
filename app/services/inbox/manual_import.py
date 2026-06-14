"""Import a manually submitted job posting into seen_jobs (inbox)."""

from __future__ import annotations

from typing import Optional

from app.config import Settings, get_settings
from app.models.apply import JobParsed
from app.models.jobs import JobCard, ManualImportResult, ScrapeResultItem, SeenJobEntry
from app.services.highlights_service import enrich_highlights_for_new_jobs
from app.services.pi_gap_sync import portal_from_url
from app.services.scrape.fit import fit_jobs_parallel
from app.services.scrape_service import ScrapeService
from app.storage.files import read_profile_excerpt, seen_key, today_iso
from app.storage.job_repository import JobRepository


def _existing_entry(
    repo: JobRepository,
    url: str | None,
    company: str,
    title: str,
) -> tuple[str, SeenJobEntry] | None:
    job_url = (url or "").strip()
    if job_url:
        found = repo.get_by_url(job_url)
        if found:
            return found
    key = seen_key(job_url, company, title)
    seen = repo.all()
    if key in seen:
        return key, seen[key]
    return None


def _parsed_description(parsed: JobParsed) -> str | None:
    text = (parsed.raw_text or "").strip()
    return text[:15000] if text else None


def _backfill_existing(
    entry: SeenJobEntry,
    *,
    url: str | None,
    parsed: JobParsed,
) -> tuple[SeenJobEntry, bool]:
    """Fill missing url/description/location on a duplicate manual import."""
    job_url = (url or "").strip()
    description = _parsed_description(parsed)
    updates: dict = {}
    if job_url and not (entry.url or "").strip():
        updates["url"] = job_url
        updates["portal"] = portal_from_url(job_url)
        if updates["portal"] != "other":
            updates["needs_deep_eval"] = False
    if description and not (entry.description or "").strip():
        updates["description"] = description
    if parsed.location and not entry.location:
        updates["location"] = parsed.location
    if not updates:
        return entry, False
    return entry.model_copy(update=updates), True


def _job_card_from_parsed(url: str | None, parsed: JobParsed) -> JobCard:
    job_url = (url or "").strip()
    key = seen_key(job_url, parsed.company, parsed.role)
    return JobCard(
        id=job_url or key,
        title=parsed.role,
        company=parsed.company,
        location=parsed.location,
        url=job_url,
        description=parsed.raw_text,
    )


async def import_manual_job(
    *,
    url: str | None,
    parsed: JobParsed,
    settings: Optional[Settings] = None,
) -> ManualImportResult:
    settings = settings or get_settings()
    repo = JobRepository(settings.seen_jobs_path)

    existing = _existing_entry(repo, url, parsed.company, parsed.role)
    if existing:
        key, entry = existing
        entry, changed = _backfill_existing(entry, url=url, parsed=parsed)
        if changed:
            repo.upsert(key, entry)
            repo.flush()
        return ManualImportResult(
            created=False,
            key=key,
            url=entry.url,
            fit=entry.fit,
            title=entry.title,
            company=entry.company,
        )

    job_url = (url or "").strip()
    portal = portal_from_url(job_url) if job_url else "other"
    card = _job_card_from_parsed(url, parsed)

    scrape = ScrapeService(settings)
    profile = read_profile_excerpt(settings)
    llm_ok = (await scrape.llm.healthcheck()).get("ok", False)
    fit_results = await fit_jobs_parallel(
        scrape,
        [(card, portal)],
        profile,
        llm_ok,
        allow_llm=True,
    )
    fit, assessment = fit_results[0]

    key = seen_key(job_url, parsed.company, parsed.role)
    entry = SeenJobEntry(
        title=parsed.role,
        company=parsed.company,
        url=job_url,
        description=_parsed_description(parsed),
        first_seen=today_iso(),
        fit=fit,  # type: ignore[arg-type]
        status="new",
        location=parsed.location,
        portal=portal,
        import_source="manual",
        salary_raw=assessment.salary_raw,
        salary_b2b_monthly=assessment.monthly_b2b_median,
        salary_source=assessment.source,
        salary_meets_threshold=assessment.meets_threshold,
        needs_deep_eval=portal == "other",
    )
    repo.upsert(key, entry)
    repo.flush()

    if fit == "high":
        await enrich_highlights_for_new_jobs(
            [
                ScrapeResultItem(
                    fit=fit,
                    title=parsed.role,
                    company=parsed.company,
                    location=parsed.location,
                    url=job_url,
                    portal=portal,
                    description=(parsed.raw_text or "")[:300] or None,
                )
            ],
            settings=settings,
        )

    return ManualImportResult(
        created=True,
        key=key,
        url=job_url,
        fit=fit,  # type: ignore[arg-type]
        title=parsed.role,
        company=parsed.company,
    )
