from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class TaskCreateResponse(BaseModel):
    task_id: str
    kind: str
    status: str = "running"


class TaskStatus(BaseModel):
    task_id: str
    kind: str
    status: Literal["running", "completed", "failed"]
    stage: str = ""
    progress: int = 0
    message: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
