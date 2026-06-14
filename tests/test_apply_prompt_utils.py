from app.services.apply_prompt_utils import (
    job_posting_excerpt,
    language_assessment_for_eval,
    sanitize_false_english_gap,
    sanitize_posting_gaps,
)

PROFILE_SNIPPET = """# Candidate Profile

## Identity
- **Name:** Test User
- **Languages:** Polski — ojczysty, Angielski — zaawansowany, Mandaryński — podstawowy
"""

JOB_SNIPPET = (
    "Our requirements English proficiency at a minimum B1+ level, "
    "with the ability to communicate effectively."
)


def test_job_posting_excerpt_no_ellipsis_artifact():
    raw = (
        "Your responsibilities " + "x" * 500
        + " Our requirements " + "y" * 500
        + " About the role " + "z" * 500
    )
    out = job_posting_excerpt(raw, max_chars=400)
    assert "[…]" not in out
    assert len(out) <= 400
    assert out.endswith("…")


def test_language_assessment_maps_zaawansowany_to_b2_and_meets_b1():
    note, english_ok = language_assessment_for_eval(PROFILE_SNIPPET, JOB_SNIPPET)
    assert "Angielski: B2" in note
    assert "B1" in note
    assert "SPEŁNIONE" in note
    assert english_ok is True


def test_sanitize_false_english_gap_strips_hallucinated_gap():
    parsed = {
        "skills_match": {"gaps": ["B1+ English proficiency", "SAP"]},
        "recommendation": (
            "Moderate fit. They need to improve English proficiency. "
            "Strong PM background."
        ),
    }
    out = sanitize_false_english_gap(parsed, english_ok=True)
    assert out["skills_match"]["gaps"] == ["SAP"]
    assert "English" not in out["recommendation"]
    assert "Strong PM background" in out["recommendation"]


def test_sanitize_posting_gaps_removes_sap_when_not_in_job():
    job = (
        "Our requirements JIRA, Confluence, project management, Agile. "
        "English proficiency B1+."
    )
    parsed = {
        "skills_match": {"gaps": ["SAP", "JIRA"]},
        "recommendation": (
            "Kandydat ma doświadczenie PM, ale wymaga uzupełnienia kompetencji z zakresu SAP. "
            "Dobrze zna JIRA."
        ),
    }
    out = sanitize_posting_gaps(parsed, job)
    assert out["skills_match"]["gaps"] == ["JIRA"]
    assert "SAP" not in out["recommendation"]
    assert "JIRA" in out["recommendation"]


def test_job_posting_excerpt_prefers_sections():
    raw = (
        "noise " * 50
        + "Your responsibilities lead teams and deliver projects. "
        + "noise " * 50
        + "Our requirements JIRA experience required. "
    )
    out = job_posting_excerpt(raw, max_chars=900)
    assert "Your responsibilities" in out
    assert "Our requirements" in out
