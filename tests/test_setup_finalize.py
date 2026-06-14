"""Finalize must use latest saved wizard section (search-queries.md)."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.services.profile_service import ProfileService
from app.services.setup_service import SetupService


@pytest.mark.asyncio
async def test_finalize_regenerates_search_queries_from_section9(tmp_path):
    profile = tmp_path / "profile"
    setup = tmp_path / "setup"
    profile.mkdir()
    setup.mkdir()

    state = {
        "path": "wizard",
        "section1": {
            "full_name": "Jan Kowalski",
            "location": "Kraków",
            "email": "jan@example.com",
            "language_skills": [
                {"language": "polish", "level": "native"},
                {"language": "english", "level": "B2"},
                {"language": "german", "level": "A2"},
            ],
            "languages": "Polski (Ojczysty), Angielski (B2), Niemiecki (A2)",
            "employment_status": "",
        },
        "section4": {"programming_skills": "Python"},
        "section7": {"target_roles": ["Old Role"]},
        "section9": {
            "role_titles": ["Head of Operations"],
            "key_skills": ["ERP"],
            "city": "Kraków",
            "ideal_locations": [],
            "acceptable_locations": [],
            "portals": ["pracuj"],
            "adjacent_roles": ["Program Manager"],
        },
    }
    (setup / "wizard_state.json").write_text(json.dumps(state), encoding="utf-8")

    settings = Settings().model_copy(update={"data_dir": tmp_path.resolve()})
    svc = ProfileService(settings)

    svc.save_section(
        9,
        {
            "role_titles": [
                "Director of Operations",
                "Head of IT",
                "AI Product Manager",
            ],
            "key_skills": ["Odoo", "Docker"],
            "city": "Wrocław",
            "ideal_locations": ["Wrocław"],
            "acceptable_locations": ["remote"],
            "portals": ["pracuj"],
            "adjacent_roles": ["COO"],
        },
    )

    setup_svc = SetupService()
    setup_svc.profile = svc
    result = await setup_svc.finalize()
    assert result.success

    sq = (profile / "search-queries.md").read_text(encoding="utf-8")
    assert "Director of Operations" in sq
    assert "Head of IT" in sq
    assert "AI Product Manager" in sq
    assert '"Docker" Wrocław' in sq
    assert "Wrocław" in sq
    assert "COO" in sq
    assert "Head of Operations" not in sq
    assert "### Priority 1: Target roles" in sq
