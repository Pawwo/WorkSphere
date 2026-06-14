"""CV data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

@dataclass
class ExperienceEntry:
    period: str
    title: str
    company: str
    location: str = ""
    bullets: List[str] = field(default_factory=list)


@dataclass
class EducationEntry:
    period: str
    degree: str
    institution: str
    location: str = ""
    detail: str = ""


@dataclass
class CvDraftData:
    profile_statement: str
    competencies: List[str]
    experience_entries: List[ExperienceEntry]
    education_entries: List[EducationEntry]
    languages_line: str = ""
    publications: List[str] = field(default_factory=list)
    awards: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    role_headline: str = ""
    emphasis_jobs: List[str] = field(default_factory=list)
    cv_language: str = "en"
    references_line: str = "Available upon request."
