"""Application document filename helpers."""

from app.services.apply_service import (
    application_cover_filename,
    application_cv_filename,
    short_company_name,
)


def test_short_company_name_strips_legal_suffix():
    assert short_company_name("Wolters Kluwer Polska Sp. z o.o.") == "Wolters_Kluwer"
    assert short_company_name("Acme Corp") == "Acme_Corp"


def test_resume_and_cover_filenames():
    name = "Jan Kowalski"
    company = "Wolters Kluwer Polska Sp. z o.o."
    assert application_cv_filename(name, company, ".html") == (
        "Resume_Jan_Kowalski_Wolters_Kluwer.html"
    )
    assert application_cover_filename(name, company, ".html") == (
        "Cover_Jan_Kowalski_Wolters_Kluwer.html"
    )
