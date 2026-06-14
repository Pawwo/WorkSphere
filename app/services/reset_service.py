from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import List, Optional

from app.config import Settings, get_settings
from app.models.workflow import (
    ResetExecuteRequest,
    ResetExecuteResponse,
    ResetPreviewRequest,
    ResetPreviewResponse,
)
from app.services.profile_service import ProfileService

PROFILE_RESET_FILES = {
    "01-candidate-profile.md": """# Candidate Profile

<!-- Run /setup to populate this file -->

## Identity

## Education

## Professional Experience

## Independent Projects

## Technical Skills

## Publications

## Awards

## References
""",
    "02-behavioral-profile.md": """# Behavioral Profile

<!-- Run /setup to populate this file -->

## Overview

## Strongest Behavioral Traits

## How You Work Best

## Growth Areas

## Mapping to Job Posting Language
""",
    "search-queries.md": """# Search Queries for Job Scraper

<!-- Run /setup (sekcja 9) aby wygenerować zapytania batch -->

## Search Portals (CLI)

**Primary** (fast, IT-focused — use on every scrape):
- pracuj, justjoin, nofluffjobs, theprotocol, praca_pl, rocketjobs

**Broad** (slower — use with broad=true):
- indeed, linkedin

## Query Categories

<!-- Kategorie Priority 1–4 zostaną uzupełnione przez wizard setup -->

## Location Filter

- **Ideal:** (uzupełnij)
- **Acceptable:** (uzupełnij)
- **Borderline:** (uzupełnij)
- **Too far:** (uzupełnij)
""",
}

DOCUMENTS_KEEP_NAMES = frozenset({"README.md", ".gitkeep"})
JOB_SCRAPER_RESET_FILES = (
    "triage_result.json",
    "evaluate_queue.json",
    "apply_results.json",
    "evaluate_results.json",
)


