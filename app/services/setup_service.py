from __future__ import annotations

import logging
from typing import List

from app.llm.client import BielikClient
from app.llm.token_budgets import BEHAVIORAL
from app.llm.structured import extract_json
from app.models.setup import CVImportResponse, SetupFinalizeResponse, WizardState
from app.prompts.loader import render_prompt
from app.services.cv_import_service import CvImportService
from app.services.profile.language_skills import LANGUAGE_OPTIONS, LEVEL_OPTIONS
from app.services.profile_service import ProfileService

logger = logging.getLogger(__name__)

WIZARD_SECTIONS = [
    {
        "id": 1,
        "title": "Tożsamość i kontakt",
        "fields": [
            {"name": "full_name", "label": "Imię i nazwisko", "type": "text", "required": True},
            {"name": "location", "label": "Lokalizacja (miasto)", "type": "text", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": True},
            {"name": "phone", "label": "Telefon", "type": "text"},
            {"name": "linkedin", "label": "LinkedIn URL", "type": "url"},
            {"name": "github", "label": "GitHub URL", "type": "url"},
            {
                "name": "language_skills",
                "label": "Języki i poziomy",
                "type": "language_list",
                "min_items": 3,
            },
            {"name": "employment_status", "label": "Status zatrudnienia", "type": "text"},
            {"name": "constraints", "label": "Ograniczenia (dojazd, rodzina)", "type": "textarea"},
        ],
    },
    {
        "id": 2,
        "title": "Edukacja",
        "fields": [
            {"name": "education", "label": "Wykształcenie", "type": "education_list"},
            {"name": "certifications", "label": "Certyfikaty", "type": "string_list"},
        ],
    },
    {
        "id": 3,
        "title": "Doświadczenie zawodowe",
        "fields": [
            {"name": "experience", "label": "Stanowiska", "type": "experience_list"},
            {"name": "projects", "label": "Projekty niezależne", "type": "string_list"},
        ],
    },
    {
        "id": 4,
        "title": "Umiejętności techniczne",
        "fields": [
            {"name": "programming_skills", "label": "Języki programowania", "type": "textarea", "required": True},
            {"name": "ml_skills", "label": "ML/AI", "type": "textarea"},
            {"name": "domain_expertise", "label": "Domena", "type": "textarea"},
            {"name": "tools", "label": "Narzędzia", "type": "textarea"},
            {"name": "other_skills", "label": "Inne", "type": "textarea"},
        ],
    },
    {
        "id": 5,
        "title": "Publikacje i nagrody (opcjonalnie)",
        "fields": [
            {"name": "publications", "label": "Publikacje", "type": "string_list"},
            {"name": "awards", "label": "Nagrody", "type": "string_list"},
        ],
    },
    {
        "id": 6,
        "title": "Profil behawioralny (opcjonalnie)",
        "fields": [
            {"name": "thrive_in", "label": "W jakim środowisku dobrze pracujesz?", "type": "textarea"},
            {"name": "drains_energy", "label": "Co wyczerpuje energię?", "type": "textarea"},
            {"name": "team_style", "label": "Styl pracy w zespole", "type": "textarea"},
            {"name": "decision_style", "label": "Podejmowanie decyzji", "type": "textarea"},
            {"name": "communication_style", "label": "Styl komunikacji", "type": "textarea"},
            {"name": "notes", "label": "Dodatkowe uwagi", "type": "textarea"},
        ],
    },
    {
        "id": 7,
        "title": "Cele kariery",
        "fields": [
            {"name": "target_roles", "label": "Docelowe stanowiska", "type": "string_list", "required": True},
            {"name": "target_industries", "label": "Branże", "type": "textarea"},
            {"name": "excites", "label": "Co Cię motywuje?", "type": "textarea"},
            {"name": "deal_breakers", "label": "Deal-breakers", "type": "textarea"},
            {"name": "must_haves", "label": "Must-haves", "type": "textarea"},
            {"name": "salary_expectation", "label": "Oczekiwania finansowe", "type": "text"},
            {"name": "avoid_environments", "label": "Środowiska do unikania", "type": "textarea"},
            {"name": "location_constraints", "label": "Lokalizacja / dojazd", "type": "textarea"},
        ],
    },
    {
        "id": 8,
        "title": "Referencje (opcjonalnie)",
        "fields": [
            {"name": "references", "label": "Referencje", "type": "reference_list"},
        ],
    },
    {
        "id": 9,
        "title": "Konfiguracja wyszukiwania",
        "fields": [
            {"name": "role_titles", "label": "Tytuły do wyszukiwania (3-8)", "type": "string_list", "required": True},
            {"name": "key_skills", "label": "Słowa kluczowe", "type": "string_list", "required": True},
            {"name": "target_companies", "label": "Docelowe firmy", "type": "string_list"},
            {"name": "city", "label": "Miasto główne", "type": "text", "placeholder": "np. Warszawa"},
            {"name": "region", "label": "Województwo", "type": "text", "placeholder": "np. mazowieckie"},
            {"name": "country", "label": "Kraj", "type": "text", "placeholder": "Polska"},
            {"name": "ideal_locations", "label": "Idealne lokalizacje", "type": "string_list"},
            {"name": "acceptable_locations", "label": "Akceptowalne lokalizacje", "type": "string_list"},
            {"name": "borderline_locations", "label": "Graniczne lokalizacje", "type": "string_list"},
            {"name": "too_far_locations", "label": "Zbyt odległe lokalizacje", "type": "string_list"},
            {"name": "portals", "label": "Portale", "type": "string_list"},
            {"name": "adjacent_roles", "label": "Role sąsiednie", "type": "string_list"},
        ],
    },
]


def _collect_gaps(state: WizardState) -> List[str]:
    gaps: List[str] = []
    if not state.section1:
        gaps.append("Sekcja 1 — tożsamość i kontakt")
    elif state.section1:
        if not state.section1.language_skills:
            gaps.append("Sekcja 1 — języki i poziomy (min. 3)")
        if not state.section1.constraints:
            gaps.append("Sekcja 1 — ograniczenia lokalizacji (constraints)")
    if not state.section2 or not state.section2.education:
        gaps.append("Sekcja 2 — wykształcenie")
    if not state.section3 or not state.section3.experience:
        gaps.append("Sekcja 3 — doświadczenie zawodowe")
    if not state.section4 or not state.section4.programming_skills:
        gaps.append("Sekcja 4 — umiejętności techniczne")
    if not state.section6:
        gaps.append("Sekcja 6 — profil behawioralny (opcjonalnie, uzupełnij ręcznie)")
    if not state.section7 or not state.section7.target_roles:
        gaps.append("Sekcja 7 — cele kariery")
    if not state.section8:
        gaps.append("Sekcja 8 — referencje (opcjonalnie)")
    if not state.section9 or not state.section9.role_titles:
        gaps.append("Sekcja 9 — zapytania wyszukiwania")
    return gaps


class SetupService:
    def __init__(self):
        self.profile = ProfileService()
        self.llm = BielikClient()
        self.cv_import = CvImportService(self.llm)

    def get_wizard_schema(self) -> dict:
        state = self.profile.load_wizard_state()
        return {
            "sections": WIZARD_SECTIONS,
            "state": state.model_dump(),
            "language_options": [{"value": k, "label": v} for k, v in LANGUAGE_OPTIONS],
            "level_options": [{"value": k, "label": v} for k, v in LEVEL_OPTIONS],
        }

    async def import_cv(self, cv_text: str) -> CVImportResponse:
        gaps: List[str] = []
        warnings: List[str] = []

        llm_ok = (await self.llm.healthcheck()).get("ok", False)
        extracted: dict = {}
        career: dict = {}

        if llm_ok:
            extracted, extract_warnings = await self.cv_import.extract_from_cv(cv_text)
            warnings.extend(extract_warnings)
            if extracted:
                career = await self.cv_import.infer_career_and_search(extracted, cv_text)
        else:
            gaps.append("Bielik niedostępny — uzupełnij dane ręcznie w wizardzie")

        if not extracted:
            extracted = {"identity": {}, "education": [], "experience": [], "skills": {}}
            if llm_ok:
                gaps.append("Nie udało się wyekstrahować danych z CV — sprawdź format lub skróć tekst")

        state = self.profile.merge_cv_extract(extracted, cv_text, career=career or None)
        gaps.extend(_collect_gaps(state))

        name = (extracted.get("identity") or {}).get("full_name", "Kandydat")
        exp_count = len(extracted.get("experience", []))
        sections_done = sum(1 for i in range(1, 10) if getattr(state, f"section{i}", None))
        summary = (
            f"Wyekstrahowano profil dla {name}: {exp_count} stanowisk, "
            f"{sections_done}/9 sekcji wstępnie uzupełnionych."
        )
        if warnings:
            summary += " " + "; ".join(warnings[:2])

        return CVImportResponse(
            extracted=extracted,
            summary=summary,
            gaps=gaps,
            wizard_state=state,
        )

    async def enhance_behavioral(self, state: WizardState) -> WizardState:
        s6 = state.section6
        if not s6:
            return state
        llm_ok = (await self.llm.healthcheck()).get("ok", False)
        if not llm_ok:
            return state
        prompt = render_prompt(
            "behavioral_synthesis.jinja2",
            thrive_in=s6.thrive_in or "",
            drains_energy=s6.drains_energy or "",
            team_style=s6.team_style or "",
            decision_style=s6.decision_style or "",
            communication_style=s6.communication_style or "",
            notes=s6.notes or "",
        )
        try:
            raw = await self.llm.chat_complete(
                [
                    {"role": "system", "content": "Zwracasz tylko JSON."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=BEHAVIORAL,
                temperature=0.2,
            )
            parsed = extract_json(raw)
            if isinstance(parsed, dict) and parsed.get("summary"):
                from app.models.setup import WizardSection6

                state.section6 = WizardSection6(
                    **s6.model_dump(),
                    notes=(s6.notes or "") + "\n\n[LLM synthesis]\n" + parsed.get("summary", ""),
                )
                self.profile.save_wizard_state(state)
        except Exception as exc:
            logger.warning("Behavioral synthesis failed: %s", exc)
        return state

    async def finalize(self) -> SetupFinalizeResponse:
        state = self.profile.load_wizard_state()
        if not state.section1:
            return SetupFinalizeResponse(
                success=False,
                files_written=[],
                message="Uzupełnij co najmniej sekcję 1 (tożsamość) przed finalizacją.",
            )

        state = await self.enhance_behavioral(state)
        written = self.profile.generate_all_files(state)

        return SetupFinalizeResponse(
            success=True,
            files_written=written,
            message=f"Zapisano {len(written)} plików profilu. Możesz uruchomić /api/scrape.",
        )
