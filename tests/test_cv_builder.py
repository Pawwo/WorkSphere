"""CV builder — experience bullets from profile, wizard, master CV."""

import pytest

from app.config import Settings
from app.services.cv_builder import (
    ExperienceEntry,
    baseline_cv_draft,
    merge_experience_bullets,
    parse_experience_from_master,
    parse_experience_from_profile,
    resolve_experience_entries,
)

PROFILE_WITH_PLACEHOLDERS = """
## Professional Experience

### Chief Operating Officer - VentorTech (08.2025 - present)
Warszawa / Szczecin
- (uzupełnij)

### Founder / Co-Owner - myOdoo.pl sp. z o.o. (07.2025 - present)
Szczecin
- (uzupełnij)
"""

MASTER_CV_SNIPPET = """
SUMMARY ATS
COO and Odoo ERP leader.

DOŚWIADCZENIE ZAWODOWE
Chief Operating Officer | VentorTech | Warszawa | 08.2025 - obecnie
    Zakres odpowiedzialności
    Prowadzenie operacji i wdrożeń Odoo ERP.
    Udokumentowane efekty
    Wzrost efektywności delivery o 30%.
Commercial Advisor | Example Corp | Remote | 01.2020 - 06.2025
    Zakres odpowiedzialności
    Doradztwo operacyjne.
Founder | myOdoo.pl | Szczecin | 07.2025 - obecnie
    Zakres odpowiedzialności
    Rozwój praktyki Odoo.
"""


@pytest.fixture
def cv_settings(tmp_path):
    cv_dir = tmp_path / "documents" / "CV"
    cv_dir.mkdir(parents=True)
    (cv_dir / "PAWEŁ WODYŃSKI — MASTER CV SOURCE.txt").write_text(
        MASTER_CV_SNIPPET, encoding="utf-8"
    )
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


def test_resolve_experience_fills_from_master(cv_settings):
    entries = resolve_experience_entries(PROFILE_WITH_PLACEHOLDERS, cv_settings)
    assert len(entries) >= 2
    coo = entries[0]
    assert coo.title == "Chief Operating Officer"
    assert coo.company == "VentorTech"
    assert coo.bullets
    assert "(uzupełnij)" not in coo.bullets[0]
    assert "odoo" in coo.bullets[0].lower() or "operacji" in coo.bullets[0].lower()


def test_parse_experience_from_master_has_all_jobs(cv_settings):
    master = parse_experience_from_master(cv_settings)
    assert len(master) >= 2
    titles = {e.title for e in master}
    assert "Chief Operating Officer" in titles
    assert "Commercial Advisor" in titles


def test_baseline_cv_draft_no_placeholder_bullets(cv_settings):
    draft = baseline_cv_draft(
        role="Head of Operations",
        company="Kuchnia Vikinga",
        profile_md=PROFILE_WITH_PLACEHOLDERS,
        settings=cv_settings,
    )
    all_bullets = [b for e in draft.experience_entries for b in e.bullets]
    assert all_bullets
    assert not any("(uzupełnij)" in b for b in all_bullets)


def test_merge_prefers_wizard_over_master_for_same_job(cv_settings):
    profile = parse_experience_from_profile(PROFILE_WITH_PLACEHOLDERS)
    wizard = [
        ExperienceEntry(
            period="08.2025 - Present",
            title="Chief Operating Officer",
            company="VentorTech",
            location="Warszawa",
            bullets=["Custom wizard bullet about Odoo delivery."],
        )
    ]
    merged = merge_experience_bullets(
        profile, wizard, parse_experience_from_master(cv_settings)
    )
    assert merged[0].bullets[0].startswith("Custom wizard")
