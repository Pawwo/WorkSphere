from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, List, Optional

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.models.jobs import (
    JobCard,
    PortalError,
    ScrapeBatchQueryResult,
    ScrapeBatchRequest,
    ScrapeBatchResponse,
    ScrapeRequest,
    ScrapeResponse,
    ScrapeResultItem,
    SearchMeta,
    SearchResponse,
    SeenJobEntry,
)
from app.services.fit_utils import sort_by_fit
from app.services.highlights_service import enrich_highlights_for_new_jobs
from app.services.salary_service import SalaryService
from app.services.scrape.batch_context import BatchContext
from app.services.scrape.dedup import identity_keys_from_seen, job_identity
from app.services.scrape.fit import fit_jobs_parallel
from app.services.scrape.freshness import effective_days, is_fresh, portal_strict_freshness
from app.services.scrape.portal_routing import portals_for_query
from app.services.scrape.portals import normalize_portal, resolve_portals_for_request
from app.services.scrape.posting_extract import description_for_storage
from app.services.scrape.queries import resolve_batch_queries as build_batch_queries
from app.services.search_queries import resolve_linkedin_queries
from app.scrapers.bun_cli import BunCLIError, BunCLIWrapper
from app.storage.db import Database
from app.storage.files import load_tracker_keys, read_profile_excerpt, seen_key, today_iso
from app.storage.job_repository import JobRepository

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, str], Awaitable[None]]


