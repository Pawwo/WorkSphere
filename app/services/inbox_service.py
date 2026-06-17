"""Unified inbox — list, triage, update jobs (replaces JobsService + WorkflowService)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from pathlib import Path
from collections.abc import Coroutine
from typing import Any, Optional, TypeVar

T = TypeVar("T")


def _run_async_from_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run async coroutine from sync code; safe inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()

from app.config import Settings, get_settings
from app.models.jobs import (
    FitFilter,
    SeenJobEntry,
    SeenJobUpdate,
    StatusFilter,
    TierFilter,
)
from app.services.fit_utils import fit_sort_key
from app.services.inbox.filter import filter_seen_jobs, filter_triage_item
from app.services.salary_service import SalaryService
from app.services.inbox.language_levels import language_gap, load_candidate_languages
from app.services.inbox.language_triage import (
    LanguageRequirement,
    ensure_posting_blob,
    extract_language_requirements,
)
from app.services.inbox.llm_language_triage import batch_extract_language_llm
from app.services.inbox.skip_reason import (
    build_auto_language_skip_reason,
    build_auto_skip_reason,
    stamp_manual_skip_reason,
)
from app.services.inbox.tier_rules import assign_tier
from app.services.workflow.triage import salary_triage_penalty, score_job
from app.storage.files import job_public_url
from app.storage.job_repository import JobRepository, job_url_lookup_variants
from app.storage.json_io import write_json


class InboxService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.repo = JobRepository(self.settings.seen_jobs_path)

    @property
    def triage_path(self) -> Path:
        return self.settings.job_scraper_dir / "triage_result.json"

    @property
    def queue_path(self) -> Path:
        return self.settings.job_scraper_dir / "evaluate_queue.json"

    def _load_triage_data(self) -> dict | None:
        if not self.triage_path.exists():
            return None
        return json.loads(self.triage_path.read_text(encoding="utf-8"))

    def _load_queue_data(self) -> dict | None:
        if not self.queue_path.exists():
            return None
        return json.loads(self.queue_path.read_text(encoding="utf-8"))

    def _find_seen_job(self, seen: dict, url: str) -> SeenJobEntry | None:
        resolved = self._resolve_seen(seen, url)
        return resolved[1] if resolved else None

    def _resolve_seen(self, seen: dict, ref: str) -> tuple[str, SeenJobEntry] | None:
        if not ref:
            return None
        for candidate in job_url_lookup_variants(ref):
            for key, job in seen.items():
                if job.url == candidate or key == candidate:
                    return key, job
        return None

    def _effective_status(self, item: dict, seen: dict) -> str:
        job = self._find_seen_job(seen, item.get("url", ""))
        if job and job.status in ("skipped", "evaluated"):
            return job.status
        return item.get("status") or (job.status if job else "new")

    def _effective_tier(self, item: dict, seen: dict) -> str:
        job = self._find_seen_job(seen, item.get("url", ""))
        if job and job.status == "skipped":
            return "skip"
        return item.get("tier", "")

    def _merge_row(self, item: dict, seen: dict) -> dict:
        ref = item.get("url", "") or item.get("key", "")
        resolved = self._resolve_seen(seen, ref)
        key, job = resolved if resolved else (ref, None)
        public_url = job_public_url(job.url) if job else job_public_url(ref)
        return {
            "url": public_url,
            "key": key,
            "title": item.get("title") or (job.title if job else ""),
            "company": item.get("company") or (job.company if job else ""),
            "tier": self._effective_tier(item, seen),
            "triage_score": item.get("triage_score"),
            "triage_reason": item.get("triage_reason", ""),
            "quick_fit": item.get("quick_fit") or (job.fit if job else "medium"),
            "fit": item.get("quick_fit") or (job.fit if job else "medium"),
            "status": self._effective_status(item, seen),
            "salary_b2b_monthly": item.get("salary_b2b_monthly")
            if item.get("salary_b2b_monthly") is not None
            else (job.salary_b2b_monthly if job else None),
            "salary_meets_threshold": item.get("salary_meets_threshold")
            if item.get("salary_meets_threshold") is not None
            else (job.salary_meets_threshold if job else None),
            "location": job.location if job else "",
            "portal": job.portal if job else "",
            "deadline": job.deadline if job else "",
            "highlights": job.highlights if job else [],
            "first_seen": job.first_seen if job else "",
            "pi_score": job.pi_score if job else item.get("pi_score"),
            "pi_verdict": job.pi_verdict if job else item.get("pi_verdict"),
            "pi_app": job.pi_app if job else item.get("pi_app"),
            "needs_deep_eval": job.needs_deep_eval if job else item.get("needs_deep_eval"),
            "skip_reason": (
                job.skip_reason.model_dump()
                if job and job.skip_reason
                else item.get("skip_reason")
            ),
            "description": job.description if job else None,
            "import_source": job.import_source if job else None,
        }

    def _job_row(self, key: str, job: SeenJobEntry) -> dict:
        return {
            "key": key,
            "url": job_public_url(job.url),
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "deadline": job.deadline,
            "portal": job.portal,
            "first_seen": job.first_seen,
            "fit": job.fit,
            "quick_fit": job.fit,
            "status": job.status,
            "highlights": job.highlights,
            "salary_b2b_monthly": job.salary_b2b_monthly,
            "salary_meets_threshold": job.salary_meets_threshold,
            "salary_source": job.salary_source,
            "skip_reason": job.skip_reason.model_dump() if job.skip_reason else None,
            "description": job.description,
            "import_source": job.import_source,
        }

    def _counts_from_seen(self, seen: dict) -> dict:
        counts = {"high": 0, "medium": 0, "low": 0, "new": 0, "skipped": 0, "evaluated": 0}
        for job in seen.values():
            counts[job.fit] = counts.get(job.fit, 0) + 1
            counts[job.status] = counts.get(job.status, 0) + 1
        return counts

    def _job_ref(self, key: str, job: SeenJobEntry) -> str:
        return job.url or key

    def _ranked_urls(self, triage: dict) -> set[str]:
        urls: set[str] = set()
        for item in triage.get("ranked", []):
            url = item.get("url")
            if not url:
                continue
            urls.add(url)
            urls.update(job_url_lookup_variants(url))
        return urls

    def _is_job_ranked(self, key: str, job: SeenJobEntry, ranked_urls: set[str]) -> bool:
        ref = self._job_ref(key, job)
        if ref in ranked_urls:
            return True
        return any(v in ranked_urls for v in job_url_lookup_variants(ref))

    def _untriaged_count(self, seen: dict, triage: dict | None) -> int:
        if not triage or not triage.get("ranked"):
            return 0
        ranked_urls = self._ranked_urls(triage)
        return sum(
            1
            for key, job in seen.items()
            if job.status == "new" and not self._is_job_ranked(key, job, ranked_urls)
        )

    def _untriaged_item(self, key: str, job: SeenJobEntry) -> dict:
        return {
            "url": job_public_url(job.url),
            "key": key,
            "title": job.title,
            "company": job.company,
            "quick_fit": job.fit,
            "triage_score": None,
            "triage_reason": "Poza triażem",
            "tier": "",
            "status": job.status,
            "salary_b2b_monthly": job.salary_b2b_monthly,
            "salary_meets_threshold": job.salary_meets_threshold,
        }

    def _append_untriaged_rows(
        self,
        rows: list[dict],
        seen: dict,
        ranked_urls: set[str],
        *,
        tier: TierFilter,
        status: StatusFilter,
        fit: FitFilter,
        q: str | None,
    ) -> None:
        if tier == "evaluate":
            return
        for key, job in filter_seen_jobs(seen, status=status, fit=fit, q=q):
            if self._is_job_ranked(key, job, ranked_urls):
                continue
            if tier == "priority":
                continue
            if tier == "skip":
                if job.status != "skipped":
                    continue
            elif tier == "review" and job.status == "skipped":
                continue
            rows.append(self._merge_row(self._untriaged_item(key, job), seen))

    def get_counts(self) -> dict:
        triage = self._load_triage_data()
        queue = self._load_queue_data()
        seen = self.repo.all()
        new_count = sum(1 for j in seen.values() if j.status == "new")
        untriaged = self._untriaged_count(seen, triage)
        if triage:
            priority = triage.get("priority_count", 0)
            review = triage.get("review_count", 0)
            return {
                "priority": priority,
                "review": review,
                "skipped": triage.get("skipped_count", 0),
                "new": new_count,
                "untriaged": untriaged,
                "evaluate_queue": len(queue.get("jobs", [])) if queue else 0,
                "inbox_badge": priority + review + untriaged,
                "has_triage": True,
                "triage_stale": untriaged > 0,
            }
        return {
            "priority": 0,
            "review": 0,
            "skipped": 0,
            "new": new_count,
            "untriaged": 0,
            "evaluate_queue": 0,
            "inbox_badge": new_count,
            "has_triage": False,
            "triage_stale": False,
        }

    def get_evaluate_queue(self) -> dict:
        queue = self._load_queue_data()
        if not queue:
            return {"urls": [], "jobs": []}
        return queue

    def list_jobs(
        self,
        *,
        status: StatusFilter = None,
        fit: FitFilter = None,
        new_only: bool = False,
        tier: TierFilter = None,
        q: str | None = None,
    ) -> dict:
        if tier is not None:
            return self.load_inbox(tier=tier, status=status, fit=fit, q=q)

        seen = self.repo.all()
        rows = [
            self._job_row(key, job)
            for key, job in filter_seen_jobs(
                seen, status=status, fit=fit, q=q, new_only=new_only
            )
        ]
        counts = self._counts_from_seen(seen)
        return {"total": len(rows), "counts": counts, "jobs": rows, "has_triage": False}

    def load_inbox(
        self,
        *,
        tier: TierFilter = None,
        status: StatusFilter = None,
        fit: FitFilter = None,
        q: str | None = None,
    ) -> dict:
        triage = self._load_triage_data()
        seen = self.repo.all()
        queue_urls: set[str] = set()
        if tier == "evaluate":
            queue = self._load_queue_data()
            queue_urls = set(queue.get("urls", [])) if queue else set()

        rows: list[dict] = []

        if triage and triage.get("ranked"):
            ranked_urls = self._ranked_urls(triage)
            for item in triage["ranked"]:
                if not filter_triage_item(
                    item,
                    seen,
                    tier=tier,
                    status=status,
                    fit=fit,
                    q=q,
                    effective_tier=self._effective_tier,
                    effective_status=self._effective_status,
                    queue_urls=queue_urls if tier == "evaluate" else None,
                ):
                    continue
                rows.append(self._merge_row(item, seen))
            self._append_untriaged_rows(
                rows,
                seen,
                ranked_urls,
                tier=tier,
                status=status,
                fit=fit,
                q=q,
            )
        else:
            for key, job in filter_seen_jobs(seen, status=status, fit=fit, q=q):
                item = {
                    "url": job_public_url(job.url),
                    "key": key,
                    "title": job.title,
                    "company": job.company,
                    "quick_fit": job.fit,
                    "triage_score": None,
                    "triage_reason": "",
                    "tier": "",
                    "status": job.status,
                    "salary_b2b_monthly": job.salary_b2b_monthly,
                    "salary_meets_threshold": job.salary_meets_threshold,
                }
                rows.append(self._merge_row(item, seen))

        counts = self.get_counts()
        return {
            "total": len(rows),
            "counts": counts,
            "has_triage": counts["has_triage"],
            "triage_stale": counts.get("triage_stale", False),
            "jobs": rows,
        }

    def present_new_matches(self) -> dict:
        data = self.list_jobs(status="new")
        jobs = data["jobs"]
        c = data["counts"]
        return {
            "title": "New Job Matches",
            "summary": (
                f"Found {len(jobs)} new positions "
                f"({c.get('high', 0)} high, {c.get('medium', 0)} medium, {c.get('low', 0)} low match)."
            ),
            "jobs": jobs,
        }

    def update_job(self, url: str, update: SeenJobUpdate) -> bool:
        fields = {}
        if update.status is not None:
            fields["status"] = update.status
        if update.fit is not None:
            fields["fit"] = update.fit
        if update.skip_reason is not None:
            fields["skip_reason"] = stamp_manual_skip_reason(update.skip_reason)
        if not fields:
            return False
        found = self.repo.get_by_url(url)
        if not found:
            return False
        key, job = found
        canonical_url = job.url or key
        ok = self.repo.update_fields(url, **fields)
        if not ok:
            return False
        self.repo.flush()
        if update.status is not None:
            skip_reason = fields.get("skip_reason")
            if skip_reason is None:
                found = self.repo.get_by_url(url)
                skip_reason = found[1].skip_reason if found else None
            self.sync_job_to_triage(canonical_url, status=update.status, skip_reason=skip_reason)
        return True

    def _find_ranked_item(self, ranked: list[dict], ref: str) -> dict | None:
        ref_vars = set(job_url_lookup_variants(ref))
        for item in ranked:
            item_url = item.get("url", "")
            if not item_url:
                continue
            if item_url == ref or item_url in ref_vars:
                return item
            if set(job_url_lookup_variants(item_url)) & ref_vars:
                return item
        return None

    def sync_job_to_triage(
        self,
        url: str,
        *,
        status: str,
        skip_reason=None,
    ) -> None:
        triage = self._load_triage_data()
        if not triage or not triage.get("ranked"):
            return

        ranked = triage["ranked"]
        item = self._find_ranked_item(ranked, url)
        if item is None:
            return

        item["status"] = status
        if status == "skipped":
            item["tier"] = "skip"
            self._remove_from_evaluate_queue(url)
            if skip_reason is not None:
                item["skip_reason"] = (
                    skip_reason.model_dump()
                    if hasattr(skip_reason, "model_dump")
                    else skip_reason
                )

        triage["priority_count"] = sum(1 for r in ranked if r.get("tier") == "priority")
        triage["review_count"] = sum(1 for r in ranked if r.get("tier") == "review")
        triage["skipped_count"] = sum(1 for r in ranked if r.get("tier") == "skip")
        self.triage_path.write_text(
            json.dumps(triage, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _remove_from_evaluate_queue(self, url: str) -> None:
        queue = self._load_queue_data()
        if not queue:
            return
        urls = queue.get("urls", [])
        jobs = queue.get("jobs", [])
        if url not in urls:
            return
        self.queue_path.write_text(
            json.dumps(
                {
                    "urls": [u for u in urls if u != url],
                    "jobs": [j for j in jobs if j.get("url") != url],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _language_gaps(
        self,
        requirements: list[LanguageRequirement],
        profile_langs: list,
    ) -> list[LanguageRequirement]:
        if not profile_langs:
            return []
        return [
            req
            for req in requirements
            if language_gap(profile_langs, language=req.language, level=req.level)
        ]

    @staticmethod
    def _has_auto_language_skip(job, *, row: dict | None = None) -> bool:
        skip = None
        if row and row.get("skip_reason"):
            skip = row["skip_reason"]
        elif job is not None and job.skip_reason is not None:
            skip = (
                job.skip_reason.model_dump()
                if hasattr(job.skip_reason, "model_dump")
                else job.skip_reason
            )
        if isinstance(skip, dict):
            return skip.get("category") == "auto_language_level"
        return getattr(skip, "category", None) == "auto_language_level"

    def _apply_language_skip(
        self,
        *,
        gaps: list[LanguageRequirement],
        status: str,
        reason: str,
        triage_score: int,
        quick_fit: str,
        job,
        skipped: int,
    ) -> tuple[str, str, int, object | None, str]:
        gap = gaps[0]
        tier = "skip"
        gap_token = gap.token or f"{gap.language}_{gap.level}"
        reason = f"{reason}, {gap_token}" if reason != "generic" else gap_token
        auto_skip_reason = None
        if status == "new":
            status = "skipped"
            skipped += 1
            if job.skip_reason is None:
                auto_skip_reason = build_auto_language_skip_reason(
                    language=gap.language,
                    level=gap.level,
                    triage_score=triage_score,
                    triage_reason=reason,
                    quick_fit=quick_fit,
                    matched_token=gap.token,
                )
        return status, reason, skipped, auto_skip_reason, tier

    def run_triage(self, *, keys: set[str] | None = None) -> dict:
        self.repo.invalidate()
        seen = self.repo.all()
        incremental = bool(keys)
        salary_svc = SalaryService(self.settings)
        profile_langs = load_candidate_languages(self.settings)

        ranked_by_url: dict[str, dict] = {}
        if incremental:
            existing = self._load_triage_data() or {}
            for row in existing.get("ranked", []):
                url = row.get("url")
                if url:
                    ranked_by_url[url] = row

        skipped = 0
        pending_llm: list[tuple[str, str]] = []
        llm_ctx: dict[str, dict] = {}

        if incremental:
            items = [(k, seen[k]) for k in keys if k in seen]
        else:
            items = list(seen.items())

        for key, job in items:
            title = job.title
            company = job.company
            triage_score, reason = score_job(title, company)
            job_data = job.model_dump()
            quick_fit = job.fit
            needs_salary_assess = job.salary_b2b_monthly is None or salary_svc.should_reassess_estimated(
                salary_source=job.salary_source,
                description=job.description,
            )
            if needs_salary_assess and job.status == "new":
                prev_meets = job.salary_meets_threshold
                assessment = salary_svc.assess(
                    title=title,
                    salary=job.salary_raw,
                    description=job.description,
                )
                job_data["salary_raw"] = assessment.salary_raw or job.salary_raw
                job_data["salary_b2b_monthly"] = assessment.monthly_b2b_median
                job_data["salary_source"] = assessment.source
                job_data["salary_meets_threshold"] = assessment.meets_threshold
                if (
                    prev_meets is False
                    and assessment.meets_threshold
                    and job.salary_source == "estimated"
                ):
                    order = ["high", "medium", "low"]
                    idx = order.index(quick_fit)
                    if idx > 0:
                        quick_fit = order[idx - 1]
                        job_data["fit"] = quick_fit
            sal_pen, sal_reason = salary_triage_penalty(job_data, salary_svc)
            triage_score += sal_pen
            if sal_reason:
                reason = f"{reason}, {sal_reason}" if reason != "generic" else sal_reason
            status = job.status
            auto_skip_reason = None

            posting_blob, fetched_desc = ensure_posting_blob(job)
            if fetched_desc:
                job_data["description"] = fetched_desc
            requirements = extract_language_requirements(posting_blob)
            lang_gaps = self._language_gaps(requirements, profile_langs)
            if self._has_auto_language_skip(job):
                tier = "skip"
                status = job.status
            elif lang_gaps:
                status, reason, skipped, auto_skip_reason, tier = self._apply_language_skip(
                    gaps=lang_gaps,
                    status=status,
                    reason=reason,
                    triage_score=triage_score,
                    quick_fit=quick_fit,
                    job=job,
                    skipped=skipped,
                )
            else:
                from app.services.inbox.fit_signals import extract_job_signals

                job_signals = extract_job_signals(title=title, description=posting_blob)
                tier = assign_tier(
                    quick_fit=quick_fit,
                    triage_score=triage_score,
                    salary_meets_threshold=job_data.get("salary_meets_threshold"),
                    pi_score=job.pi_score,
                    pi_verdict=job.pi_verdict,
                    job_signals=job_signals,
                )
                if tier == "skip" and status == "new":
                    status = "skipped"
                    skipped += 1
                    auto_skip_reason = build_auto_skip_reason(
                        quick_fit=quick_fit,
                        triage_score=triage_score,
                        triage_reason=reason,
                    )

            updates: dict = {}
            for field in (
                "salary_raw",
                "salary_b2b_monthly",
                "salary_source",
                "salary_meets_threshold",
                "description",
                "fit",
            ):
                if job_data.get(field) != getattr(job, field):
                    updates[field] = job_data.get(field)
            if status != job.status:
                updates["status"] = status
            if auto_skip_reason is not None:
                updates["skip_reason"] = auto_skip_reason
            if updates:
                self.repo.upsert(key, job.model_copy(update=updates))

            row: dict = {
                "url": job.url or key,
                "title": title,
                "company": company,
                "quick_fit": quick_fit,
                "triage_score": triage_score,
                "triage_reason": reason,
                "tier": tier,
                "status": status,
                "salary_b2b_monthly": job_data.get("salary_b2b_monthly"),
                "salary_meets_threshold": job_data.get("salary_meets_threshold"),
                "pi_score": job.pi_score,
                "pi_verdict": job.pi_verdict,
                "pi_app": job.pi_app,
            }
            if auto_skip_reason is not None:
                row["skip_reason"] = auto_skip_reason.model_dump()
            elif job.skip_reason:
                row["skip_reason"] = job.skip_reason.model_dump()
            row_url = job.url or key
            ranked_by_url[row_url] = row

            if (
                profile_langs
                and not lang_gaps
                and not requirements
                and job.status == "new"
                and len(posting_blob) >= 80
            ):
                pending_llm.append((key, posting_blob))
                llm_ctx[key] = {
                    "triage_score": triage_score,
                    "reason": reason,
                    "quick_fit": quick_fit,
                    "job": job,
                    "job_data": dict(job_data),
                    "row_url": row_url,
                }

        llm_extracts = _run_async_from_sync(
            batch_extract_language_llm(pending_llm, self.settings)
        )
        for key, llm_reqs in llm_extracts.items():
            ctx = llm_ctx.get(key)
            if not ctx or ctx["job"].status != "new":
                continue
            gaps = self._language_gaps(llm_reqs, profile_langs)
            if not gaps:
                continue
            row = ranked_by_url.get(ctx["row_url"])
            if row is None:
                continue
            job = ctx["job"]
            status, reason, skipped, auto_skip_reason, tier = self._apply_language_skip(
                gaps=gaps,
                status=row["status"],
                reason=ctx["reason"],
                triage_score=ctx["triage_score"],
                quick_fit=ctx["quick_fit"],
                job=job,
                skipped=skipped,
            )
            row["tier"] = tier
            row["status"] = status
            row["triage_reason"] = reason
            if auto_skip_reason is not None:
                row["skip_reason"] = auto_skip_reason.model_dump()
            updates: dict = {}
            job_data = ctx["job_data"]
            for field in (
                "salary_raw",
                "salary_b2b_monthly",
                "salary_source",
                "salary_meets_threshold",
                "description",
            ):
                if job_data.get(field) != getattr(job, field):
                    updates[field] = job_data.get(field)
            if status != job.status:
                updates["status"] = status
            if auto_skip_reason is not None:
                updates["skip_reason"] = auto_skip_reason
            if updates:
                self.repo.upsert(key, job.model_copy(update=updates))

        ranked = list(ranked_by_url.values())

        ranked.sort(
            key=lambda x: (
                fit_sort_key(x["quick_fit"]),
                -(x["triage_score"] or 0),
                -(x.get("pi_score") or 0),
            )
        )

        priority = [r for r in ranked if r["tier"] == "priority"]
        review = [r for r in ranked if r["tier"] == "review"]
        top10 = [
            r
            for r in (priority + review)
            if r.get("status") != "skipped"
            and not self._has_auto_language_skip(None, row=r)
        ][:10]
        skipped_count = sum(1 for r in ranked if r.get("tier") == "skip")

        write_json(
            self.triage_path,
            {
                "skipped_count": skipped_count,
                "priority_count": len(priority),
                "review_count": len(review),
                "ranked": ranked,
            },
        )
        write_json(
            self.queue_path,
            {"urls": [r["url"] for r in top10], "jobs": top10},
        )
        self.repo.flush()

        return {
            "skipped": skipped,
            "priority": len(priority),
            "review": len(review),
            "top10": top10,
        }
