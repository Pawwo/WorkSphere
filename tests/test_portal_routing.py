"""Smart portal routing per query."""

from app.services.scrape.portal_routing import portals_for_query

ALL = [
    "pracuj",
    "praca-pl",
    "justjoin",
    "nofluffjobs",
    "theprotocol",
    "rocketjobs",
    "linkedin-pl",
]


def test_exec_query_skips_dev_portals():
    result = portals_for_query(ALL, "COO Warszawa", smart_routing=True)
    assert "justjoin" not in result
    assert "nofluffjobs" not in result
    assert "rocketjobs" not in result
    assert "theprotocol" not in result
    assert "pracuj" in result
    assert "linkedin-pl" in result


def test_dev_query_keeps_all_portals():
    result = portals_for_query(ALL, "Python developer", smart_routing=True)
    assert result == ALL


def test_smart_routing_disabled():
    result = portals_for_query(ALL, "COO Warszawa", smart_routing=False)
    assert result == ALL
