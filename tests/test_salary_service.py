from app.services.salary_service import SalaryService


def test_parse_b2b_direct_above_threshold():
    svc = SalaryService()
    a = svc.assess(title="COO", salary="28 000 - 35 000 PLN B2B")
    assert a.meets_threshold is True
    assert a.source == "direct"
    assert (a.monthly_b2b_max or 0) >= 25000


def test_parse_brutto_below_threshold_downgrades_fit():
    svc = SalaryService()
    a = svc.assess(title="Project Manager", salary="15 000 - 18 000 PLN brutto")
    assert a.meets_threshold is False
    assert svc.adjust_fit("high", a, svc.threshold_pln) == "low"


def test_estimate_when_missing_salary():
    svc = SalaryService()
    a = svc.assess(title="COO Operations Director", salary=None, description="No pay info")
    assert a.source == "estimated"
    assert a.monthly_b2b_median is not None
    assert a.role_bucket in ("coo", "operations_director", "head_of_operations", "default_manager")


def test_extract_from_description():
    svc = SalaryService()
    desc = "Oferujemy wynagrodzenie 26 000 - 30 000 PLN netto na fakturze B2B"
    a = svc.assess(title="Operations Manager", description=desc)
    assert a.source == "description"
    assert a.meets_threshold is True


def test_pracuj_html_garbage_falls_back_to_estimate():
    svc = SalaryService()
    desc = (
        "Oferta pracy Project Manager valid for 14 days ( to 25 Jun ) "
        "Przyokopowa 33 Warszawa contract of employment full-time "
        "Your responsibilities manage projects JIRA Confluence "
        "© Grupa Pracuj S.A. 12345678901234567890"
    )
    a = svc.assess(title="Project & Program Manager", description=desc)
    assert a.source == "estimated"
    assert (a.monthly_b2b_median or 0) <= svc.MAX_SANE_MONTHLY_B2B_PLN
    assert a.reason == "ESTIMATED_FROM_BENCHMARKS"


def test_absurd_parsed_range_falls_back_to_estimate():
    svc = SalaryService()
    a = svc.assess(title="COO", salary="1 777 440 - 3 528 000 PLN B2B")
    assert a.reason == "PARSE_FALLBACK_ESTIMATE"
    assert (a.monthly_b2b_median or 0) <= svc.MAX_SANE_MONTHLY_B2B_PLN


def test_extract_polish_thousand_separator_from_blob():
    svc = SalaryService()
    desc = (
        "LinkedIn chrome " * 20
        + "Widełki: 30.000 - 50.000 PLN B2B "
        + "Chief AI Implementation Officer role details"
    )
    extracted = svc.extract_salary_from_description(desc)
    assert "30.000" in extracted or "30000" in extracted.replace(" ", "")
    a = svc.assess(title="Chief AI Implementation Officer", description=desc)
    assert a.source == "description"
    assert a.meets_threshold is True
    assert a.monthly_b2b_median == 40000
    assert "b2b" in (a.salary_raw or "").lower()


def test_chief_ai_implementation_officer_role_bucket():
    svc = SalaryService()
    assert svc._role_bucket("Chief AI Implementation Officer") == "ai_manager"


def test_should_reassess_estimated_when_description_has_salary():
    svc = SalaryService()
    assert svc.should_reassess_estimated(
        salary_source="estimated",
        description="Widełki: 30.000 - 50.000 PLN B2B",
    )
    assert not svc.should_reassess_estimated(
        salary_source="estimated",
        description="No salary information here",
    )
    assert not svc.should_reassess_estimated(
        salary_source="direct",
        description="Widełki: 30.000 - 50.000 PLN B2B",
    )
