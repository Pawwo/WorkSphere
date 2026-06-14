"""Document renderer and PDF compiler protocols for CV/cover generation."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Protocol, Tuple

from app.services.cv.types import CvDraftData


class DocumentRenderer(Protocol):
    """Render CvDraftData and cover fields to a storable document string."""

    def render_cv(self, draft: CvDraftData, identity: dict, company_slug: str = "") -> str: ...

    def render_cover(
        self,
        cover_data: dict,
        identity: dict,
        company_slug: str,
        role_slug: str,
    ) -> str: ...

    @property
    def file_extension(self) -> str: ...


class PdfCompiler(Protocol):
    """Compile document sources to PDF and verify page counts."""

    async def compile_and_verify(
        self,
        cv_source_path: Path,
        cover_source_path: Path,
        cv_name: str,
        cover_name: str,
    ) -> Tuple[List[str], List[str], List[str]]: ...

    def tools_available(self) -> dict: ...
