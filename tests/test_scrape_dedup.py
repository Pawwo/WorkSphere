"""Cross-portal deduplication helpers."""

from app.services.scrape.dedup import job_identity, normalize_company, normalize_title


def test_normalize_company_strips_legal_suffix():
    assert normalize_company("Acme Sp. z o.o.") == "acme"
    assert normalize_company("NEARMAP POLAND SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ") == "nearmap poland"


def test_normalize_title_strips_parenthetical():
    assert normalize_title("Engineering Manager (k/m)") == "engineering manager"


def test_job_identity_matches_across_portals():
    a = job_identity("Acme Sp. z o.o.", "Head of Operations")
    b = job_identity("ACME", "Head of Operations (m/k)")
    assert a == b