class ResetService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.profile = ProfileService(self.settings)
        self.documents_dir = self.settings.data_dir / "documents"
        self.application_packages_dir = self.settings.data_dir / "applications"
        self.cv_dir = self.settings.repo_root / "cv"
        self.cover_dir = self.settings.repo_root / "cover_letters"
        self.wizard_state = self.settings.data_dir / "setup" / "wizard_state.json"
        self.seen_jobs = self.settings.seen_jobs_path

    @staticmethod
    def _is_generated_cv(path: Path) -> bool:
        return path.is_file() and path.name.startswith(("main_", "Resume_"))

    @staticmethod
    def _is_generated_cover(path: Path) -> bool:
        return (
            path.is_file()
            and path.name.startswith(("cover_", "Cover_"))
            and path.name != "cover.cls"
        )

    def _collect_uploaded_documents(self) -> List[str]:
        paths: List[str] = []
        if not self.documents_dir.exists():
            return paths
        for path in sorted(self.documents_dir.rglob("*")):
            if path.is_file() and path.name not in DOCUMENTS_KEEP_NAMES:
                paths.append(str(path.relative_to(self.settings.data_dir)))
        return paths

    def _collect_application_packages(self) -> List[str]:
        paths: List[str] = []
        if not self.application_packages_dir.exists():
            return paths
        for path in sorted(self.application_packages_dir.rglob("*")):
            rel = path.relative_to(self.settings.data_dir)
            paths.append(str(rel) + ("/" if path.is_dir() else ""))
        return paths

    def _collect_generated_artifacts(self) -> List[str]:
        paths: List[str] = []
        for directory, matcher in (
            (self.cv_dir, self._is_generated_cv),
            (self.cover_dir, self._is_generated_cover),
        ):
            if not directory.exists():
                continue
            for path in sorted(directory.iterdir()):
                if matcher(path):
                    paths.append(str(path.relative_to(self.settings.repo_root)))
        return paths

    def preview(self, request: ResetPreviewRequest) -> ResetPreviewResponse:
        profile_files = {}
        document_files: List[str] = []

        if request.scope in ("profile", "all"):
            for name in PROFILE_RESET_FILES:
                try:
                    content = self.profile.read_file(name)
                    profile_files[name] = "has content" if len(content.strip()) > 100 else "minimal/empty"
                except FileNotFoundError:
                    profile_files[name] = "missing"
            profile_files["wizard_state.json"] = "exists" if self.wizard_state.exists() else "missing"
            profile_files["seen_jobs.json"] = "exists" if self.seen_jobs.exists() else "missing"

        if request.scope in ("documents", "all"):
            document_files.extend(self._collect_uploaded_documents())
            document_files.extend(self._collect_application_packages())
            document_files.extend(self._collect_generated_artifacts())
            if request.scope == "all":
                for name in JOB_SCRAPER_RESET_FILES:
                    if (self.settings.job_scraper_dir / name).exists():
                        document_files.append(f"data/job_scraper/{name}")
                if self.settings.db_path.exists():
                    document_files.append("data/app.db (applications, apply_runs)")

        return ResetPreviewResponse(
            scope=request.scope,
            profile_files=profile_files,
            document_files=document_files,
        )

    def _clear_uploaded_documents(self, cleared: List[str], unchanged: List[str]) -> None:
        if not self.documents_dir.exists():
            unchanged.append("data/documents/ (missing)")
            return
        found = False
        for path in sorted(self.documents_dir.rglob("*"), reverse=True):
            if path.is_file() and path.name not in DOCUMENTS_KEEP_NAMES:
                path.unlink()
                cleared.append(str(path.relative_to(self.settings.data_dir)))
                found = True
            elif path.is_dir() and path != self.documents_dir:
                try:
                    if not any(path.iterdir()):
                        path.rmdir()
                except OSError:
                    pass
        if not found:
            unchanged.append("data/documents/ (no uploads)")

    def _clear_application_packages(self, cleared: List[str], unchanged: List[str]) -> None:
        if not self.application_packages_dir.exists():
            unchanged.append("data/applications/ (missing)")
            return
        found = False
        for entry in list(self.application_packages_dir.iterdir()):
            if entry.name in DOCUMENTS_KEEP_NAMES:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
                cleared.append(str(entry.relative_to(self.settings.data_dir)) + "/")
                found = True
            elif entry.is_file():
                entry.unlink()
                cleared.append(str(entry.relative_to(self.settings.data_dir)))
                found = True
        if not found:
            unchanged.append("data/applications/ (empty)")

    def _clear_generated_artifacts(self, cleared: List[str], unchanged: List[str]) -> None:
        removed = 0
        for directory, matcher in (
            (self.cv_dir, self._is_generated_cv),
            (self.cover_dir, self._is_generated_cover),
        ):
            if not directory.exists():
                unchanged.append(f"{directory.relative_to(self.settings.repo_root)}/ (missing)")
                continue
            for path in list(directory.iterdir()):
                if matcher(path):
                    path.unlink()
                    cleared.append(str(path.relative_to(self.settings.repo_root)))
                    removed += 1
        if removed == 0:
            unchanged.append("cv/ + cover_letters/ (no generated files)")

    def _clear_sqlite_applications(self, cleared: List[str]) -> None:
        if not self.settings.db_path.exists():
            return
        with sqlite3.connect(self.settings.db_path) as conn:
            conn.execute("DELETE FROM application_activities")
            conn.execute("DELETE FROM applications")
            conn.execute("DELETE FROM apply_runs")
            conn.commit()
        cleared.append("data/app.db (applications, apply_runs)")

    def _clear_job_scraper_workflow(self, cleared: List[str]) -> None:
        for name in JOB_SCRAPER_RESET_FILES:
            path = self.settings.job_scraper_dir / name
            if path.exists():
                path.unlink()
                cleared.append(f"data/job_scraper/{name}")

    def execute(self, request: ResetExecuteRequest) -> ResetExecuteResponse:
        if request.confirmation != "RESET":
            return ResetExecuteResponse(
                cleared=[],
                unchanged=[],
                message="Reset anulowany — wymagane potwierdzenie RESET.",
            )

        cleared: List[str] = []
        unchanged: List[str] = []

        if request.scope in ("profile", "all"):
            for name, template in PROFILE_RESET_FILES.items():
                path = self.settings.profile_dir / name
                if path.exists():
                    self.profile.write_file(name, template)
                    cleared.append(f"data/profile/{name}")
                else:
                    unchanged.append(f"data/profile/{name}")

            self.wizard_state.parent.mkdir(parents=True, exist_ok=True)
            self.wizard_state.write_text(
                '{"path":"wizard","sections_done":[],"cv_text":null,"cv_extracted":null}',
                encoding="utf-8",
            )
            cleared.append("data/setup/wizard_state.json (cleared)")

            if self.seen_jobs.exists():
                self.seen_jobs.write_text('{"seen": {}}', encoding="utf-8")
                cleared.append("data/job_scraper/seen_jobs.json")

            for name in ("05-cv-templates.md", "07-interview-prep.md"):
                path = self.settings.profile_dir / name
                if not path.exists():
                    continue
                content = path.read_text(encoding="utf-8")
                if name == "05-cv-templates.md" and "Profile statement" in content:
                    marker = "**Profile statement templates:**"
                    if marker in content:
                        head = content.split(marker)[0]
                        content = head + marker + "\n\n<!-- Run /setup to populate -->\n"
                        self.profile.write_file(name, content)
                        cleared.append(f"data/profile/{name} (statements cleared)")

                if name == "07-interview-prep.md":
                    content = path.read_text(encoding="utf-8")
                    if "## STAR" in content or "## Ready-Made" in content:
                        head = content.split("##")[0]
                        content = head + "## STAR Candidates (Complete Manually)\n\n<!-- Run /setup to populate -->\n"
                        self.profile.write_file(name, content)
                        cleared.append(f"data/profile/{name} (STAR cleared)")

        if request.scope in ("documents", "all"):
            self._clear_uploaded_documents(cleared, unchanged)
            self._clear_application_packages(cleared, unchanged)
            self._clear_generated_artifacts(cleared, unchanged)
            self._clear_sqlite_applications(cleared)

        if request.scope == "all":
            self._clear_job_scraper_workflow(cleared)

        return ResetExecuteResponse(
            cleared=cleared,
            unchanged=unchanged,
            message="Reset zakończony. Uruchom /setup aby odbudować profil.",
        )
