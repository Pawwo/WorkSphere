"""search-queries.md — brak kategorii = brak zapytań batch (bez fallbacku)."""

from app.config import Settings
from app.services import search_queries as sq
from app.services.search_queries import (
    append_city_to_query,
    parse_search_queries,
    resolve_scrape_queries,
)


def test_parse_empty_categories(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    path = profile / "search-queries.md"
    path.write_text(
        "# Search Queries\n\n## Query Categories\n\n<!-- pusto -->\n",
        encoding="utf-8",
    )
    assert parse_search_queries(path)["categories"] == []


def test_resolve_scrape_queries_no_fallback(monkeypatch, tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "search-queries.md").write_text(
        "# Search Queries\n\n## Query Categories\n",
        encoding="utf-8",
    )
    settings = Settings().model_copy(update={"data_dir": tmp_path.resolve()})
    monkeypatch.setattr(sq, "get_settings", lambda: settings)
    assert resolve_scrape_queries() == []


def test_append_city_skips_remote_and_polska():
    assert append_city_to_query('"software engineer" remote polska', "Szczecin") == (
        '"software engineer" remote polska'
    )
    assert append_city_to_query("ERP operacje polska", "Szczecin") == "ERP operacje polska"
    assert append_city_to_query('"COO" remote', "Szczecin") == '"COO" remote'
    assert append_city_to_query('"COO" Szczecin', "Szczecin") == '"COO" Szczecin'
    assert append_city_to_query('"COO"', "Szczecin") == '"COO" Szczecin'
