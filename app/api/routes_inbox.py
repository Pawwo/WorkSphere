from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from app.models.jobs import SeenJobUpdate
from app.models.tasks import TaskCreateResponse
from app.services.inbox_service import InboxService
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


async def _run_triage_task(task_id: str) -> None:
    tasks = TaskService.get()
    try:
        loop = asyncio.get_running_loop()
        svc = InboxService()
        result = await loop.run_in_executor(None, svc.run_triage)
        counts = svc.get_counts()
        await tasks.complete(task_id, {**result, "counts": counts})
    except Exception as exc:
        await tasks.fail(task_id, str(exc))


@router.get("")
async def inbox_list(
    tier: str | None = Query(None, pattern="^(priority|review|skip|evaluate)$"),
    status: str | None = Query(None, pattern="^(new|skipped|evaluated)$"),
    fit: str | None = Query(None, pattern="^(high|medium|low)$"),
    q: str | None = None,
):
    if tier:
        return InboxService().load_inbox(tier=tier, status=status, fit=fit, q=q)
    return InboxService().list_jobs(status=status, fit=fit, q=q)


@router.get("/counts")
async def inbox_counts():
    return InboxService().get_counts()


@router.get("/evaluate-queue")
async def inbox_evaluate_queue():
    return InboxService().get_evaluate_queue()


@router.post("/triage")
async def inbox_triage():
    result = InboxService().run_triage()
    counts = InboxService().get_counts()
    return {**result, "counts": counts}


@router.post("/triage/async", response_model=TaskCreateResponse)
async def inbox_triage_async():
    task_id = await TaskService.get().create("triage")
    asyncio.create_task(_run_triage_task(task_id))
    return TaskCreateResponse(task_id=task_id, kind="triage", status="running")


@router.get("/new-matches")
async def inbox_new_matches():
    return InboxService().present_new_matches()


@router.patch("/{url:path}")
async def inbox_update_job(url: str, update: SeenJobUpdate):
    ok = InboxService().update_job(url, update)
    if not ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}
