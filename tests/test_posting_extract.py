"""Posting requirements extraction for seen_jobs.description."""

from app.services.scrape.posting_extract import (
    description_for_storage,
    extract_key_description,
)

GAMEPOINT_SNIPPET = """
Position Summary We are looking for a curious Automation Solution Specialist.
What we're looking for Bachelor's or Master's degree in Computer Science, Engineering, Data Science, or a related field
Around 3+ years of experience in analytics, BI, reporting, or automation-focused roles
Hands-on experience building and maintaining automation workflows in production environments
Experience working with APIs and event-driven architectures
Solid understanding of AI/ML concepts (OCR, NLP, prompt engineering, confidence scoring)
Strong problem-solving mindset and analytical thinking
Seniority level Associate Employment type Contract
"""


def test_extract_linkedin_requirements_section():
    out = extract_key_description(
        GAMEPOINT_SNIPPET,
        portal="linkedin-pl",
        url="https://www.linkedin.com/jobs/view/automation-solutions-specialist-at-gamepoint-4423661306/",
    )
    assert "Bachelor" in out
    assert "automation workflows" in out
    assert "Seniority level" not in out
    assert "Sign in" not in out


def test_extract_polish_wymagania_section():
    raw = """
    O firmie Example Sp. z o.o.
    Wymagania
    Minimum 3 lata doświadczenia w Python
    Znajomość SQL i chmury AWS
    Mile widziane: Kubernetes
    Oferujemy
    Prywatna opieka medyczna
    """
    out = extract_key_description(raw, portal="pracuj", url="https://www.pracuj.pl/praca/example")
    assert "Python" in out
    assert "Oferujemy" not in out


def test_description_for_storage_prefers_extracted():
    raw = "x " * 50 + "Wymagania " + "y " * 50
    stored = description_for_storage(raw, portal="pracuj", url="https://www.pracuj.pl/praca/x")
    assert len(stored) <= 4000


def test_extract_empty_returns_empty():
    assert extract_key_description("") == ""
    assert description_for_storage("") == ""


def test_description_for_storage_trims_leading_comma():
    raw = (
        "Wymagania\n"
        ", Szukamy osoby z doświadczeniem w zarządzaniu zespołem inżynierów. "
        "Minimum 5 lat w IT.\n"
        "Oferujemy\n"
        "Benefity"
    )
    stored = description_for_storage(raw, portal="pracuj", url="https://www.pracuj.pl/praca/x")
    assert stored.startswith("Szukamy")
    assert not stored.startswith(",")
