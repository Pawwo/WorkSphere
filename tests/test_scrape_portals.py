"""Portal profile resolution."""

from pathlib import Path

from app.config import Settings
from app.services.scrape.portal_routing import portals_for_query
from app.services.scrape.portals import resolve_portals_for_request


def _settings(tmp_path: Path) -> Settings:
    return Settings().model_copy(
        update={
            "data_dir": tmp_path.resolve(),
            "scrapers_portal_profiles": {
                "executive": ["pracuj", "praca-pl"],
                "broad": ["linkedin-pl"],
            },
            "scrapers_default_portal_profile": "executive",
            "scrapers_disabled_portals": ["indeed-pl"],
        }
    )


def test_executive_profile_without_broad(tmp_path):
    portals = resolve_portals_for_request(_settings(tmp_path), broad=False)
    assert portals == ["pracuj", "praca-pl"]


def test_executive_profile_with_broad_adds_linkedin(tmp_path):
    portals = resolve_portals_for_request(_settings(tmp_path), broad=True)
    assert portals == ["pracuj", "praca-pl", "linkedin-pl"]


def test_full_profile_includes_seven_portals(tmp_path):
    settings = _settings(tmp_path).model_copy(
        update={
            "scrapers_default_portal_profile": "full",
            "scrapers_portal_profiles": {
                "executive": ["pracuj", "praca-pl"],
                "full": [
                    "pracuj",
                    "praca-pl",
                    "justjoin",
                    "nofluffjobs",
                    "theprotocol",
                    "rocketjobs",
                    "linkedin-pl",
                ],
                "broad": [],
            },
        }
    )
    portals = resolve_portals_for_request(
        settings, broad=False, portal_profile="full"
    )
    assert len(portals) == 7
    assert "linkedin-pl" in portals
    assert "justjoin" in portals


def test_coo_query_keeps_all_portals_when_smart_routing_off():
    all_portals = [
        "pracuj",
        "praca-pl",
        "justjoin",
        "nofluffjobs",
        "theprotocol",
        "rocketjobs",
        "linkedin-pl",
    ]
    result = portals_for_query(
        all_portals,
        "Chief Operating Officer (COO) Warszawa",
        smart_routing=False,
    )
    assert result == all_portals


def test_coo_query_skips_dev_portals_when_smart_routing_on():
    all_portals = [
        "pracuj",
        "praca-pl",
        "justjoin",
        "nofluffjobs",
        "theprotocol",
        "rocketjobs",
        "linkedin-pl",
    ]
    result = portals_for_query(
        all_portals,
        "Chief Operating Officer (COO) Warszawa",
        smart_routing=True,
    )
    assert result == ["pracuj", "praca-pl", "linkedin-pl"]
