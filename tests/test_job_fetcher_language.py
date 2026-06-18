"""Job posting language heuristics."""

from __future__ import annotations

from app.services.job_fetcher import (
    _detect_language,
    _resolve_job_language,
    _role_implies_english,
    _role_title_part,
)

SMITH_NEPHEW_ROLE = "Senior IT Project Manager in Wrocław, Dolnośląskie, Poland"
SMITH_NEPHEW_RAW = (
    "Seniority level Mid-Senior level Employment type Full-time Job function "
    "Project Management and Information Technology Industries Medical Equipment "
    "Manufacturing Referrals increase your chances of interviewing at Smith+Nephew by 2x "
    "See who you know Get notified when a new job is posted."
)


def test_role_title_part_strips_linkedin_location() -> None:
    assert _role_title_part(SMITH_NEPHEW_ROLE) == "Senior IT Project Manager"
    assert _role_title_part("Head of IT") == "Head of IT"


def test_role_implies_english_ignores_polish_location() -> None:
    assert _role_implies_english(SMITH_NEPHEW_ROLE) is True
    assert _role_implies_english("Kierownik projektu IT in Warszawa, Mazowieckie, Poland") is False


def test_detect_language_linkedin_chrome_is_english() -> None:
    assert _detect_language(SMITH_NEPHEW_RAW) == "en"


def test_resolve_job_language_smith_nephew() -> None:
    assert _resolve_job_language(SMITH_NEPHEW_ROLE, SMITH_NEPHEW_RAW) == "en"


def test_detect_language_polish_posting() -> None:
    pl_text = "Wymagania: doświadczenie w zarządzaniu projektami. Oferujemy stabilne zatrudnienie."
    assert _detect_language(pl_text) == "pl"
    assert _resolve_job_language("Kierownik projektu", pl_text) == "pl"


INLOGICA_ROLE = "Project Manager ERP"
INLOGICA_RAW = (
    "wysokich umiejętności współpracy z zespołem – praca wymaga ciągłej konsultacji z klientami. "
    "min. 2-letniego doświadczenia jako Project Manager ERP. Twój zakres obowiązków: "
    "planowanie i koordynacja wszystkich aspektów projektów od inicjacji po realizację."
)


def test_resolve_job_language_english_role_polish_posting() -> None:
    assert _resolve_job_language(INLOGICA_ROLE, INLOGICA_RAW) == "pl"


def test_resolve_job_language_short_body_uses_role() -> None:
    assert _resolve_job_language(SMITH_NEPHEW_ROLE, "Short posting.") == "en"
