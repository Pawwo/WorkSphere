from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Set

import httpx

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.llm.token_budgets import EXPAND
from app.llm.structured import extract_json
from app.models.workflow import (
    CompetencyItem,
    ExpandApplyRequest,
    ExpandApplyResponse,
    ExpandPreviewRequest,
    ExpandPreviewResponse,
)
from app.prompts.loader import render_prompt
from app.services.profile_service import ProfileService

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".md", ".txt", ".tex", ".csv", ".json"}


class ExpandService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.profile = ProfileService(self.settings)
        self.llm = BielikClient(self.settings)
        self.documents_dir = self.settings.data_dir / "documents"

    def _existing_skills(self) -> Set[str]:
        try:
            text = self.profile.read_file("01-candidate-profile.md").lower()
        except FileNotFoundError:
            text = ""
        try:
            text += "\n" + self.profile.read_file("02-behavioral-profile.md").lower()
        except FileNotFoundError:
            pass
        tokens = set(re.findall(r"[a-zA-Z+#.]{2,}", text))
        return tokens

    def _is_duplicate(self, name: str, existing: Set[str]) -> bool:
        name_l = name.lower()
        if name_l in existing:
            return True
        for tok in existing:
            if name_l in tok or tok in name_l:
                return True
        return False

    def _scan_documents(self) -> tuple[List[str], str]:
        sources: List[str] = []
        chunks: List[str] = []
        if not self.documents_dir.exists():
            return sources, ""
        for path in sorted(self.documents_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            rel = str(path.relative_to(self.documents_dir))
            sources.append(f"documents/{rel}")
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:8000]
                chunks.append(f"### documents/{rel}\n{content}")
            except Exception as exc:
                logger.debug("skip %s: %s", path, exc)
        return sources, "\n\n".join(chunks)

    def _github_username(self, profile_md: str) -> Optional[str]:
        m = re.search(r"github\.com/([A-Za-z0-9_-]+)", profile_md, re.I)
        return m.group(1) if m else None

    async def _fetch_github(self, username: str) -> tuple[List[str], str]:
        sources: List[str] = [f"github/{username}"]
        chunks: List[str] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 10, "sort": "updated"},
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code != 200:
                return sources, ""
            repos = resp.json()
            for repo in repos[:8]:
                name = repo.get("name", "")
                desc = repo.get("description") or ""
                lang = repo.get("language") or ""
                topics = ", ".join(repo.get("topics") or [])
                chunks.append(f"### GitHub repo: {name}\nLang: {lang}\nTopics: {topics}\n{desc}")
                readme = ""
                try:
                    r = await client.get(
                        f"https://api.github.com/repos/{username}/{name}/readme",
                        headers={"Accept": "application/vnd.github.raw"},
                    )
                    if r.status_code == 200:
                        readme = r.text[:3000]
                except Exception:
                    pass
                if readme:
                    chunks.append(f"README excerpt:\n{readme}")
        return sources, "\n\n".join(chunks)

    async def preview(self, request: ExpandPreviewRequest) -> ExpandPreviewResponse:
        existing = self._existing_skills()
        sources_scanned: List[str] = []
        source_text_parts: List[str] = []

        profile_md = ""
        try:
            profile_md = self.profile.read_file("01-candidate-profile.md")
        except FileNotFoundError:
            pass

        if request.include_documents:
            doc_sources, doc_text = self._scan_documents()
            sources_scanned.extend(doc_sources)
            if doc_text:
                source_text_parts.append(doc_text)

        if request.include_github:
            username = self._github_username(profile_md)
            if username:
                gh_sources, gh_text = await self._fetch_github(username)
                sources_scanned.extend(gh_sources)
                if gh_text:
                    source_text_parts.append(gh_text)
            else:
                sources_scanned.append("github/(skipped — brak URL w profilu)")

        competencies: List[CompetencyItem] = []
        skipped = 0

        llm_ok = (await self.llm.healthcheck()).get("ok", False)
        if llm_ok and source_text_parts:
            prompt = render_prompt(
                "expand_extract.jinja2",
                existing_profile=profile_md[:4000],
                sources_text="\n\n".join(source_text_parts)[:12000],
            )
            try:
                raw = await self.llm.chat_complete(
                    [{"role": "system", "content": "JSON only"}, {"role": "user", "content": prompt}],
                    max_tokens=EXPAND,
                    temperature=0.1,
                )
                parsed = extract_json(raw)
                if isinstance(parsed, dict):
                    raw_items = parsed.get("competencies") or parsed.get("new_competencies") or []
                    for item in raw_items:
                        if isinstance(item, str):
                            name = item.strip()
                            category = "technical_secondary"
                            source = "expand"
                            method = "inference"
                        elif isinstance(item, dict):
                            name = item.get("name", "").strip()
                            category = item.get("category", "technical_secondary")
                            source = item.get("source", "expand")
                            method = item.get("method", "inference")
                        else:
                            continue
                        if not name:
                            continue
                        if self._is_duplicate(name, existing):
                            skipped += 1
                            continue
                        competencies.append(
                            CompetencyItem(
                                name=name,
                                category=category,
                                source=source,
                                method=method,
                            )
                        )
            except Exception as exc:
                logger.warning("expand LLM failed: %s", exc)

        if not competencies and source_text_parts:
            for kw in re.findall(
                r"\b(Python|TypeScript|Docker|Kubernetes|FastAPI|React|AWS|GCP|Azure|PostgreSQL|Redis|Git|Linux|CI/CD|MLOps|PyTorch|TensorFlow)\b",
                "\n".join(source_text_parts),
                re.I,
            ):
                name = kw
                if self._is_duplicate(name, existing):
                    skipped += 1
                    continue
                competencies.append(
                    CompetencyItem(
                        name=name,
                        category="technical_secondary",
                        source="regex fallback",
                        method="inference",
                    )
                )

        seen_names: Set[str] = set()
        unique: List[CompetencyItem] = []
        for c in competencies:
            key = c.name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            unique.append(c)

        return ExpandPreviewResponse(
            sources_scanned=sources_scanned,
            new_competencies=unique,
            skipped_duplicates=skipped,
        )

    def apply(self, request: ExpandApplyRequest, preview_items: Optional[List[CompetencyItem]] = None) -> ExpandApplyResponse:
        items = preview_items or request.competencies
        if request.apply_all and preview_items:
            items = preview_items
        if not items:
            return ExpandApplyResponse(added_to_profile=0, added_to_behavioral=0, message="Brak kompetencji do dodania.")

        profile_added = 0
        behavioral_added = 0

        try:
            profile_content = self.profile.read_file("01-candidate-profile.md")
        except FileNotFoundError:
            profile_content = "# Candidate Profile\n\n## Technical Skills\n"

        try:
            behavioral_content = self.profile.read_file("02-behavioral-profile.md")
        except FileNotFoundError:
            behavioral_content = "# Behavioral Profile\n\n## Strongest Behaviors\n"

        tech_lines: List[str] = []
        behavioral_lines: List[str] = []

        for item in items:
            line = f"- {item.name} *(źródło: {item.source})*"
            if item.category == "behavioral":
                behavioral_lines.append(line)
                behavioral_added += 1
            else:
                tech_lines.append(line)
                profile_added += 1

        if tech_lines:
            if "## Technical Skills" in profile_content:
                profile_content = profile_content.rstrip() + "\n\n### Expanded (via /expand)\n" + "\n".join(tech_lines) + "\n"
            else:
                profile_content += "\n## Technical Skills\n" + "\n".join(tech_lines) + "\n"
            self.profile.write_file("01-candidate-profile.md", profile_content)

        if behavioral_lines:
            if "## Strongest Behaviors" in behavioral_content:
                behavioral_content = behavioral_content.rstrip() + "\n\n### Expanded *(review before relying)*\n" + "\n".join(behavioral_lines) + "\n"
            else:
                behavioral_content += "\n## Strongest Behaviors\n" + "\n".join(behavioral_lines) + "\n"
            self.profile.write_file("02-behavioral-profile.md", behavioral_content)

        return ExpandApplyResponse(
            added_to_profile=profile_added,
            added_to_behavioral=behavioral_added,
            message=f"Dodano {profile_added} do profilu, {behavioral_added} behawioralnych.",
        )
