#!/usr/bin/env python3
"""Re-run LLM quick_fit on all inbox jobs, then triage for Tier + Score."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.llm.client import BielikClient  # noqa: E402
from app.services.fit_cache import set_fit  # noqa: E402
from app.services.inbox_service import InboxService  # noqa: E402
from app.services.keyword_triage import keyword_fit_hint  # noqa: E402
from app.services.salary_service import SalaryService  # noqa: E402
from app.storage.files import read_profile_excerpt  # noqa: E402
from app.storage.job_repository import JobRepository  # noqa: E402


async def refit_all() -> dict:
    settings = get_settings()
    repo = JobRepository(settings.seen_jobs_path)
    seen = repo.all()
    llm = BielikClient(settings)
    salary = SalaryService(settings)
    profile = read_profile_excerpt(settings)

    health = await llm.healthcheck()
    if not health.get("ok"):
        raise RuntimeError(f"LLM unavailable: {health}")

    sem = asyncio.Semaphore(max(1, settings.llm_concurrency))
    total = len(seen)
    changed = 0
    llm_calls = 0
    keyword_low = 0
    done = 0

    async def refit_one(key: str, job) -> None:
        nonlocal changed, llm_calls, keyword_low, done
        async with sem:
            assessment = salary.assess(
                title=job.title,
                salary=job.salary_raw,
                description=None,
            )
            low_hint = keyword_fit_hint(job.title, job.company or "")
            if low_hint:
                new_fit = salary.adjust_fit(low_hint, assessment, salary.threshold_pln)
                keyword_low += 1
            else:
                description = ""
                if job.highlights:
                    description = "\n".join(job.highlights)
                llm_calls += 1
                raw_fit = await llm.quick_fit(
                    profile,
                    {
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "description": description,
                    },
                )
                set_fit(job.url or key, job.title, job.company or "", raw_fit)  # type: ignore[arg-type]
                new_fit = salary.adjust_fit(raw_fit, assessment, salary.threshold_pln)  # type: ignore[arg-type]

            if new_fit != job.fit:
                changed += 1
                repo.upsert(key, job.model_copy(update={"fit": new_fit}))

            done += 1
            if done % 25 == 0 or done == total:
                print(f"  [{done}/{total}] fit updated: {changed}, llm: {llm_calls}, keyword_low: {keyword_low}")

    await asyncio.gather(*(refit_one(key, job) for key, job in seen.items()))
    repo.flush()

    reset_new = 0
    for key, job in repo.all().items():
        if job.status != "skipped":
            continue
        if job.skip_reason and job.skip_reason.source == "manual":
            continue
        repo.upsert(key, job.model_copy(update={"status": "new", "skip_reason": None}))
        reset_new += 1
    repo.flush()

    triage = InboxService(settings).run_triage()
    return {
        "total": total,
        "fit_changed": changed,
        "llm_calls": llm_calls,
        "keyword_low": keyword_low,
        "reset_to_new": reset_new,
        **triage,
    }


def main() -> None:
    print("Re-fitting all inbox jobs with LLM…")
    result = asyncio.run(refit_all())
    print(f"\nDone. Total: {result['total']}, fit changed: {result['fit_changed']}")
    print(f"LLM calls: {result['llm_calls']}, keyword low: {result['keyword_low']}")
    print(f"Reset to new: {result['reset_to_new']}")
    print(f"Triage — priority: {result['priority']}, review: {result['review']}, auto-skipped: {result['skipped']}")
    print("\nTop 10 evaluate queue:")
    for i, r in enumerate(result["top10"], 1):
        print(
            f"  {i}. [{r['triage_score']}] {r['quick_fit']:6} {r['title'][:50]} | {r['company'][:20]}"
        )


if __name__ == "__main__":
    main()
