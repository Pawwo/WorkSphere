from app.services.fit_cache import clear_fit_cache, get_fit, set_fit


def test_fit_cache_roundtrip():
    clear_fit_cache()
    assert get_fit("https://x.com", "Dev", "Acme") is None
    set_fit("https://x.com", "Dev", "Acme", "high")
    assert get_fit("https://x.com", "Dev", "Acme") == "high"
