from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.models.jobs import ScrapeBatchRequest, ScrapeBatchResponse, ScrapeRequest, ScrapeResponse
from app.models.tasks import TaskCreateResponse
from app.config import get_settings
from app.services.scrape.portals import load_portal_lists, resolve_portals_for_request
from app.services.scrape_service import ScrapeService
from app.services.search_queries import parse_search_queries
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


@router.post("", response_model=ScrapeResponse)
async def scrape_jobs(request: ScrapeRequest):
    try:
        service = ScrapeService()
        return await service.run(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _run_scrape_task(task_id: str, request: ScrapeRequest) -> None:
    tasks = TaskService.get()
    try:
        result = await ScrapeService().run(
            request,
            on_progress=tasks.progress_callback(task_id),
        )
        await tasks.complete(task_id, result.model_dump())
    except Exception as exc:
        await tasks.fail(task_id, str(exc))


@router.post("/async", response_model=TaskCreateResponse)
async def scrape_jobs_async(request: ScrapeRequest):
    task_id = await TaskService.get().create("scrape")
    asyncio.create_task(_run_scrape_task(task_id, request))
    return TaskCreateResponse(task_id=task_id, kind="scrape", status="running")


@router.get("/batch/preview")
async def scrape_batch_preview(
    broad: bool = False,
    max_categories: int | None = None,
    append_city: bool = True,
):
    settings = get_settings()
    if max_categories is None:
        max_categories = 99 if broad else 3
    service = ScrapeService()
    queries = service.resolve_batch_queries(
        ScrapeBatchRequest(
            broad=broad,
            max_categories=max_categories,
            append_city=append_city,
        )
    )
    parsed = parse_search_queries()
    categories = [c["name"] for c in parsed.get("categories", [])[:max_categories]]
    batch_portals = resolve_portals_for_request(
        settings,
        broad=False,
        portal_profile=settings.scrapers_default_portal_profile,
    )
    return {
        "queries": queries,
        "count": len(queries),
        "categories": categories,
        "max_categories": max_categories,
        "source": "search-queries.md" if categories else ("wizard" if queries else "brak"),
        "portals": batch_portals,
        "portal_profile": settings.scrapers_default_portal_profile,
    }


@router.post("/batch", response_model=ScrapeBatchResponse)
async def scrape_jobs_batch(request: ScrapeBatchRequest):
    try:
        return await ScrapeService().run_batch(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _run_scrape_batch_task(task_id: str, request: ScrapeBatchRequest) -> None:
    tasks = TaskService.get()
    try:
        result = await ScrapeService().run_batch(
            request,
            on_progress=tasks.progress_callback(task_id),
        )
        await tasks.complete(task_id, result.model_dump())
    except Exception as exc:
        await tasks.fail(task_id, str(exc))


@router.post("/batch/async", response_model=TaskCreateResponse)
async def scrape_jobs_batch_async(request: ScrapeBatchRequest):
    service = ScrapeService()
    if not service.resolve_batch_queries(request):
        raise HTTPException(
            status_code=400,
            detail="Brak zapytań. Uzupełnij search-queries.md lub sekcję 9 wizarda.",
        )
    task_id = await TaskService.get().create("scrape_batch")
    asyncio.create_task(_run_scrape_batch_task(task_id, request))
    return TaskCreateResponse(task_id=task_id, kind="scrape_batch", status="running")
