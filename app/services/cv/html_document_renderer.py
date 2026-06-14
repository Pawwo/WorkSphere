"""HTML document renderer (Playwright PDF path)."""

from __future__ import annotations

from app.services.cv.html_builder import build_cover_html, build_cv_html
from app.services.cv.types import CvDraftData


class HtmlDocumentRenderer:
    @property
    def file_extension(self) -> str:
        return ".html"

    def render_cv(self, draft: CvDraftData, identity: dict, company_slug: str = "") -> str:
        return build_cv_html(draft, identity, company_slug)

    def render_cover(
        self,
        cover_data: dict,
        identity: dict,
        company_slug: str,
        role_slug: str,
    ) -> str:
        return build_cover_html(cover_data, identity, company_slug, role_slug)
