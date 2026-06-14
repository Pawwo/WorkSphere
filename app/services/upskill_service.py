from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.llm.token_budgets import UPSKILL
from app.llm.structured import extract_json
from app.models.workflow import GapItem, LearningEntry, LearningResource, UpskillRequest, UpskillResponse
from app.prompts.loader import render_prompt
from app.search.searxng_client import SearXNGClient
from app.services.job_fetcher import fetch_job_posting
from app.services.profile_service import ProfileService

logger = logging.getLogger(__name__)

COMMON_SKILLS = [
    "python", "java", "typescript", "javascript", "react", "angular", "vue",
    "docker", "kubernetes", "aws", "gcp", "azure", "postgresql", "mongodb",
    "fastapi", "django", "flask", "spring", "kafka", "redis", "terraform",
    "ci/cd", "mlops", "pytorch", "tensorflow", "spark", "sql", "git", "linux",
]


class UpskillService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.profile = ProfileService(self.settings)
        self.llm = BielikClient(self.settings)
        self.search = SearXNGClient(self.settings)
        self.upskill_dir = self.settings.data_dir / "upskill"
        self.tracker_path = self.settings.tracker_path

    def _load_tracker_rows(self) -> List[dict]:
        if not self.tracker_path.exists():
            return []
        with self.tracker_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader if any(row.values())]

    def _profile_skills(self) -> set:
        try:
            text = self.profile.read_file("01-candidate-profile.md").lower()
        except FileNotFoundError:
            return set()
        return set(text.split())

    def _extract_skills_from_text(self, text: str) -> List[str]:
        text_l = text.lower()
        found = [s for s in COMMON_SKILLS if s in text_l]
        return found

    def _hard_skill_gaps_aggregate(self, rows: List[dict], profile_skills: set) -> List[GapItem]:
        scores: dict[str, float] = {}
        for row in rows:
            fit = 50
            try:
                fit = int(row.get("fit_rating") or 50)
            except ValueError:
                pass
            weight = (100 - fit) / 100.0
            blob = " ".join(
                filter(None, [row.get("role", ""), row.get("sector", ""), row.get("notes", "")])
            ).lower()
            for skill in self._extract_skills_from_text(blob):
                if skill.replace("/", "") in profile_skills or skill in " ".join(profile_skills):
                    continue
                scores[skill] = scores.get(skill, 0) + weight

        gaps = []
        for skill, score in sorted(scores.items(), key=lambda x: -x[1]):
            priority = "Critical" if score >= 2 else "High" if score >= 1 else "Medium"
            gaps.append(
                GapItem(
                    priority=priority,  # type: ignore[arg-type]
                    skill=skill,
                    gap_type="hard",
                    source=f"tracker score {score:.1f}",
                )
            )
        return gaps[:15]

    async def _llm_gaps(self, profile: str, jobs_context: str, mode: str) -> tuple[List[GapItem], List[LearningEntry]]:
        llm_ok = (await self.llm.healthcheck()).get("ok", False)
        if not llm_ok:
            return [], []
        prompt = render_prompt(
            "upskill_synthesis.jinja2",
            profile=profile[:4000],
            jobs_context=jobs_context[:6000],
            mode=mode,
        )
        try:
            raw = await self.llm.chat_complete(
                [{"role": "system", "content": "JSON only"}, {"role": "user", "content": prompt}],
                max_tokens=UPSKILL,
                temperature=0.2,
            )
            parsed = extract_json(raw)
            if not isinstance(parsed, dict):
                return [], []
            gaps = [
                GapItem(
                    priority=g.get("priority", "Medium"),
                    skill=g.get("skill", ""),
                    gap_type=g.get("gap_type", "hard"),
                    source=g.get("source", "LLM"),
                )
                for g in parsed.get("gaps", [])
                if g.get("skill")
            ]
            plan = [
                LearningEntry(
                    gap=e.get("gap", ""),
                    priority=e.get("priority", "Medium"),
                    study_direction=e.get("study_direction", ""),
                    time_estimate=e.get("time_estimate", "~20h"),
                )
                for e in parsed.get("learning_plan", [])
                if e.get("gap")
            ]
            return gaps, plan
        except Exception as exc:
            logger.warning("upskill LLM failed: %s", exc)
            return [], []

    async def _enrich_learning_plan(self, plan: List[LearningEntry]) -> List[LearningEntry]:
        enriched: List[LearningEntry] = []
        for entry in plan[:8]:
            resources: List[LearningResource] = []
            try:
                results = await self.search.search_learning(entry.gap, limit=3)
                for r in results:
                    resources.append(LearningResource(title=r.title, url=r.url, reason=r.snippet[:120]))
            except Exception as exc:
                logger.debug("search learning failed: %s", exc)
            enriched.append(entry.model_copy(update={"resources": resources}))
        return enriched

    def _write_report(
        self,
        mode: str,
        gaps: List[GapItem],
        plan: List[LearningEntry],
        jobs_context: str,
    ) -> Path:
        self.upskill_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        path = self.upskill_dir / f"report-{today}.md"

        lines = [
            f"# Upskill Report — {today}",
            f"\n**Mode:** {mode}\n",
            "## Gap Heatmap\n",
            "| Priority | Skill | Type | Source |",
            "|----------|-------|------|--------|",
        ]
        for g in gaps:
            lines.append(f"| {g.priority} | {g.skill} | {g.gap_type} | {g.source} |")

        lines.append("\n## Learning Plan\n")
        for entry in plan:
            lines.append(f"### {entry.gap} ({entry.priority})")
            lines.append(f"- **Kierunek:** {entry.study_direction}")
            lines.append(f"- **Czas:** {entry.time_estimate}")
            for res in entry.resources:
                lines.append(f"- [{res.title}]({res.url}) — {res.reason}")
            lines.append("")

        lines.append("\n## Jobs Context\n")
        lines.append(jobs_context[:3000])

        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    async def run(self, request: UpskillRequest) -> UpskillResponse:
        profile = ""
        try:
            profile = self.profile.read_file("01-candidate-profile.md")
        except FileNotFoundError:
            profile = "Brak profilu — uruchom setup."

        profile_skills = self._profile_skills()
        gaps: List[GapItem] = []
        jobs_context = ""

        if request.mode == "targeted":
            job = await fetch_job_posting(url=request.url, text=request.text)
            jobs_context = job.raw_text
            for skill in self._extract_skills_from_text(job.raw_text):
                if skill not in " ".join(profile_skills):
                    gaps.append(
                        GapItem(priority="High", skill=skill, gap_type="hard", source=job.role)
                    )
        else:
            rows = self._load_tracker_rows()
            if not rows:
                jobs_context = "Tracker pusty — dodaj wpisy do data/job_search_tracker.csv"
            else:
                jobs_context = "\n".join(
                    f"- {r.get('company','?')}: {r.get('role','?')} (fit={r.get('fit_rating','?')})"
                    for r in rows
                )
                gaps = self._hard_skill_gaps_aggregate(rows, profile_skills)

        llm_gaps, plan = await self._llm_gaps(profile, jobs_context, request.mode)
        seen = {g.skill.lower() for g in gaps}
        for g in llm_gaps:
            if g.skill.lower() not in seen:
                gaps.append(g)
                seen.add(g.skill.lower())

        if not plan and gaps:
            plan = [
                LearningEntry(
                    gap=g.skill,
                    priority=g.priority,
                    study_direction=f"Naucz się {g.skill} w kontekście {g.gap_type}",
                    time_estimate="~20-40h",
                )
                for g in gaps[:6]
                if g.priority in ("Critical", "High", "Medium")
            ]

        plan = await self._enrich_learning_plan(plan)
        report_path = self._write_report(request.mode, gaps, plan, jobs_context)

        return UpskillResponse(
            mode=request.mode,
            report_path=str(report_path.relative_to(self.settings.repo_root)),
            gaps=gaps,
            learning_plan=plan,
            summary=f"Znaleziono {len(gaps)} luk. Raport: {report_path.name}",
        )
