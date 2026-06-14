from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


_PRESENT_ENDS = frozenset({"obecnie", "present", "teraz", "now", "aktualnie"})


def _split_period(period: str) -> tuple[str, str]:
    parts = re.split(r"\s*[–\-]\s*", period.strip(), maxsplit=1)
    start = parts[0].strip() if parts else "?"
    if len(parts) < 2:
        return start, "present"
    end_raw = parts[1].strip()
    end = "present" if end_raw.lower() in _PRESENT_ENDS else end_raw
    return start, end


class EducationEntry(BaseModel):
    degree: str
    field: Optional[str] = None
    institution: str
    years: str
    thesis: Optional[str] = None
    topics: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_years(cls, data):
        if isinstance(data, dict) and "years" not in data and data.get("period"):
            data = {**data, "years": data["period"]}
        return data


class ExperienceEntry(BaseModel):
    title: str
    company: str
    start: str
    end: str = "present"
    location: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)
    technologies: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_period(cls, data):
        if not isinstance(data, dict):
            return data
        if "start" not in data and data.get("period"):
            start, end = _split_period(str(data["period"]))
            data = {**data, "start": start, "end": end}
        data.setdefault("company", "—")
        data.setdefault("bullets", [])
        return data


class ReferenceEntry(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


LanguageCode = Literal[
    "polish", "english", "german", "french", "spanish", "italian", "ukrainian", "other"
]
LanguageLevel = Literal["native", "C2", "C1", "B2", "B1", "A2", "A1"]


class LanguageEntry(BaseModel):
    language: LanguageCode
    level: LanguageLevel


class WizardSection1(BaseModel):
    full_name: str
    location: str
    phone: Optional[str] = None
    email: str
    linkedin: Optional[str] = None
    github: Optional[str] = None
    language_skills: List[LanguageEntry] = Field(default_factory=list)
    languages: str = ""
    employment_status: str = ""
    constraints: Optional[str] = None

    @model_validator(mode="after")
    def migrate_legacy_languages(self) -> WizardSection1:
        if not self.language_skills and (self.languages or "").strip():
            from app.services.profile.language_skills import (
                format_languages_line,
                parse_languages_text,
            )

            parsed = parse_languages_text(self.languages)
            if parsed:
                object.__setattr__(self, "language_skills", parsed)
        elif self.language_skills and not (self.languages or "").strip():
            from app.services.profile.language_skills import format_languages_line

            object.__setattr__(self, "languages", format_languages_line(self.language_skills))
        return self


class WizardSection2(BaseModel):
    education: List[EducationEntry] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)


class WizardSection3(BaseModel):
    experience: List[ExperienceEntry] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)


class WizardSection4(BaseModel):
    programming_skills: str
    ml_skills: Optional[str] = None
    domain_expertise: Optional[str] = None
    tools: Optional[str] = None
    other_skills: Optional[str] = None


class WizardSection5(BaseModel):
    publications: List[str] = Field(default_factory=list)
    awards: List[str] = Field(default_factory=list)


class WizardSection6(BaseModel):
    assessment_type: Optional[str] = None
    thrive_in: Optional[str] = None
    drains_energy: Optional[str] = None
    team_style: Optional[str] = None
    decision_style: Optional[str] = None
    communication_style: Optional[str] = None
    notes: Optional[str] = None


class WizardSection7(BaseModel):
    target_roles: List[str] = Field(default_factory=list)
    target_industries: Optional[str] = None
    excites: Optional[str] = None
    deal_breakers: Optional[str] = None
    must_haves: Optional[str] = None
    salary_expectation: Optional[str] = None
    avoid_environments: Optional[str] = None
    location_constraints: Optional[str] = None


class WizardSection8(BaseModel):
    references: List[ReferenceEntry] = Field(default_factory=list)


class WizardSection9(BaseModel):
    role_titles: List[str] = Field(default_factory=list)
    key_skills: List[str] = Field(default_factory=list)
    target_companies: List[str] = Field(default_factory=list)
    city: str = "Warszawa"
    region: str = "mazowieckie"
    country: str = "Polska"
    ideal_locations: List[str] = Field(default_factory=list)
    acceptable_locations: List[str] = Field(default_factory=list)
    borderline_locations: List[str] = Field(default_factory=list)
    too_far_locations: List[str] = Field(default_factory=list)
    portals: List[str] = Field(
        default_factory=lambda: [
            "pracuj",
            "justjoin",
            "nofluffjobs",
            "theprotocol",
            "praca_pl",
            "rocketjobs",
        ]
    )
    adjacent_roles: List[str] = Field(default_factory=list)


class WizardState(BaseModel):
    path: Literal["wizard", "cv"] = "wizard"
    section1: Optional[WizardSection1] = None
    section2: Optional[WizardSection2] = None
    section3: Optional[WizardSection3] = None
    section4: Optional[WizardSection4] = None
    section5: Optional[WizardSection5] = None
    section6: Optional[WizardSection6] = None
    section7: Optional[WizardSection7] = None
    section8: Optional[WizardSection8] = None
    section9: Optional[WizardSection9] = None
    cv_text: Optional[str] = None
    cv_extracted: Optional[dict] = None


class SetupStatus(BaseModel):
    complete: bool
    path: Optional[str] = None
    sections_done: List[int] = Field(default_factory=list)
    placeholders_remaining: int = 0
    files: dict = Field(default_factory=dict)


class CVImportRequest(BaseModel):
    cv_text: str


class CVImportResponse(BaseModel):
    extracted: dict
    summary: str
    gaps: List[str]
    wizard_state: WizardState


class WizardSectionRequest(BaseModel):
    section: int = Field(ge=1, le=9)
    data: dict


class SetupFinalizeResponse(BaseModel):
    success: bool
    files_written: List[str]
    message: str
