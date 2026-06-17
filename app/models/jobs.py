from __future__ import annotations

from typing import List, Literal, Optional

FitFilter = Optional[Literal["high", "medium", "low"]]
StatusFilter = Optional[Literal["new", "skipped", "evaluated"]]
TierFilter = Optional[Literal["priority", "review", "skip", "evaluate"]]

from pydantic import BaseModel, Field, model_validator


class JobCard(BaseModel):
    id: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    date: Optional[str] = None
    deadline: Optional[str] = None
    salary: Optional[str] = None
    url: str
    description: Optional[str] = None


class SearchMeta(BaseModel):
    total: int
    page: int
    perPage: int


class SearchResponse(BaseModel):
    meta: SearchMeta
    results: List[JobCard]


class ScrapeRequest(BaseModel):
    query: Optional[str] = None
    focus: Optional[str] = None
    broad: bool = False
    days: int = 7
    limit: int = 30
    portals: Optional[List[str]] = None


class ScrapeBatchRequest(BaseModel):
    broad: bool = False
    days: int = 2
    limit: int = 20
    max_categories: Optional[int] = 3
    portals: Optional[List[str]] = None
    roles: Optional[List[str]] = None
    append_city: bool = True


class PortalError(BaseModel):
    portal: str
    code: str
    message: str


class ScrapeBatchQueryResult(BaseModel):
    query: str
    run_id: Optional[int] = None
    total_found: int = 0
    new_count: int = 0


class ScrapeBatchResponse(BaseModel):
    queries_run: int
    total_found: int
    new_count: int
    results: List[ScrapeBatchQueryResult] = Field(default_factory=list)
    new_jobs: List[ScrapeResultItem] = Field(default_factory=list)
    portal_errors: List[PortalError] = Field(default_factory=list)


SkipReasonSource = Literal["manual", "auto_triage"]

ManualSkipCategory = Literal[
    "wrong_scoring",
    "english_level",
    "missing_skill",
    "domain_knowledge",
    "salary_low",
    "other",
]

AutoSkipCategory = Literal[
    "auto_low_fit",
    "auto_low_score",
    "auto_low_fit_and_score",
    "auto_english_level",
    "auto_language_level",
]

SkipReasonCategory = ManualSkipCategory | AutoSkipCategory

_MANUAL_SKIP_ITEM_FIELDS = (
    "correct_fit",
    "correct_score",
    "missing_item",
    "domain_note",
    "salary_note",
    "comment",
)


class ManualSkipReasonItem(BaseModel):
    category: ManualSkipCategory
    correct_fit: Optional[Literal["high", "medium", "low"]] = None
    correct_score: Optional[int] = None
    missing_item: Optional[str] = None
    domain_note: Optional[str] = None
    salary_note: Optional[str] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def validate_category_fields(self) -> ManualSkipReasonItem:
        cat = self.category
        if cat == "wrong_scoring":
            if self.correct_fit is None and self.correct_score is None:
                raise ValueError("wrong_scoring requires correct_fit or correct_score")
        elif cat == "missing_skill":
            if not (self.missing_item or "").strip():
                raise ValueError("missing_skill requires missing_item")
        elif cat == "domain_knowledge":
            if not (self.domain_note or "").strip():
                raise ValueError("domain_knowledge requires domain_note")
        elif cat == "salary_low":
            if not (self.salary_note or "").strip():
                raise ValueError("salary_low requires salary_note")
        elif cat == "other":
            if not (self.comment or "").strip():
                raise ValueError("other requires comment")
        return self


class SkipReasonDetails(BaseModel):
    source: SkipReasonSource = "manual"
    category: Optional[SkipReasonCategory] = None
    reasons: List[ManualSkipReasonItem] = Field(default_factory=list)
    triage_reason: Optional[str] = None
    triage_score: Optional[int] = None
    quick_fit: Optional[Literal["high", "medium", "low"]] = None
    skipped_at: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def legacy_manual_to_reasons(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        source = data.get("source", "manual")
        if source != "manual" or data.get("reasons"):
            return data
        cat = data.get("category")
        manual = {
            "wrong_scoring",
            "english_level",
            "missing_skill",
            "domain_knowledge",
            "salary_low",
            "other",
        }
        if cat not in manual:
            return data
        item: dict = {"category": cat}
        for field in _MANUAL_SKIP_ITEM_FIELDS:
            if data.get(field) is not None:
                item[field] = data[field]
        return {**data, "reasons": [item]}

    @model_validator(mode="after")
    def validate_source_fields(self) -> SkipReasonDetails:
        if self.source == "auto_triage":
            if self.category is None or self.triage_score is None:
                raise ValueError("auto_triage requires category and triage_score")
            return self
        if not self.reasons:
            raise ValueError("manual skip requires at least one reason")
        return self


class SeenJobEntry(BaseModel):
    title: str
    company: str
    url: str
    description: Optional[str] = None
    first_seen: str
    fit: Literal["high", "medium", "low"] = "medium"
    quick_fit_reason: Optional[str] = None
    quick_fit_signals: Optional[dict] = None
    quick_fit_prompt_version: Optional[str] = None
    status: Literal["new", "skipped", "evaluated"] = "new"
    location: Optional[str] = None
    deadline: Optional[str] = None
    portal: Optional[str] = None
    highlights: Optional[List[str]] = None
    salary_raw: Optional[str] = None
    salary_b2b_monthly: Optional[int] = None
    salary_source: Optional[str] = None
    salary_meets_threshold: Optional[bool] = None
    import_source: Optional[str] = None
    pi_score: Optional[int] = None
    pi_verdict: Optional[str] = None
    pi_app: Optional[str] = None
    needs_deep_eval: Optional[bool] = None
    skip_reason: Optional[SkipReasonDetails] = None


class SeenJobUpdate(BaseModel):
    status: Optional[Literal["new", "skipped", "evaluated"]] = None
    fit: Optional[Literal["high", "medium", "low"]] = None
    skip_reason: Optional[SkipReasonDetails] = None


class ManualImportResult(BaseModel):
    created: bool
    key: str
    url: str
    fit: Literal["high", "medium", "low"]
    title: str
    company: str


class ScrapeResultItem(BaseModel):
    fit: Literal["high", "medium", "low"]
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    deadline: Optional[str] = None
    url: str
    portal: str
    description: Optional[str] = None
    highlights: Optional[List[str]] = None


class ScrapeResponse(BaseModel):
    run_id: int
    total_found: int
    new_count: int
    results: List[ScrapeResultItem]
    portal_errors: List[PortalError] = Field(default_factory=list)


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded", "error"]
    llm: dict
    searxng: dict
    scrapers: dict
    latex: dict = Field(default_factory=dict)
