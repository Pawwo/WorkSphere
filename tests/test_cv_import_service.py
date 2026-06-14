"""Unit tests for CV condensing (no LLM)."""

from pathlib import Path

from app.services.cv_import_service import (
    condense_cv,
    count_job_headers,
    header_excerpt,
    experience_only_excerpt,
    skills_excerpt,
)
from app.services.profile_service import ProfileService
from app.models.setup import WizardState

ROOT = Path(__file__).resolve().parents[1]
MASTER_CV = ROOT / "data" / "documents" / "CV" / "PAWEŁ WODYŃSKI — MASTER CV SOURCE.txt"


def test_excerpts_fit_llm_budget():
    if not MASTER_CV.exists():
        return
    text = MASTER_CV.read_text(encoding="utf-8")
    assert len(header_excerpt(text)) <= 1400
    assert len(experience_only_excerpt(text)) <= 2800
    assert len(skills_excerpt(text)) <= 1000
    condensed = condense_cv(text)
    assert len(condensed) <= 3000
    assert "VentorTech" in experience_only_excerpt(text) or "COO" in experience_only_excerpt(text)
    assert "@" in header_excerpt(text) or "pawel" in header_excerpt(text).lower()


def test_count_job_headers_master_cv():
    if not MASTER_CV.exists():
        return
    text = MASTER_CV.read_text(encoding="utf-8")
    n = count_job_headers(text)
    assert n >= 10


def test_parse_job_lines():
    sample = """Chief Operating Officer | VentorTech | Warszawa | 08.2025 – obecnie
Manager Business Development | myOdoo.pl | Szczecin | 04.2018 – 01.2023"""
    from app.services.cv_import_service import parse_job_lines_from_excerpt
    jobs = parse_job_lines_from_excerpt(sample)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Chief Operating Officer"
    assert jobs[0]["company"] == "VentorTech"
    extracted = {
        "identity": {
            "full_name": "Jan Kowalski",
            "location": "Warszawa",
            "email": "jan@example.com",
            "employment_status": "Szukam pracy",
            "constraints": "hybrid",
        },
        "skills": {
            "programming": "Python",
            "other": "Leadership, Agile",
        },
        "experience": [{"title": "Dev", "company": "ACME", "start": "2020", "end": "2025", "bullets": []}],
    }
    career = {
        "target_roles": ["COO"],
        "role_titles": ["coo warszawa"],
        "key_skills": ["odoo"],
        "city": "Warszawa",
    }
    svc = ProfileService()
    state_path = svc.wizard_state_path
    backup = state_path.read_text(encoding="utf-8") if state_path.exists() else None
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(WizardState().model_dump_json(indent=2), encoding="utf-8")
        state = svc.merge_cv_extract(extracted, "cv text", career=career)
        assert state.section1.employment_status == "Szukam pracy"
        assert state.section1.constraints == "hybrid"
        assert state.section4.other_skills == "Leadership, Agile"
        assert state.section7.target_roles == ["COO"]
        assert state.section9.role_titles == ["coo warszawa"]
    finally:
        if backup is not None:
            state_path.write_text(backup, encoding="utf-8")
