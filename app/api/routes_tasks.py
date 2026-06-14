from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.tasks import TaskStatus
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatus)
async def get_task(task_id: str):
    status = await TaskService.get().get_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@router.get("/{task_id}/stream")
async def stream_task(task_id: str):
    status = await TaskService.get().get_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    return StreamingResponse(
        TaskService.get().stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
