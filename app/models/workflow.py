from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ExpandPreviewRequest(BaseModel):
    include_github: bool = True
    include_documents: bool = True


class CompetencyItem(BaseModel):
    name: str
    category: str
    source: str
    method: str = "inference"


class ExpandPreviewResponse(BaseModel):
    sources_scanned: List[str]
    new_competencies: List[CompetencyItem]
    skipped_duplicates: int = 0


class ExpandApplyRequest(BaseModel):
    competencies: List[CompetencyItem] = Field(default_factory=list)
    apply_all: bool = False
    include_github: bool = True
    include_documents: bool = True


class ExpandApplyResponse(BaseModel):
    added_to_profile: int
    added_to_behavioral: int
    message: str


class UpskillRequest(BaseModel):
    mode: Literal["aggregate", "targeted"] = "aggregate"
    url: Optional[str] = None
    text: Optional[str] = None


class GapItem(BaseModel):
    priority: Literal["Critical", "High", "Medium", "Low"]
    skill: str
    gap_type: str
    source: str


class LearningResource(BaseModel):
    title: str
    url: str
    reason: str


class LearningEntry(BaseModel):
    gap: str
    priority: str
    study_direction: str
    time_estimate: str
    resources: List[LearningResource] = Field(default_factory=list)


class UpskillResponse(BaseModel):
    mode: str
    report_path: str
    gaps: List[GapItem]
    learning_plan: List[LearningEntry]
    summary: str


class ResetPreviewRequest(BaseModel):
    scope: Literal["profile", "documents", "all"]


class ResetPreviewResponse(BaseModel):
    scope: str
    profile_files: dict = Field(default_factory=dict)
    document_files: List[str] = Field(default_factory=list)
    warning: str = "Ta operacja jest nieodwracalna. Wymaga potwierdzenia RESET."


class ResetExecuteRequest(BaseModel):
    scope: Literal["profile", "documents", "all"]
    confirmation: str


class ResetExecuteResponse(BaseModel):
    cleared: List[str]
    unchanged: List[str]
    message: str
