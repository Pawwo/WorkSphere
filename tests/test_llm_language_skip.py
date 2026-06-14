from app.services.inbox.llm_language_triage import likely_needs_language_llm, posting_text_for_llm


def test_posting_text_trimmed_to_2800():
    long_text = "x" * 5000
    assert len(posting_text_for_llm(long_text)) == 2800


def test_pl_only_posting_skips_llm():
    text = (
        "Stanowisko w Warszawie. Wymagany język polski na poziomie native. "
        "Brak innych wymagań językowych. " * 5
    )
    assert likely_needs_language_llm(text) is False


def test_english_posting_needs_llm():
    text = (
        "We require fluent English (B2+) for daily communication with the team. "
        "Polish is a plus. " * 5
    )
    assert likely_needs_language_llm(text) is True
