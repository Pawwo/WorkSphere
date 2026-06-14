"""Parallel job fit assessment during scrape."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List

from app.models.jobs import JobCard
from app.services.fit_cache import get_fit, set_fit
from app.services.keyword_triage import keyword_fit_hint
from app.services.salary_service import SalaryAssessment

if TYPE_CHECKING:
    from app.services.scrape_service import ScrapeService


async def fit_jobs_parallel(
    service: ScrapeService,
    jobs: List[tuple[JobCard, str]],
    profile_excerpt: str,
    llm_ok: bool,
    *,
    allow_llm: bool = True,
) -> List[tuple[str, SalaryAssessment]]:
    limit = service.settings.scrape_llm_fit_limit if allow_llm else 0
    unlimited = allow_llm and limit <= 0
    llm_slots = limit if limit > 0 else 0

    async def fit_one(job: JobCard, _portal: str) -> tuple[str, SalaryAssessment]:
        nonlocal llm_slots
        assessment = service.salary.assess(
            title=job.title,
            salary=job.salary,
            description=job.description,
        )
        low_hint = keyword_fit_hint(job.title, job.company or "")
        if low_hint:
            fit: str = service.salary.adjust_fit(low_hint, assessment, service.salary.threshold_pln)
            return fit, assessment

        cached = get_fit(job.url, job.title, job.company or "")
        if cached:
            fit = service.salary.adjust_fit(cached, assessment, service.salary.threshold_pln)
            return fit, assessment

        call_llm = allow_llm and llm_ok and (unlimited or llm_slots > 0)
        if call_llm:
            if not unlimited:
                llm_slots -= 1
            raw_fit = await service.llm.quick_fit(profile_excerpt, job.model_dump())
            set_fit(job.url, job.title, job.company or "", raw_fit)  # type: ignore[arg-type]
        else:
            raw_fit = "medium"
        fit = service.salary.adjust_fit(raw_fit, assessment, service.salary.threshold_pln)  # type: ignore[arg-type]
        return fit, assessment

    return list(await asyncio.gather(*(fit_one(job, portal) for job, portal in jobs)))
