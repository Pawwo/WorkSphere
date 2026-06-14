from app.services.inbox.tier_rules import assign_tier, pi_priority_boost


def test_quick_fit_high_is_priority():
    assert assign_tier(quick_fit="high", triage_score=0) == "priority"


def test_pi_score_boost_priority():
    assert pi_priority_boost(78, "🟨") is True
    assert assign_tier(quick_fit="medium", triage_score=5, pi_score=75) == "priority"


def test_low_is_skip():
    assert assign_tier(quick_fit="low", triage_score=50) == "skip"


def test_medium_with_salary_priority():
    assert (
        assign_tier(
            quick_fit="medium",
            triage_score=10,
            salary_meets_threshold=True,
        )
        == "priority"
    )
