from app.services.cv.truth_guard import (
    SkillTruthIndex,
    build_skill_truth_index,
)


PROFILE = """
## Technical Skills
- Odoo ERP, Python, JIRA, Confluence, Agile, Scrum
## Certifications
- Google Cloud Generative AI Leader
"""

MASTER = """
KLUCZOWE KOMPETENCJE
Odoo ERP, Python, JIRA, Confluence, project management, stakeholder engagement

ATS KEYWORDS
operations, digital transformation, KPI
"""


def test_build_index_includes_profile_tools(tmp_path):
    cv_dir = tmp_path / "documents" / "CV"
    cv_dir.mkdir(parents=True)
    from app.config import Settings

    settings = Settings().model_copy(update={"data_dir": tmp_path.resolve()})
    (cv_dir / "PAWEŁ WODYŃSKI — MASTER CV SOURCE.txt").write_text(MASTER, encoding="utf-8")
    idx = build_skill_truth_index(profile_md=PROFILE, settings=settings)
    assert idx.is_allowed("JIRA")
    assert idx.is_allowed("odoo")


def test_watchlist_not_allowed_via_short_token_substrings():
    idx = SkillTruthIndex(allowed_tools={"za", "erp", "python"})
    assert not idx._watchlist_phrase_allowed("zapier")
    assert not idx._watchlist_phrase_allowed("sap erp")
    assert idx.check_text("Zapier and SAP ERP integrations")


def test_sanitize_replaces_zapier_when_not_in_profile():
    idx = SkillTruthIndex(allowed_tools={"python", "odoo"})
    text, violations = idx.sanitize_text("Automated workflows using Zapier and Python.")
    assert "zapier" in violations or "Zapier" in " ".join(violations)
    assert "zapier" not in text.lower()
    assert "python" in text.lower()


def test_sanitize_dict_cleans_experience_bullets():
    idx = SkillTruthIndex(allowed_tools={"jira", "confluence"})
    data = {
        "experience_entries": [
            {
                "title": "COO",
                "company": "X",
                "bullets": ["Used Zapier for automation", "JIRA dashboards for KPIs"],
            }
        ]
    }
    out = idx.sanitize_dict(data)
    bullets = out["experience_entries"][0]["bullets"]
    assert all("zapier" not in b.lower() for b in bullets)
    assert any("jira" in b.lower() for b in bullets)
