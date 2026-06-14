"""Pipeline execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.models.apply import ApplyRequest, FitEvaluation, JobParsed, ReviewerResult
from app.models.jobs import ManualImportResult


@dataclass
class PipelineContext:
    request: ApplyRequest
    application_id: int
    run_id: int
    task_id: Optional[str] = None
    company_slug: str = ""
    role_slug: str = ""
    application_dir: str = ""
    parsed: Optional[JobParsed] = None
    inbox_imported: Optional[ManualImportResult] = None
    evaluation: Optional[FitEvaluation] = None
    reviewer: Optional[ReviewerResult] = None
    files: List[str] = field(default_factory=list)
    pdf_files: List[str] = field(default_factory=list)
    pdf_verification: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verification: dict = field(default_factory=dict)
    interview_prep_file: Optional[str] = None
    tailoring_decisions: List[str] = field(default_factory=list)
    job_targets: dict = field(default_factory=dict)
    bundle: dict = field(default_factory=dict)
    _stage_started: dict = field(default_factory=dict)
    stage_timings: dict = field(default_factory=dict)
    llm_json_broken: bool = False
    llm_health: Optional[dict] = None
