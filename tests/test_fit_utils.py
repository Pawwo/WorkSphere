from app.services.fit_utils import FIT_SORT_KEY, fit_sort_key, sort_by_fit


def test_fit_sort_key_order():
    assert fit_sort_key("high") < fit_sort_key("medium")
    assert fit_sort_key("medium") < fit_sort_key("low")
    assert fit_sort_key(None) == 9


def test_sort_by_fit():
    items = [{"fit": "low"}, {"fit": "high"}, {"fit": "medium"}]
    sorted_items = sort_by_fit(items, lambda x: x["fit"])
    assert [x["fit"] for x in sorted_items] == ["high", "medium", "low"]


def test_fit_sort_key_constants():
    assert FIT_SORT_KEY["high"] == 0
