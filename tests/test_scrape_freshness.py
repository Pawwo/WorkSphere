"""Freshness filter helpers."""

from datetime import datetime, timedelta, timezone

from app.services.scrape.freshness import effective_days, is_fresh, portal_strict_freshness


def test_is_fresh_within_48h():
    recent = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%d")
    assert is_fresh(recent, max_age_hours=48, strict=True) is True


def test_is_fresh_rejects_old():
    old = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
    assert is_fresh(old, max_age_hours=48, strict=True) is False


def test_is_fresh_strict_rejects_missing_date():
    assert is_fresh(None, max_age_hours=48, strict=True) is False
    assert is_fresh(None, max_age_hours=48, strict=False) is True


def test_effective_days_from_hours():
    assert effective_days(48, 7) == 2
    assert effective_days(24, 7) == 1


def test_portal_strict_freshness_per_portal():
    overrides = {"justjoin": False, "pracuj": True}
    assert portal_strict_freshness("justjoin", global_strict=True, portal_overrides=overrides) is False
    assert portal_strict_freshness("pracuj", global_strict=False, portal_overrides=overrides) is True
