from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.config import Settings, get_settings
from app.models.setup import (
    WizardSection1,
    WizardSection2,
    WizardSection3,
    WizardSection4,
    WizardSection5,
    WizardSection6,
    WizardSection7,
    WizardSection8,
    WizardSection9,
    WizardState,
)
from app.services.profile.generators import (
    gen_01,
    gen_02,
    gen_04,
    gen_05,
    gen_07,
    gen_claude,
    gen_search_queries,
)

PROFILE_FILES = [
    "01-candidate-profile.md",
    "02-behavioral-profile.md",
    "03-writing-style.md",
    "04-job-evaluation.md",
    "05-cv-templates.md",
    "06-cover-letter-templates.md",
    "07-interview-prep.md",
    "CLAUDE.md",
    "search-queries.md",
]

def _normalize_string_list(items: list) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            parts = [str(v).strip() for v in item.values() if v]
            if parts:
                out.append(" — ".join(parts))
    return out


SECTION_MODELS = {
    1: WizardSection1,
    2: WizardSection2,
    3: WizardSection3,
    4: WizardSection4,
    5: WizardSection5,
    6: WizardSection6,
    7: WizardSection7,
    8: WizardSection8,
    9: WizardSection9,
}


class ProfileService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.profile_dir = self.settings.profile_dir
        self.wizard_state_path = self.settings.data_dir / "setup" / "wizard_state.json"

    def _count_placeholders(self, text: str) -> int:
        return len(re.findall(r"\[YOUR_|\[PLACEHOLDER\]|\[DEGREE\]|\[JOB_TITLE\]", text))

    def get_status(self) -> dict:
        files_status = {}
        total_placeholders = 0
        for name in PROFILE_FILES:
            path = self.profile_dir / name
            if path.exists():
                content = path.read_text(encoding="utf-8")
                ph = self._count_placeholders(content)
                total_placeholders += ph
                files_status[name] = {"exists": True, "placeholders": ph}
            else:
                files_status[name] = {"exists": False, "placeholders": 0}

        state = self.load_wizard_state()
        sections_done = []
        for i in range(1, 10):
            if getattr(state, f"section{i}", None) is not None:
                sections_done.append(i)

        complete = total_placeholders == 0 and bool(sections_done) or (
            total_placeholders < 5 and "01-candidate-profile.md" in files_status
            and files_status["01-candidate-profile.md"]["placeholders"] == 0
        )

        return {
            "complete": complete,
            "path": state.path,
            "sections_done": sections_done,
            "placeholders_remaining": total_placeholders,
            "files": files_status,
        }

    def read_file(self, name: str) -> str:
        if name not in PROFILE_FILES:
            raise FileNotFoundError(name)
        path = self.profile_dir / name
        if not path.exists():
            raise FileNotFoundError(name)
        return path.read_text(encoding="utf-8")

    def write_file(self, name: str, content: str) -> None:
        path = self.profile_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def load_wizard_state(self) -> WizardState:
        if not self.wizard_state_path.exists():
            return WizardState()
        data = json.loads(self.wizard_state_path.read_text(encoding="utf-8"))
        return WizardState.model_validate(data)

    def save_wizard_state(self, state: WizardState) -> None:
        self.wizard_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.wizard_state_path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def save_section(self, section: int, data: dict) -> WizardState:
        model_cls = SECTION_MODELS[section]
        parsed = model_cls.model_validate(data)
        if section == 1 and isinstance(parsed, WizardSection1):
            from app.services.profile.language_skills import format_languages_line

            parsed = parsed.model_copy(
                update={"languages": format_languages_line(parsed.language_skills)}
            )
        state = self.load_wizard_state()
        state.path = "wizard"
        setattr(state, f"section{section}", parsed)
        self.save_wizard_state(state)
        return state

    def merge_cv_extract(
        self,
        extracted: dict,
        cv_text: str,
        *,
        career: dict | None = None,
    ) -> WizardState:
        state = self.load_wizard_state()
        state.path = "cv"
        state.cv_text = cv_text
        state.cv_extracted = extracted

        identity = extracted.get("identity", {})
        if identity:
            from app.services.profile.language_skills import (
                format_languages_line,
                parse_languages_text,
            )

            langs_text = identity.get("languages") or "Polski (native)"
            skills = parse_languages_text(langs_text)
            state.section1 = WizardSection1(
                full_name=identity.get("full_name") or "Kandydat",
                location=identity.get("location") or "",
                phone=identity.get("phone"),
                email=identity.get("email") or "email@example.com",
                linkedin=identity.get("linkedin"),
                github=identity.get("github"),
                language_skills=skills,
                languages=format_languages_line(skills) if skills else langs_text,
                employment_status=identity.get("employment_status") or "Aktywnie szukam pracy",
                constraints=identity.get("constraints"),
            )

        edu = extracted.get("education", [])
        if edu:
            from app.models.setup import EducationEntry

            state.section2 = WizardSection2(
                education=[EducationEntry(**e) for e in edu if e.get("degree")],
                certifications=_normalize_string_list(extracted.get("certifications", [])),
            )

        exp = extracted.get("experience", [])
        if exp:
            from app.models.setup import ExperienceEntry

            entries = []
            for e in exp:
                if not e.get("title"):
                    continue
                e.setdefault("company", "—")
                e.setdefault("start", "?")
                e.setdefault("bullets", [])
                entries.append(ExperienceEntry(**e))
            state.section3 = WizardSection3(
                experience=entries,
                projects=_normalize_string_list(extracted.get("projects", [])),
            )

        skills = extracted.get("skills", {})
        if skills:
            state.section4 = WizardSection4(
                programming_skills=skills.get("programming") or "",
                ml_skills=skills.get("ml"),
                domain_expertise=skills.get("domain"),
                tools=skills.get("tools"),
                other_skills=skills.get("other"),
            )

        pubs = extracted.get("publications", [])
        awards = extracted.get("awards", [])
        if pubs or awards:
            state.section5 = WizardSection5(
                publications=_normalize_string_list(pubs),
                awards=_normalize_string_list(awards),
            )

        if career:
            roles = career.get("target_roles") or []
            if roles or career.get("target_industries"):
                state.section7 = WizardSection7(
                    target_roles=roles,
                    target_industries=career.get("target_industries"),
                    excites=career.get("excites"),
                    deal_breakers=career.get("deal_breakers"),
                    must_haves=career.get("must_haves"),
                    salary_expectation=career.get("salary_expectation") or None,
                    location_constraints=career.get("location_constraints"),
                )
            role_titles = career.get("role_titles") or []
            if role_titles or career.get("city"):
                city = career.get("city") or (identity.get("location") or "").split(",")[0].strip() or "Warszawa"
                state.section9 = WizardSection9(
                    role_titles=role_titles,
                    key_skills=career.get("key_skills") or [],
                    city=city,
                    ideal_locations=career.get("ideal_locations") or [],
                    acceptable_locations=career.get("acceptable_locations") or [],
                    adjacent_roles=career.get("adjacent_roles") or [],
                )

        self.save_wizard_state(state)
        return state

    def generate_all_files(self, state: WizardState) -> List[str]:
        s1 = state.section1 or WizardSection1(
            full_name="Kandydat", location="", email="email@example.com"
        )
        s2 = state.section2 or WizardSection2()
        s3 = state.section3 or WizardSection3()
        s4 = state.section4 or WizardSection4(programming_skills="")
        s5 = state.section5 or WizardSection5()
        s6 = state.section6 or WizardSection6()
        s7 = state.section7 or WizardSection7()
        s8 = state.section8 or WizardSection8()
        s9 = state.section9 or WizardSection9()

        written: List[str] = []

        self.write_file(
            "01-candidate-profile.md",
            gen_01(self.settings, s1, s2, s3, s4, s5, s8),
        )
        written.append("01-candidate-profile.md")

        self.write_file("02-behavioral-profile.md", gen_02(s1, s6))
        written.append("02-behavioral-profile.md")

        self.write_file("04-job-evaluation.md", gen_04(self.profile_dir, s4, s7))
        written.append("04-job-evaluation.md")

        self.write_file("05-cv-templates.md", gen_05(s1, s4, s7))
        written.append("05-cv-templates.md")

        self.write_file("07-interview-prep.md", gen_07(s3))
        written.append("07-interview-prep.md")

        self.write_file(
            "CLAUDE.md",
            gen_claude(self.profile_dir, s1, s2, s3, s4, s5, s6, s7),
        )
        written.append("CLAUDE.md")

        self.write_file("search-queries.md", gen_search_queries(s4, s7, s9))
        written.append("search-queries.md")

        return written

    def regenerate_search_queries_file(self) -> List[str]:
        """Rebuild search-queries.md from current wizard section 9 (and 4/7)."""
        state = self.load_wizard_state()
        s4 = state.section4 or WizardSection4(programming_skills="")
        s7 = state.section7 or WizardSection7()
        s9 = state.section9 or WizardSection9()
        self.write_file("search-queries.md", gen_search_queries(s4, s7, s9))
        return ["search-queries.md"]