class ScrapeService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.cli = BunCLIWrapper(self.settings)
        self.llm = BielikClient(self.settings)
        self.salary = SalaryService(self.settings)
        self.db = Database(self.settings.db_path)
        self._file_lock = asyncio.Lock()

    def _resolve_query(self, request: ScrapeRequest) -> str:
        if request.query:
            return request.query
        if request.focus:
            return request.focus
        from app.services.search_queries import resolve_scrape_queries

        queries = resolve_scrape_queries(broad=False, max_categories=1)
        return queries[0] if queries else ""

    def _resolve_portals(self, request: ScrapeRequest, *, is_batch: bool = False) -> List[str]:
        profile = self.settings.scrapers_default_portal_profile
        return resolve_portals_for_request(
            self.settings,
            broad=request.broad,
            explicit_portals=request.portals,
            portal_profile=profile if not request.portals else None,
        )

    def _scrape_days(self, request_days: int | None) -> int:
        configured = request_days or self.settings.scrapers_default_days
        return effective_days(self.settings.scrapers_max_age_hours, configured)

    def resolve_batch_queries(self, request: ScrapeBatchRequest) -> List[str]:
        return build_batch_queries(self.settings, request)

    def _job_is_fresh(self, job: JobCard, portal: str | None = None) -> bool:
        strict = (
            portal_strict_freshness(
                portal or "",
                global_strict=self.settings.scrapers_strict_freshness,
                portal_overrides=self.settings.scrapers_portal_strict_freshness,
            )
            if portal
            else self.settings.scrapers_strict_freshness
        )
        return is_fresh(
            job.date,
            max_age_hours=self.settings.scrapers_max_age_hours,
            strict=strict,
        )

    def _portals_for_query(
        self,
        base_portals: List[str],
        query: str,
        *,
        is_batch: bool,
    ) -> List[str]:
        if is_batch and self.settings.scrapers_smart_portal_routing:
            return portals_for_query(
                base_portals,
                query,
                smart_routing=True,
            )
        return list(base_portals)

    async def _scrape_portals_for_query(
        self,
        query: str,
        portals: List[str],
        *,
        days: int,
        limit: int,
        broad: bool,
        is_batch: bool = False,
        batch_ctx: BatchContext | None = None,
    ) -> tuple[List[tuple[str, SearchResponse | BunCLIError]], List[PortalError]]:
        parallel_results: List[tuple[str, SearchResponse | BunCLIError]] = []
        portal_errors: List[PortalError] = []

        linkedin_portals = [p for p in portals if normalize_portal(p) == "linkedin-pl"]
        other_portals = [p for p in portals if normalize_portal(p) != "linkedin-pl"]

        if other_portals:
            parallel_results.extend(
                await self.cli.search_parallel_tiered(
                    other_portals,
                    query,
                    days=days,
                    limit=limit,
                    max_age_hours=self.settings.scrapers_max_age_hours,
                    is_batch=is_batch,
                )
            )

        if is_batch:
            li_subquery_cap = max(1, self.settings.scrapers_linkedin_batch_subqueries)
            li_queries = [query]
        else:
            li_subquery_cap = 5
            li_queries = resolve_linkedin_queries() if broad else [query]

        for portal in linkedin_portals:
            merged_cards = []
            seen_urls: set[str] = set()
            had_error: Optional[PortalError] = None
            per_query_limit = max(10, limit // max(1, len(li_queries)))

            async def _run_linkedin_queries() -> None:
                nonlocal had_error, merged_cards, seen_urls
                for li_q in li_queries[:li_subquery_cap]:
                    try:
                        outcome = await self.cli.search(
                            portal,
                            li_q,
                            days=days,
                            limit=per_query_limit,
                            max_age_hours=self.settings.scrapers_max_age_hours,
                        )
                        for job in outcome.results:
                            if job.url not in seen_urls and self._job_is_fresh(job, portal):
                                seen_urls.add(job.url)
                                merged_cards.append(job)
                    except BunCLIError as exc:
                        had_error = PortalError(portal=portal, code=exc.code, message=str(exc))
                    except Exception as exc:
                        had_error = PortalError(portal=portal, code="API_ERROR", message=str(exc))

            if batch_ctx is not None:
                async with batch_ctx.linkedin_sem:
                    await _run_linkedin_queries()
            else:
                await _run_linkedin_queries()

            if merged_cards:
                parallel_results.append(
                    (
                        portal,
                        SearchResponse(
                            meta=SearchMeta(total=len(merged_cards), page=1, perPage=len(merged_cards)),
                            results=merged_cards[:limit],
                        ),
                    )
                )
            elif had_error:
                portal_errors.append(had_error)
                parallel_results.append(
                    (portal, BunCLIError(portal, had_error.message, code=had_error.code))
                )

        for portal, outcome in parallel_results:
            if isinstance(outcome, BunCLIError):
                portal_errors.append(PortalError(portal=portal, code=outcome.code, message=str(outcome)))

        return parallel_results, portal_errors

    async def _process_results(
        self,
        *,
        parallel_results: List[tuple[str, SearchResponse | BunCLIError]],
        portals_used: List[str],
        seen: dict,
        known_identities: set[tuple[str, str]],
        repo: JobRepository,
        profile_excerpt: str,
        llm_ok: bool,
        use_llm_fit: bool,
        portal_new_counts: dict[str, int],
        portal_found_counts: dict[str, int],
    ) -> tuple[List[ScrapeResultItem], int, int, int, int, int]:
        pending_jobs: List[tuple[JobCard, str]] = []
        total_found = 0
        skipped_duplicates = 0
        skipped_stale = 0
        skipped_already_seen = 0
        skipped_reject = 0
        session_identities: set[tuple[str, str]] = set()

        from app.services.keyword_triage import is_reject_job

        for portal, outcome in parallel_results:
            if isinstance(outcome, BunCLIError):
                logger.warning("Portal %s failed: %s", portal, outcome)
                continue
            portal_key = normalize_portal(portal)
            portal_found_counts[portal_key] = portal_found_counts.get(portal_key, 0) + len(
                outcome.results
            )
            for job in outcome.results:
                total_found += 1
                if not self._job_is_fresh(job, portal):
                    skipped_stale += 1
                    continue
                key = seen_key(job.url, job.company or "", job.title)
                if key in seen:
                    skipped_already_seen += 1
                    continue
                ident = job_identity(job.company or "", job.title)
                if ident and (ident in known_identities or ident in session_identities):
                    skipped_duplicates += 1
                    continue
                if ident:
                    session_identities.add(ident)
                if is_reject_job(job.title, job.company or ""):
                    skipped_reject += 1
                    continue
                pending_jobs.append((job, portal))

        fit_results = await fit_jobs_parallel(
            self,
            pending_jobs,
            profile_excerpt,
            llm_ok,
            allow_llm=use_llm_fit,
        )

        all_new: List[ScrapeResultItem] = []
        for (job, portal), (fit, assessment) in zip(pending_jobs, fit_results):
            key = seen_key(job.url, job.company or "", job.title)
            portal_key = normalize_portal(portal)
            stored_desc = (
                description_for_storage(
                    job.description or "",
                    portal=portal_key,
                    url=job.url,
                )
                if (job.description or "").strip()
                else None
            )
            entry = SeenJobEntry(
                title=job.title,
                company=job.company or "",
                url=job.url,
                description=stored_desc or None,
                first_seen=today_iso(),
                fit=fit,  # type: ignore[arg-type]
                status="new",
                location=job.location,
                deadline=job.deadline,
                portal=portal,
                salary_raw=assessment.salary_raw or job.salary,
                salary_b2b_monthly=assessment.monthly_b2b_median,
                salary_source=assessment.source,
                salary_meets_threshold=assessment.meets_threshold,
            )
            repo.upsert(key, entry)
            seen[key] = entry
            ident = job_identity(job.company or "", job.title)
            if ident:
                known_identities.add(ident)
            portal_new_counts[portal_key] = portal_new_counts.get(portal_key, 0) + 1
            all_new.append(
                ScrapeResultItem(
                    fit=fit,  # type: ignore[arg-type]
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    deadline=job.deadline,
                    url=job.url,
                    portal=portal,
                    description=(job.description or "")[:300] or None,
                )
            )

        return all_new, total_found, skipped_duplicates, skipped_stale, skipped_already_seen, skipped_reject

    async def run_batch(
        self,
        request: ScrapeBatchRequest,
        on_progress: Optional[ProgressFn] = None,
    ) -> ScrapeBatchResponse:
        queries = self.resolve_batch_queries(request)
        if not queries:
            raise ValueError(
                "Brak zapytań. Uzupełnij data/profile/search-queries.md lub sekcję 9 wizarda."
            )

        use_llm_fit = self.settings.scrapers_batch_fit_mode != "fast"
        if use_llm_fit and on_progress:
            await on_progress("init", 3, "Sprawdzam dostępność LLM…")
        if use_llm_fit:
            await self.llm.wait_until_ready(probe=True)

        llm_ok = await self.llm.is_ready(probe=True)
        batch_ctx = BatchContext(self.settings)

        per_query: List[ScrapeBatchQueryResult] = []
        total_found = 0
        new_count = 0
        all_new_jobs: List[ScrapeResultItem] = []
        all_portal_errors: List[PortalError] = []
        n = len(queries)
        parallelism = max(1, self.settings.scrapers_batch_query_parallelism)
        sem = asyncio.Semaphore(parallelism)

        async def run_one(i: int, query: str) -> ScrapeResponse:
            async with sem:
                if on_progress:
                    base_pct = int(100 * i / n)

                    async def scaled_progress(
                        stage: str, pct: int, msg: str, *, _base=base_pct, _q=query, _idx=i
                    ) -> None:
                        overall = min(99, _base + int(pct / n))
                        await on_progress(
                            stage,
                            overall,
                            f"[{_idx + 1}/{n}] {_q}: {msg}",
                        )

                    progress_fn: Optional[ProgressFn] = scaled_progress
                else:
                    progress_fn = None

                run_req = ScrapeRequest(
                    query=query,
                    broad=request.broad,
                    days=request.days,
                    limit=request.limit,
                    portals=request.portals,
                )
                return await self.run(
                    run_req,
                    on_progress=progress_fn,
                    llm_ok=llm_ok,
                    defer_highlights=True,
                    batch_ctx=batch_ctx,
                    is_batch=True,
                )

        results = await asyncio.gather(*(run_one(i, q) for i, q in enumerate(queries)))

        await batch_ctx.flush()

        for query, result in zip(queries, results):
            total_found += result.total_found
            new_count += result.new_count
            all_new_jobs.extend(result.results)
            all_portal_errors.extend(result.portal_errors)
            per_query.append(
                ScrapeBatchQueryResult(
                    query=query,
                    run_id=result.run_id,
                    total_found=result.total_found,
                    new_count=result.new_count,
                )
            )

        all_new_jobs = sort_by_fit(all_new_jobs, lambda x: x.fit)

        if all_new_jobs:
            await enrich_highlights_for_new_jobs(all_new_jobs, settings=self.settings)
            for item in all_new_jobs:
                key = seen_key(item.url, item.company or "", item.title)
                entry = batch_ctx.seen.get(key)
                if entry and entry.highlights:
                    item.highlights = entry.highlights

        if on_progress:
            await on_progress("done", 100, f"Zakończono {n} zapytań, {new_count} nowych ofert")

        from app.services.post_batch_service import run_post_batch_async

        triage_keys = {
            seen_key(item.url, item.company or "", item.title)
            for item in all_new_jobs
            if item.url
        }
        await run_post_batch_async(
            self.settings,
            on_progress=on_progress,
            triage_keys=triage_keys or None,
        )

        return ScrapeBatchResponse(
            queries_run=n,
            total_found=total_found,
            new_count=new_count,
            results=per_query,
            new_jobs=all_new_jobs,
            portal_errors=all_portal_errors,
        )

    async def run(
        self,
        request: ScrapeRequest,
        on_progress: Optional[ProgressFn] = None,
        *,
        llm_ok: Optional[bool] = None,
        defer_highlights: bool = False,
        batch_ctx: BatchContext | None = None,
        is_batch: bool = False,
    ) -> ScrapeResponse:
        query = self._resolve_query(request).strip()
        if not query:
            raise ValueError(
                "Brak zapytania. Podaj query w formularzu lub uzupełnij search-queries.md / setup."
            )
        base_portals = self._resolve_portals(request, is_batch=is_batch)
        portals = self._portals_for_query(base_portals, query, is_batch=is_batch)
        if batch_ctx and batch_ctx.rocketjobs_circuit_open:
            portals = [p for p in portals if normalize_portal(p) != "rocketjobs"]
        if batch_ctx and batch_ctx.praca_pl_circuit_open:
            portals = [p for p in portals if normalize_portal(p) != "praca-pl"]
        days = self._scrape_days(request.days)
        limit = request.limit or self.settings.scrapers_default_limit

        if on_progress:
            await on_progress("init", 5, f"Zapytanie: {query}")

        use_llm_fit = not is_batch or self.settings.scrapers_batch_fit_mode != "fast"
        if use_llm_fit and not is_batch and on_progress:
            await on_progress("init", 8, "Sprawdzam dostępność LLM…")

        profile_excerpt = read_profile_excerpt(self.settings)
        if llm_ok is None:
            llm_ok = await self.llm.is_ready(probe=True)

        if on_progress:
            await on_progress(
                "scrape",
                15,
                f"Portale ({len(portals)}): {', '.join(portals)}",
            )

        parallel_results, portal_errors = await self._scrape_portals_for_query(
            query,
            portals,
            days=days,
            limit=limit,
            broad=request.broad,
            is_batch=is_batch,
            batch_ctx=batch_ctx,
        )

        if batch_ctx:
            for portal, outcome in parallel_results:
                if not isinstance(outcome, BunCLIError) or outcome.code != "TIMEOUT":
                    continue
                if normalize_portal(portal) == "rocketjobs":
                    batch_ctx.record_rocketjobs_timeout()
                elif normalize_portal(portal) == "praca-pl":
                    batch_ctx.record_praca_pl_timeout()

        if on_progress:
            ok_count = sum(1 for _, o in parallel_results if not isinstance(o, BunCLIError))
            await on_progress("scrape", 70, f"Portale: {ok_count}/{len(portals)} OK")
            await on_progress("process", 75, "Przetwarzanie wyników")

        portal_new_counts: dict[str, int] = {normalize_portal(p): 0 for p in portals}
        portal_found_counts: dict[str, int] = {normalize_portal(p): 0 for p in portals}
        skipped_duplicates = 0
        skipped_stale = 0
        skipped_already_seen = 0
        skipped_reject = 0
        total_found = 0
        all_new: List[ScrapeResultItem] = []

        if batch_ctx is not None:
            async with batch_ctx._lock:
                all_new, total_found, skipped_duplicates, skipped_stale, skipped_already_seen, skipped_reject = (
                    await self._process_results(
                        parallel_results=parallel_results,
                        portals_used=portals,
                        seen=batch_ctx.seen,
                        known_identities=batch_ctx.known_identities,
                        repo=batch_ctx.repo,
                        profile_excerpt=profile_excerpt,
                        llm_ok=llm_ok,
                        use_llm_fit=use_llm_fit,
                        portal_new_counts=portal_new_counts,
                        portal_found_counts=portal_found_counts,
                    )
                )
        else:
            async with self._file_lock:
                repo = JobRepository(self.settings.seen_jobs_path)
                seen = repo.all()
                tracker_keys = load_tracker_keys(self.settings.tracker_path)
                known_identities = identity_keys_from_seen(seen)
                for company_l, title_l in tracker_keys:
                    ident = job_identity(company_l, title_l)
                    if ident:
                        known_identities.add(ident)
                all_new, total_found, skipped_duplicates, skipped_stale, skipped_already_seen, skipped_reject = (
                    await self._process_results(
                        parallel_results=parallel_results,
                        portals_used=portals,
                        seen=seen,
                        known_identities=known_identities,
                        repo=repo,
                        profile_excerpt=profile_excerpt,
                        llm_ok=llm_ok,
                        use_llm_fit=use_llm_fit,
                        portal_new_counts=portal_new_counts,
                        portal_found_counts=portal_found_counts,
                    )
                )
                if on_progress:
                    await on_progress("save", 90, "Zapis wyników")
                repo.flush()

        all_new = sort_by_fit(all_new, lambda x: x.fit)

        if all_new and not defer_highlights:
            await enrich_highlights_for_new_jobs(all_new, settings=self.settings)
            async with self._file_lock:
                repo = JobRepository(self.settings.seen_jobs_path)
                seen = repo.all()
                for item in all_new:
                    key = seen_key(item.url, item.company or "", item.title)
                    entry = seen.get(key)
                    if entry and entry.highlights:
                        item.highlights = entry.highlights

        portal_metrics = {
            normalize_portal(p): {
                "found": portal_found_counts.get(normalize_portal(p), 0),
                "new": portal_new_counts.get(normalize_portal(p), 0),
            }
            for p in portals
        }
        for portal, outcome in parallel_results:
            if isinstance(outcome, BunCLIError):
                key = normalize_portal(portal)
                entry = portal_metrics.setdefault(key, {"found": 0, "new": 0})
                entry["error"] = {"code": outcome.code, "message": str(outcome)}

        portal_status = json.dumps(
            {
                "ok": [p for p, o in parallel_results if not isinstance(o, BunCLIError)],
                "errors": [e.model_dump() for e in portal_errors],
                "portal_new_counts": portal_new_counts,
                "portal_found_counts": portal_found_counts,
                "portals": portal_metrics,
                "portals_used": portals,
                "skipped_duplicates": skipped_duplicates,
                "skipped_stale": skipped_stale,
                "skipped_already_seen": skipped_already_seen,
                "skipped_reject": skipped_reject,
            },
            ensure_ascii=False,
        )
        run_id = await self.db.create_scrape_run(
            query=query,
            broad=request.broad,
            portals=",".join(portals),
            total_found=total_found,
            new_count=len(all_new),
            portal_status=portal_status,
        )

        return ScrapeResponse(
            run_id=run_id,
            total_found=total_found,
            new_count=len(all_new),
            results=all_new,
            portal_errors=portal_errors,
        )
