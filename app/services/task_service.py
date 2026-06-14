from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator, Callable, Dict, Optional

from app.config import get_settings
from app.models.tasks import TaskStatus
from app.storage.db import Database

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, str], Any]


class TaskService:
    _instance: Optional["TaskService"] = None

    def __init__(self):
        self.db = Database(get_settings().db_path)
        self._queues: Dict[str, asyncio.Queue] = {}

    @classmethod
    def get(cls) -> "TaskService":
        if cls._instance is None:
            cls._instance = TaskService()
        return cls._instance

    def _queue(self, task_id: str) -> asyncio.Queue:
        if task_id not in self._queues:
            self._queues[task_id] = asyncio.Queue()
        return self._queues[task_id]

    async def _publish(self, task_id: str, event: dict) -> None:
        await self.db.append_task_event(
            task_id,
            stage=event.get("stage", ""),
            progress=event.get("progress", 0),
            message=event.get("message", ""),
            status=event.get("status", "running"),
            payload={k: v for k, v in event.items() if k not in ("stage", "progress", "message", "status")},
        )
        q = self._queue(task_id)
        await q.put(event)

    async def create(self, kind: str) -> str:
        task_id = str(uuid.uuid4())
        await self.db.create_task(task_id, kind)
        self._queue(task_id)
        return task_id

    async def emit(self, task_id: str, stage: str, progress: int, message: str) -> None:
        await self.db.update_task(task_id, stage=stage, progress=progress, message=message, status="running")
        await self._publish(
            task_id,
            {"stage": stage, "progress": progress, "message": message, "status": "running"},
        )

    async def wait_for_input(self, task_id: str, result: Any, message: str = "Oczekiwanie na Proceed") -> None:
        payload = json.dumps(result, ensure_ascii=False, default=str)
        await self.db.update_task(
            task_id,
            stage="proceed",
            progress=25,
            message=message,
            status="waiting",
            result_json=payload,
        )
        await self._publish(
            task_id,
            {
                "stage": "proceed",
                "progress": 25,
                "message": message,
                "status": "waiting",
                "result": result,
            },
        )

    async def complete(self, task_id: str, result: Any) -> None:
        payload = json.dumps(result, ensure_ascii=False, default=str)
        await self.db.update_task(
            task_id,
            stage="done",
            progress=100,
            message="Zakończono",
            status="completed",
            result_json=payload,
        )
        await self._publish(
            task_id,
            {"stage": "done", "progress": 100, "message": "Zakończono", "status": "completed", "result": result},
        )

    async def fail(self, task_id: str, error: str) -> None:
        await self.db.update_task(
            task_id,
            stage="error",
            progress=0,
            message=error,
            status="failed",
        )
        await self._publish(
            task_id,
            {"stage": "error", "progress": 0, "message": error, "status": "failed", "error": error},
        )

    async def get_status(self, task_id: str) -> Optional[TaskStatus]:
        row = await self.db.get_task(task_id)
        if not row:
            return None
        result = None
        if row.get("result_json"):
            try:
                result = json.loads(row["result_json"])
            except json.JSONDecodeError:
                result = row["result_json"]
        return TaskStatus(
            task_id=task_id,
            kind=row["kind"],
            status=row["status"],
            stage=row.get("stage") or "",
            progress=row.get("progress") or 0,
            message=row.get("message") or "",
            result=result,
            error=row.get("message") if row["status"] == "failed" else None,
        )

    async def stream(self, task_id: str) -> AsyncIterator[str]:
        status = await self.get_status(task_id)
        if not status:
            yield f"data: {json.dumps({'error': 'not found'})}\n\n"
            return

        for event in await self.db.list_task_events(task_id):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            if event.get("status") in ("completed", "failed"):
                return

        if status.status not in ("running", "waiting"):
            yield f"data: {json.dumps(status.model_dump())}\n\n"
            return

        q = self._queue(task_id)
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'status': status.status, 'message': 'heartbeat'})}\n\n"
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            if event.get("status") in ("completed", "failed"):
                break

    def progress_callback(self, task_id: str) -> ProgressCallback:
        async def _cb(stage: str, progress: int, message: str) -> None:
            await self.emit(task_id, stage, progress, message)

        return _cb
