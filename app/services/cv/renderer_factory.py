"""Factory for CV document renderer and PDF compiler (latex vs html)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import Settings, get_settings
from app.services.cv.document_renderer import DocumentRenderer, PdfCompiler

if TYPE_CHECKING:
    pass


def get_document_renderer(settings: Settings | None = None) -> DocumentRenderer:
    settings = settings or get_settings()
    mode = (settings.cv_renderer or "html").strip().lower()
    if mode == "html":
        from app.services.cv.html_document_renderer import HtmlDocumentRenderer

        return HtmlDocumentRenderer()
    from app.services.cv.latex_document_renderer import LatexDocumentRenderer

    return LatexDocumentRenderer()


def get_pdf_compiler(settings: Settings | None = None) -> PdfCompiler:
    settings = settings or get_settings()
    mode = (settings.cv_renderer or "html").strip().lower()
    if mode == "html":
        from app.services.pdf_service import PdfService

        return PdfService(settings.repo_root, settings=settings)
    from app.services.latex_service import LatexService

    return LatexService(settings.repo_root, settings=settings)
