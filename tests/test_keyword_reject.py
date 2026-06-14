from app.services.keyword_triage import is_reject_job, keyword_fit_hint


def test_magazynier_rejected():
    assert is_reject_job("Magazynier / Magazynierka", "Podobne oferty") is True
    assert keyword_fit_hint("Magazynier", "Podobne oferty") == "low"


def test_director_not_rejected():
    assert is_reject_job("Studio Director", "Partyhat") is False
    assert keyword_fit_hint("Studio Director", "Partyhat") is None
