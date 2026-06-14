from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ApplyRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    proceed: bool = False
    compile_pdf: bool = True


class JobParsed(BaseModel):
    company: str
    role: str
    location: Optional[str] = None
    language: str = "pl"
    raw_text: str
    source: Literal["url", "text"] = "text"


class FitEvaluation(BaseModel):
    skills_match: dict = Field(default_factory=dict)
    experience_match: dict = Field(default_factory=dict)
    behavioral_match: dict = Field(default_factory=dict)
    location_match: dict = Field(default_factory=dict)
    salary_benchmark: Optional[dict] = None
    overall_fit: Literal["strong", "moderate", "weak"] = "moderate"
    recommendation: str = ""


class ReviewerResult(BaseModel):
    structured_edits: List[dict] = Field(default_factory=list)
    narrative: dict = Field(default_factory=dict)
    company_research_notes: str = ""
    overall_verdict: str = "revise"


class ApplyResponse(BaseModel):
    run_id: int
    stage: str
    parsed: JobParsed
    evaluation: Optional[FitEvaluation] = None
    reviewer: Optional[ReviewerResult] = None
    files: List[str] = Field(default_factory=list)
    pdf_files: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    message: str = ""
    verification: dict = Field(default_factory=dict)
    pdf_verification: List[str] = Field(default_factory=list)
    interview_prep_file: Optional[str] = None
    tailoring_decisions: List[str] = Field(default_factory=list)
