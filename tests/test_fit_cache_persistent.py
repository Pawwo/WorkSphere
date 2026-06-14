import pytest

from app.services.fit_cache import clear_fit_cache, configure_fit_cache_for_tests, get_fit, set_fit


@pytest.fixture
def cache_path(tmp_path):
    path = tmp_path / "fit_cache.json"
    configure_fit_cache_for_tests(path)
    yield path
    clear_fit_cache(path)


def test_fit_cache_persists_across_reload(cache_path):
    set_fit("https://example.com/1", "Dev", "Acme", "high")
    configure_fit_cache_for_tests(cache_path)
    assert get_fit("https://example.com/1", "Dev", "Acme") == "high"


def test_clear_fit_cache_removes_file(cache_path):
    set_fit("https://example.com/2", "PM", "Beta", "low")
    assert cache_path.exists()
    clear_fit_cache(cache_path)
    configure_fit_cache_for_tests(cache_path)
    assert get_fit("https://example.com/2", "PM", "Beta") is None
