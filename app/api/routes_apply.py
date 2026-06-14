from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.models.apply import ApplyRequest, ApplyResponse
from app.models.applications import ApplyAsyncRequest, ApplyAsyncResponse
from app.services.apply_service import ApplyService
from app.services.pipeline_service import PipelineService
from app.services.task_service import TaskService
from app.storage.db import Database

router = APIRouter(prefix="/api/apply", tags=["apply"])


@router.post("", response_model=ApplyResponse)
async def apply_to_job(request: ApplyRequest):
    if not request.url and not request.text:
        raise HTTPException(status_code=400, detail="Podaj url lub text ogłoszenia")
    try:
        return await ApplyService().run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _run_apply_task(
    task_id: str,
    request: ApplyAsyncRequest,
    application_id: int,
    run_id: int,
) -> None:
    tasks = TaskService.get()
    apply_req = ApplyRequest(
        url=request.url,
        text=request.text,
        proceed=request.proceed,
        compile_pdf=request.compile_pdf,
    )
    try:
        pipeline = PipelineService()
        from app.services.pipeline_service import PipelineContext

        ctx = PipelineContext(
            request=apply_req,
            application_id=application_id,
            run_id=run_id,
            task_id=task_id,
            bundle=pipeline.apply._read_profile_bundle(),
        )
        result = await pipeline.run_async(
            apply_req,
            task_id,
            on_progress=tasks.progress_callback(task_id),
            ctx=ctx,
        )
        if result.get("status") == "waiting":
            await tasks.wait_for_input(task_id, result)
        else:
            await tasks.complete(task_id, result)
    except Exception as exc:
        await tasks.fail(task_id, str(exc))


@router.post("/async", response_model=ApplyAsyncResponse)
async def apply_async(request: ApplyAsyncRequest):
    if not request.url and not request.text:
        raise HTTPException(status_code=400, detail="Podaj url lub text ogłoszenia")
    task_id = await TaskService.get().create("apply")
    pipeline = PipelineService()
    apply_req = ApplyRequest(
        url=request.url,
        text=request.text,
        proceed=request.proceed,
        compile_pdf=request.compile_pdf,
    )
    ctx = await pipeline.create_application(apply_req, task_id=task_id)
    await pipeline.db.update_application(ctx.application_id, task_id=task_id, pipeline_status="running")
    asyncio.create_task(_run_apply_task(task_id, request, ctx.application_id, ctx.run_id))
    return ApplyAsyncResponse(
        task_id=task_id,
        application_id=ctx.application_id,
        kind="apply",
        status="running",
    )


@router.get("/runs")
async def list_runs(limit: int = 20):
    db = Database(get_settings().db_path)
    return {"runs": await db.list_apply_runs(limit=limit)}


@router.get("/runs/{run_id}")
async def get_run(run_id: int):
    db = Database(get_settings().db_path)
    row = await db.get_apply_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return row
