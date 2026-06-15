"""Tests for portal URL helpers."""

from app.services.scrape.url_utils import portal_from_url


def test_portal_from_url():
    assert portal_from_url("https://justjoin.it/job-offer/foo") == "justjoin"
    assert portal_from_url("https://www.pracuj.pl/praca/x,oferta,1") == "pracuj"
