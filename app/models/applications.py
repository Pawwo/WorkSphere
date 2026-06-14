from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.pipeline import ApplyPipelineStage, HiringStage, PipelineStatus


class ApplicationCreate(BaseModel):
    url: Optional[str] = None
    company: str
    role: str
    company_slug: Optional[str] = None
    run_id: Optional[int] = None
    task_id: Optional[str] = None


class ApplicationUpdate(BaseModel):
    hiring_stage: Optional[HiringStage] = None
    pipeline_stage: Optional[ApplyPipelineStage] = None
    pipeline_status: Optional[PipelineStatus] = None
    notes: Optional[str] = None
    task_id: Optional[str] = None


class ApplicationActivityCreate(BaseModel):
    kind: Literal["stage_log", "note", "reminder"] = "note"
    author: str = "user"
    body: str


class ApplicationRecord(BaseModel):
    model_config = {"extra": "ignore"}

    id: int
    run_id: Optional[int] = None
    task_id: Optional[str] = None
    url: Optional[str] = None
    company: str
    role: str
    company_slug: Optional[str] = None
    pipeline_stage: str = "parse"
    pipeline_status: str = "pending"
    hiring_stage: str = "draft"
    overall_fit: Optional[str] = None
    fit_score: Optional[str] = None
    recommendation: Optional[str] = None
    reviewer_verdict: Optional[str] = None
    verification_pass: Optional[int] = None
    cv_file: Optional[str] = None
    cover_file: Optional[str] = None
    pdf_cv: Optional[str] = None
    pdf_cover: Optional[str] = None
    interview_prep_file: Optional[str] = None
    application_dir: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str
    activities: List[dict] = Field(default_factory=list)
    manifest: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    inbox_context: dict = Field(default_factory=dict)


class ApplyAsyncRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    proceed: bool = False
    compile_pdf: bool = True


class ApplyAsyncResponse(BaseModel):
    task_id: str
    application_id: int
    kind: str = "apply"
    status: str = "running"
