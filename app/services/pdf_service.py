"""HTML → PDF via Playwright Chromium."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class PdfService:
    CV_TARGET_PAGES = 2
    COVER_TARGET_PAGES = 1
    MAX_COMPILE_ATTEMPTS = 3

    def __init__(self, repo_root: Path, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.repo_root = repo_root
        self.cv_dir = repo_root / "cv"
        self.cover_dir = repo_root / "cover_letters"

    def tools_available(self) -> dict:
        try:
            from playwright.async_api import async_playwright  # noqa: F401

            return {"playwright": True, "chromium": True}
        except ImportError:
            return {"playwright": False, "chromium": False, "error": "playwright not installed"}

    def count_pdf_pages(self, pdf_path: Path) -> Optional[int]:
        try:
            from pypdf import PdfReader

            return len(PdfReader(str(pdf_path)).pages)
        except Exception as exc:
            logger.warning("pdf page count failed: %s", exc)
            return None

    async def pdf_page_count(self, pdf_path: Path) -> Optional[int]:
        return self.count_pdf_pages(pdf_path)

    async def _compile_html_to_pdf(self, browser, html_path: Path, pdf_path: Path) -> Tuple[bool, str]:
        if not html_path.exists():
            return False, f"Brak pliku {html_path}"
        html = html_path.read_text(encoding="utf-8")
        log = ""
        try:
            page = await browser.new_page()
            try:
                await page.set_content(html, wait_until="load")
                await page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={
                        "top": "12mm",
                        "bottom": "12mm",
                        "left": "12mm",
                        "right": "12mm",
                    },
                )
            finally:
                await page.close()
            ok = pdf_path.exists()
            if not ok:
                log = "Playwright nie utworzył pliku PDF"
            return ok, log
        except Exception as exc:
            logger.warning("Playwright PDF failed for %s: %s", html_path.name, exc)
            return False, str(exc)[:300]

    async def compile_and_verify(
        self,
        cv_source_path: Path,
        cover_source_path: Path,
        cv_name: str,
        cover_name: str,
    ) -> Tuple[List[str], List[str], List[str]]:
        pdf_files: List[str] = []
        warnings: List[str] = []
        tools = self.tools_available()

        if not tools.get("playwright"):
            warnings.append(
                "Playwright niedostępny — uruchom: pip install playwright && bash scripts/install_playwright.sh"
            )
            return pdf_files, warnings, ["fail: brak playwright"]

        cv_pdf_name = cv_name.replace(".html", ".pdf").replace(".tex", ".pdf")
        cover_pdf_name = cover_name.replace(".html", ".pdf").replace(".tex", ".pdf")
        cv_pages: Optional[int] = None
        cover_pages: Optional[int] = None

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            warnings.append(str(exc))
            return pdf_files, warnings, ["fail: brak playwright"]

        chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or None
        launch_kwargs: dict = {"headless": True}
        if chromium_path:
            launch_kwargs["executable_path"] = chromium_path

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(**launch_kwargs)
            try:
                for attempt in range(self.MAX_COMPILE_ATTEMPTS):
                    cv_pdf_path = self.cv_dir / cv_pdf_name
                    cover_pdf_path = self.cover_dir / cover_pdf_name

                    cv_ok, cv_log = await self._compile_html_to_pdf(
                        browser, cv_source_path, cv_pdf_path
                    )
                    cover_ok, cover_log = await self._compile_html_to_pdf(
                        browser, cover_source_path, cover_pdf_path
                    )

                    if not cv_ok:
                        warnings.append(
                            f"Kompilacja CV nieudana (próba {attempt + 1}): {cv_log[-200:]}"
                        )
                    if not cover_ok:
                        warnings.append(
                            f"Kompilacja listu nieudana (próba {attempt + 1}): {cover_log[-200:]}"
                        )

                    pdf_files = []
                    cv_pages = cover_pages = None
                    if cv_ok and cv_pdf_path.exists():
                        cv_pages = await self.pdf_page_count(cv_pdf_path)
                        pdf_files.append(str(cv_pdf_path.relative_to(self.repo_root)))
                    if cover_ok and cover_pdf_path.exists():
                        cover_pages = await self.pdf_page_count(cover_pdf_path)
                        pdf_files.append(str(cover_pdf_path.relative_to(self.repo_root)))

                    if (
                        cv_ok
                        and cover_ok
                        and cv_pages == self.CV_TARGET_PAGES
                        and cover_pages == self.COVER_TARGET_PAGES
                    ):
                        return pdf_files, warnings, [
                            f"pass: CV {cv_pages} stron",
                            f"pass: List {cover_pages} stron",
                        ]

                    if attempt < self.MAX_COMPILE_ATTEMPTS - 1:
                        if cv_pages and cv_pages > self.CV_TARGET_PAGES:
                            warnings.append(
                                f"CV ma {cv_pages} stron — wymaga skrócenia treści "
                                f"(próba {attempt + 2}; trim HTML w pipeline)"
                            )
                        if cover_pages and cover_pages > self.COVER_TARGET_PAGES:
                            warnings.append(
                                f"List ma {cover_pages} stron — wymaga skrócenia treści "
                                f"(próba {attempt + 2})"
                            )
                        break
            finally:
                await browser.close()

        cv_status = (
            f"pass: CV {cv_pages} stron"
            if cv_pages == self.CV_TARGET_PAGES
            else f"fail: CV {cv_pages or '?'} stron (cel {self.CV_TARGET_PAGES})"
        )
        cover_status = (
            f"pass: List {cover_pages} stron"
            if cover_pages == self.COVER_TARGET_PAGES
            else f"fail: List {cover_pages or '?'} stron (cel {self.COVER_TARGET_PAGES})"
        )
        return pdf_files, warnings, [cv_status, cover_status]

    def cleanup_artifacts(self, base_path: Path) -> None:
        """No sidecar artifacts for HTML→PDF (kept for API parity with LatexService)."""
        del base_path
