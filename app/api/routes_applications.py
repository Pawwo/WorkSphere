from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.models.applications import ApplicationActivityCreate, ApplicationUpdate, ApplyAsyncResponse
from app.models.pipeline import HIRING_STAGES, PIPELINE_STAGES, STAGE_PROGRESS
from app.config import get_settings
from app.llm.client import BielikClient
from app.services.application_service import ApplicationService
from app.services.cv.renderer_factory import get_pdf_compiler
from app.services.latex_service import LatexService
from app.services.pipeline_service import PipelineService
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("/meta")
async def applications_meta():
    return {
        "pipeline_stages": PIPELINE_STAGES,
        "stage_progress": STAGE_PROGRESS,
        "hiring_stages": HIRING_STAGES,
    }


@router.get("")
async def list_applications(
    hiring_stage: str | None = None,
    pipeline_stage: str | None = None,
    limit: int = Query(100, le=500),
):
    rows = await ApplicationService().list(
        hiring_stage=hiring_stage,
        pipeline_stage=pipeline_stage,
        limit=limit,
    )
    return {"total": len(rows), "applications": rows}


@router.get("/counts")
async def application_counts():
    from app.storage.db import Database
    from app.config import get_settings

    counts = await Database(get_settings().db_path).count_applications_by_hiring_stage()
    total = sum(counts.values())
    active = counts.get("ready_to_send", 0) + counts.get("screening", 0)
    return {"by_hiring_stage": counts, "total": total, "tracker_badge": active}


@router.get("/{app_id}")
async def get_application(app_id: int):
    record = await ApplicationService().get(app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")
    return record.model_dump()


@router.patch("/{app_id}")
async def update_application(app_id: int, update: ApplicationUpdate):
    svc = ApplicationService()
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    ok = await svc.update(app_id, **fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Application not found")
    record = await svc.get(app_id)
    return record.model_dump() if record else {"ok": True}


@router.post("/{app_id}/activities")
async def add_activity(app_id: int, body: ApplicationActivityCreate):
    svc = ApplicationService()
    from app.storage.db import Database
    from app.config import get_settings

    row = await Database(get_settings().db_path).get_application(app_id)
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    await svc.add_activity(
        app_id,
        kind=body.kind,
        body=body.body,
        author=body.author,
    )
    return {"ok": True}


async def _run_proceed_task(task_id: str, app_id: int, compile_pdf: bool) -> None:
    tasks = TaskService.get()
    pipeline = PipelineService()
    try:
        await pipeline.db.update_application(app_id, task_id=task_id, pipeline_status="running")
        resp = await pipeline.proceed(
            app_id,
            compile_pdf=compile_pdf,
            on_progress=tasks.progress_callback(task_id),
        )
        await tasks.complete(
            task_id,
            {"application_id": app_id, "stage": "done", "response": resp.model_dump()},
        )
    except Exception as exc:
        await pipeline.db.update_application(app_id, pipeline_status="failed")
        await pipeline.db.add_application_activity(app_id, kind="stage_log", body=f"Błąd: {exc}")
        await tasks.fail(task_id, str(exc))


@router.get("/{app_id}/preflight")
async def application_preflight(app_id: int):
    row = await ApplicationService().db.get_application(app_id)
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    settings = get_settings()
    pipeline_running = row.get("pipeline_status") == "running"
    llm = await BielikClient(settings).healthcheck_extended(
        force_probe=not pipeline_running,
    )
    ready = bool(llm.get("ok") and llm.get("inference_ok") is not False)
    latex_svc = LatexService(settings.repo_root, settings=settings)
    latex = latex_svc.tools_available()
    cv_renderer = (settings.cv_renderer or "html").strip().lower()
    if cv_renderer == "html":
        pdf_tools = get_pdf_compiler(settings).tools_available()
        ready_for_pdf = bool(pdf_tools.get("playwright"))
        latex = {**latex, "cv_renderer": "html", "pdf_tools": pdf_tools}
    else:
        ready_for_pdf = bool(latex.get("lualatex") and latex.get("xelatex"))
        latex = {**latex, "cv_renderer": cv_renderer}
    return {
        "application_id": app_id,
        "llm": llm,
        "cv_renderer": cv_renderer,
        "latex": {**latex, "ok": ready_for_pdf},
        "ready_for_draft": ready,
        "ready_for_pdf": ready_for_pdf,
        "interview_prep_enabled": settings.pipeline_interview_prep_enabled,
    }


@router.post("/{app_id}/proceed", response_model=ApplyAsyncResponse)
async def proceed_application(app_id: int, compile_pdf: bool = True):
    row = await ApplicationService().db.get_application(app_id)
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    if row.get("pipeline_stage") == "done" and row.get("pipeline_status") == "done":
        raise HTTPException(status_code=400, detail="Application already completed")
    task_id = await TaskService.get().create("apply")
    asyncio.create_task(_run_proceed_task(task_id, app_id, compile_pdf))
    return ApplyAsyncResponse(
        task_id=task_id,
        application_id=app_id,
        kind="apply",
        status="running",
    )


@router.post("/{app_id}/retry/{stage}")
async def retry_stage(app_id: int, stage: str, compile_pdf: bool = True):
    try:
        resp = await PipelineService().retry_stage(app_id, stage, compile_pdf=compile_pdf)
        return {"ok": True, "application_id": app_id, "response": resp.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{app_id}/documents")
async def list_documents(app_id: int):
    record = await ApplicationService().get(app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")
    docs = []
    for f in [record.cv_file, record.cover_file, record.pdf_cv, record.pdf_cover, record.interview_prep_file]:
        if f:
            docs.append({"path": f, "name": f.split("/")[-1]})
    return {"documents": docs, "manifest": record.manifest}
