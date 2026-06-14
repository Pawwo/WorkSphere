from __future__ import annotations

from typing import Literal

ApplyPipelineStage = Literal[
    "parse",
    "evaluate",
    "proceed",
    "draft",
    "review",
    "pdf",
    "checklist",
    "interview_prep",
    "tracker",
    "done",
]

PipelineStatus = Literal["pending", "running", "done", "failed", "blocked", "waiting"]

HiringStage = Literal[
    "draft",
    "ready_to_send",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "archived",
]

PIPELINE_STAGES: list[ApplyPipelineStage] = [
    "parse",
    "evaluate",
    "proceed",
    "draft",
    "review",
    "pdf",
    "checklist",
    "interview_prep",
    "tracker",
    "done",
]

HIRING_STAGES: list[HiringStage] = [
    "draft",
    "ready_to_send",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "archived",
]

STAGE_PROGRESS: dict[str, int] = {
    "parse": 10,
    "evaluate": 20,
    "proceed": 25,
    "draft": 40,
    "review": 55,
    "pdf": 70,
    "checklist": 85,
    "interview_prep": 92,
    "tracker": 98,
    "done": 100,
}
