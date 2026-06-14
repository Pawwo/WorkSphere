from app.services.cv.ats_scoring import html_to_plain_text, section_order_valid
from app.services.cv.draft import baseline_cv_draft
from app.services.cv.html_builder import build_cv_html
from app.services.cv.identity import parse_identity


PROFILE = """
## Identity
- **Name:** Test User
- **Email:** test@example.com
- **Phone:** +48 600 000 000
## Professional Experience
### COO - Acme (08.2025 - present)
- Led operations.
"""


def test_cv_html_ats_layout(tmp_path):
    from app.config import Settings

    settings = Settings().model_copy(update={"data_dir": tmp_path.resolve()})
    draft = baseline_cv_draft(
        role="Project Manager",
        company="Wolters",
        profile_md=PROFILE,
        language="en",
        settings=settings,
    )
    identity = parse_identity(PROFILE)
    html = build_cv_html(
        draft,
        identity,
        job_targets={"must_have_keywords": ["operations", "project management"]},
    )
    assert "<table" not in html.lower()
    assert "display: grid" not in html.lower()
    assert "float:" not in html.lower()
    assert '<section id="summary">' in html
    assert '<section id="skills">' in html or '<section id="experience">' in html
    assert '<ul class="skills-list">' in html or "skills-list" in html or "<section id=\"skills\">" in html
    assert section_order_valid(html)
    plain = html_to_plain_text(html)
    assert "Test User" in plain


def test_cv_html_lang_attribute():
    from app.config import Settings

    settings = Settings()
    draft = baseline_cv_draft(
        role="PM",
        company="X",
        profile_md=PROFILE,
        language="pl",
        settings=settings,
    )
    html = build_cv_html(draft, parse_identity(PROFILE))
    assert 'lang="pl"' in html
