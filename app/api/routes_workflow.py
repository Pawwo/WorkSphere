from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.get("/inbox")
async def workflow_inbox(
    tier: str | None = Query(None, pattern="^(priority|review|skip|evaluate)$"),
    status: str | None = Query(None, pattern="^(new|skipped|evaluated)$"),
    fit: str | None = Query(None, pattern="^(high|medium|low)$"),
    q: str | None = None,
):
    return WorkflowService().load_inbox(tier=tier, status=status, fit=fit, q=q)


@router.get("/counts")
async def workflow_counts():
    return WorkflowService().get_counts()


@router.get("/evaluate-queue")
async def evaluate_queue():
    return WorkflowService().get_evaluate_queue()


@router.post("/triage")
async def run_triage():
    result = WorkflowService().run_triage()
    counts = WorkflowService().get_counts()
    return {**result, "counts": counts}
