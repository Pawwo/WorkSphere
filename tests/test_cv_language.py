"""CV output language helpers."""

from app.services.cv.draft import baseline_cv_draft
from app.services.cv.language import (
    apply_offline_english_bullets,
    apply_static_cv_language,
    draft_has_language_mismatch,
    languages_line_for,
    normalize_cv_language,
    pdf_entries_language_mismatch,
    polish_pdf_bullet_samples,
    text_looks_polish,
)
from app.services.cv.master import load_master_ats_summary
from app.services.cv.types import CvDraftData, ExperienceEntry
from app.config import Settings


def test_normalize_cv_language():
    assert normalize_cv_language("en") == "en"
    assert normalize_cv_language("english") == "en"
    assert normalize_cv_language("pl") == "pl"
    assert normalize_cv_language(None) == "pl"


def test_text_looks_polish_detects_partyhat_style_bullets():
    assert text_looks_polish("Zarządzanie całością operacji firmy oraz zespołami Delivery.")
    assert not text_looks_polish("Managing company-wide operations and delivery teams.")


def test_draft_language_mismatch_en_with_polish_bullets():
    draft = CvDraftData(
        profile_statement="Chief Operating Officer with ERP experience.",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="08.2025 - Present",
                title="COO",
                company="VentorTech",
                bullets=["Zarządzanie całością operacji firmy."],
            )
        ],
        education_entries=[],
        cv_language="en",
    )
    assert draft_has_language_mismatch(draft, "en")


def test_apply_static_cv_language_english_labels():
    draft = CvDraftData(
        profile_statement="Summary",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="03.2022 - Present",
                title="Członek Komisji Rewizyjnej",
                company="Klaster IT",
                location="Szczecin",
                bullets=["Bullet"],
            )
        ],
        education_entries=[],
    )
    out = apply_static_cv_language(draft, "en")
    assert out.languages_line.startswith("English")
    assert out.experience_entries[0].title == "Audit Committee Member"


def test_apply_static_cv_language_strips_polish_awards_for_en():
    draft = CvDraftData(
        profile_statement="Summary",
        competencies=["Ops: Odoo"],
        experience_entries=[],
        education_entries=[],
        awards=["Doskonałe wyniki w obszarze utrzymania Klienta", "Top performer 2024"],
    )
    out = apply_static_cv_language(draft, "en")
    assert out.awards == ["Top performer 2024"]


def test_apply_offline_english_bullets_translates_known_pl_lines():
    draft = CvDraftData(
        profile_statement="COO with ERP experience.",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="08.2025 - Present",
                title="COO",
                company="VentorTech",
                bullets=["Zarządzanie całością operacji firmy oraz zespołami Delivery, BA, FC, PM, Dev i QA."],
            )
        ],
        education_entries=[],
        cv_language="en",
    )
    out = apply_offline_english_bullets(draft)
    assert not pdf_entries_language_mismatch(out, "en")
    assert out.experience_entries[0].bullets[0].startswith("Managing end-to-end")


def test_polish_pdf_bullet_samples_detects_pl_experience():
    draft = CvDraftData(
        profile_statement="COO with ERP experience.",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="08.2025 - Present",
                title="COO",
                company="VentorTech",
                bullets=["Zarządzanie całością operacji firmy."],
            )
        ],
        education_entries=[],
    )
    samples = polish_pdf_bullet_samples(draft, "en")
    assert samples


def test_apply_static_cv_language_translates_polish_bullets_for_en():
    draft = CvDraftData(
        profile_statement="COO with ERP experience.",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="08.2025 - Present",
                title="Chief Operating Officer",
                company="VentorTech",
                location="Warszawa / Szczecin",
                bullets=[
                    "Zarządzanie całością operacji firmy oraz zespołami Delivery, BA, FC, PM, Dev i QA."
                ],
            )
        ],
        education_entries=[],
        cv_language="en",
    )
    out = apply_static_cv_language(draft, "en")
    assert not pdf_entries_language_mismatch(out, "en")
    assert out.experience_entries[0].bullets[0].startswith("Managing end-to-end")
    assert "Warsaw" in out.experience_entries[0].location


def test_baseline_uses_english_summary_for_en_jobs():
    draft = baseline_cv_draft(
        role="COO",
        company="UltaHost",
        profile_md="## Identity\n- **Name:** Test",
        language="en",
        settings=Settings(),
    )
    assert draft.cv_language == "en"
    summary = load_master_ats_summary(Settings(), language="en")
    if summary:
        assert draft.profile_statement[:40] in summary or summary[:40] in draft.profile_statement
