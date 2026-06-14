"""CV output language helpers (aligned with job posting language)."""
from __future__ import annotations

import re
from typing import List

from app.services.cv.types import CvDraftData, EducationEntry, ExperienceEntry

_POLISH_DIACRITICS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
_POLISH_WORDS = re.compile(
    r"\b(zarządzanie|odpowiedzialność|współ|dział|pracy|firmy|zespołem|rozwój|budowa|nadzór)\b",
    re.I,
)
_ENGLISH_WORDS = re.compile(
    r"\b(the|and|with|for|led|managed|responsible|operations|development|team|company)\b",
    re.I,
)

_TITLE_EN = {
    "członek komisji rewizyjnej": "Audit Committee Member",
    "zastępca dyrektora działu handlowego": "Deputy Commercial Director",
    "specjalista ds. wsparcia sprzedaży": "Sales Support Specialist",
    "doradca handlowy": "Commercial Advisor",
    "kierownik biura handlowego": "Commercial Office Manager",
}

_LOCATION_EN = {
    "woj. zachodniopomorskie, polska": "Poland",
    "woj. zachodniopomorskie, Polska": "Poland",
}

_CITY_EN = {
    "warszawa": "Warsaw",
    "wrocław": "Wroclaw",
    "kraków": "Krakow",
    "gdańsk": "Gdansk",
    "poznań": "Poznan",
    "łódź": "Lodz",
}

# Offline PL→EN fallback for master/wizard bullets when LLM translation is unavailable.
_BULLET_TRANSLATIONS_PL_EN: dict[str, str] = {
    "Zarządzanie całością operacji firmy oraz zespołami Delivery, BA, FC, PM, Dev i QA.": (
        "Managing end-to-end company operations and teams across Delivery, BA, FC, PM, Dev, and QA."
    ),
    "Odpowiedzialność za efektywność projektów Odoo, skalowanie organizacji i standaryzację metod pracy.": (
        "Accountable for Odoo project delivery efficiency, organizational scaling, and standardized ways of working."
    ),
    "Zarządzanie budżetem, marżą i wdrożeniem narzędzi KPI.": (
        "Managing budget, margin, and KPI tooling implementation."
    ),
    "Tworzenie struktur kompetencyjnych oraz modelu end-to-end sales--delivery--support.": (
        "Building competency structures and an end-to-end sales-delivery-support operating model."
    ),
    "Nadzór nad strategicznym kierunkiem rozwoju firmy.": (
        "Overseeing the company's strategic direction and long-term growth."
    ),
    "Definiowanie wizji produktowej integrującej Odoo z agentami AI do automatyzacji workflow.": (
        "Defining product vision integrating Odoo with AI agents for workflow automation."
    ),
    "Monitorowanie kluczowych metryk finansowych i operacyjnych.": (
        "Monitoring key financial and operational metrics."
    ),
    "Współodpowiedzialność za strategiczny rozwój spółki ERP/Odoo.": (
        "Co-leading strategic growth of the ERP/Odoo business."
    ),
    "Budowa oferty konsultingowej i ekspansji na rynku SMB i mid-market.": (
        "Building consulting offerings and expansion in SMB and mid-market segments."
    ),
    "Współtworzenie długoterminowej strategii produktowej dla usług chmurowych, automatyzacji procesów, raportowania, integracji i komponentów AI.": (
        "Co-creating long-term product strategy for cloud services, process automation, reporting, integrations, and AI components."
    ),
    "Zbudowanie od podstaw działalności operacyjnej i komercyjnej spółki.": (
        "Built the company's operational and commercial capabilities from the ground up."
    ),
    "Opracowanie koncepcji biznesowej, strategii rozwoju, marki, oferty i procesów.": (
        "Developed business concept, growth strategy, brand, service offering, and core processes."
    ),
    "Nadzór nad działalnością organizacji zrzeszającej firmy z branży IT regionu Pomorza Zachodniego.": (
        "Providing oversight for a regional IT cluster representing member companies in West Pomerania."
    ),
    "Wspieranie przejrzystości finansowej i zgodności działań z celami statutowymi.": (
        "Supporting financial transparency and compliance with statutory objectives."
    ),
    "Tworzenie struktur kompetencyjnych oraz modelu end-to-end sales--delivery--support.": (
        "Building competency structures and an end-to-end sales-delivery-support operating model."
    ),
    "Tworzenie struktur kompetencyjnych oraz modelu end-to-end sales–delivery–support.": (
        "Building competency structures and an end-to-end sales-delivery-support operating model."
    ),
    "Nadzór nad jakością delivery oraz współpraca z zarządem przy strategii i roadmapie.": (
        "Overseeing delivery quality and partnering with leadership on strategy and roadmap."
    ),
    "Optymalizacja procesów CI/CD dla wdrożeń Odoo.": (
        "Optimizing CI/CD processes for Odoo deployments."
    ),
    "Monitorowanie metryk produktywności zespołów.": (
        "Monitoring team productivity metrics."
    ),
    "Redukcja czasu delivery o 20%.": (
        "Achieved a 20% reduction in delivery time."
    ),
    "Uporządkowanie metryk operacyjnych i poprawa widoczności obciążenia zespołów.": (
        "Improved operational metrics and workforce utilization visibility."
    ),
    "Doradztwo w ekspansji rynkowej i rozwoju usług ERP + AI.": (
        "Advising on market expansion and ERP + AI service development."
    ),
    "Udział w kluczowych decyzjach dotyczących struktury organizacyjnej, polityki cenowej i partnerstw technologicznych.": (
        "Contributing to key decisions on organizational structure, pricing, and technology partnerships."
    ),
    "Nadzór nad roadmapą rozwoju modułów Odoo z integracjami AI.": (
        "Supervising the Odoo module roadmap with AI integrations."
    ),
    "Pozyskanie pierwszych klientów i wejście na rynek.": (
        "Acquired initial clients and launched go-to-market entry."
    ),
    "Odpowiedzialność za sprzedaż, marketing i rozwój kanałów pozyskiwania klientów.": (
        "Led sales, marketing, and customer acquisition channels."
    ),
    "Prowadzenie analiz biznesowych i przedwdrożeniowych dla klientów.": (
        "Conducted business analysis and pre-implementation planning for clients."
    ),
    "Nadzór nad realizacją projektów wdrożeniowych ERP oraz zarządzanie portfelem projektów.": (
        "Oversaw ERP implementation projects and managed the project portfolio."
    ),
    "Organizacja pracy zespołów konsultingowych i deweloperskich.": (
        "Organized consulting and development teams."
    ),
    "Rekrutacja, planowanie, rozwój kompetencji i budowa struktury.": (
        "Recruited talent, planned capacity, and built team structures."
    ),
    "Budowa i optymalizacja procesów operacyjnych, delivery i obsługi klienta.": (
        "Built and optimized operational, delivery, and customer success processes."
    ),
    "Odpowiedzialność za wyniki finansowe, rentowność projektów i rozwój przychodów.": (
        "Accountable for financial results, project profitability, and revenue growth."
    ),
    "Reprezentowanie firmy w relacjach z kluczowymi klientami i partnerami technologicznymi.": (
        "Represented the company with key clients and technology partners."
    ),
    "Wdrożenie procesów Agile/Scrum w delivery projektów Odoo.": (
        "Introduced Agile/Scrum practices into Odoo delivery."
    ),
    "Zbudowanie działalności od zera.": (
        "Built the business from scratch."
    ),
    "Redukcja churnu klientów o 15% dzięki poprawie obsługi posprzedażowej.": (
        "Reduced client churn by 15% through improved post-delivery customer success."
    ),
    "Udział w kształtowaniu kierunków współpracy biznes–nauka.": (
        "Shaped business-academia collaboration initiatives."
    ),
    "Reprezentowanie interesów około 100 firm członkowskich.": (
        "Represented the interests of approximately 100 member companies."
    ),
    "Przeprowadzanie audytów wewnętrznych i raportowanie rekomendacji usprawnień.": (
        "Conducted internal audits and reported improvement recommendations."
    ),
    "Wdrażanie dashboardów analitycznych w Odoo do śledzenia KPI operacyjnych i prognozowania obciążenia zespołów.": (
        "Implemented analytics dashboards in Odoo for operational KPIs and workforce forecasting."
    ),
    "Koordynowanie procesów związanych z kreowaniem przyszłości firmy.": (
        "Coordinated processes related to the company's future growth planning."
    ),
    "Operacyjne organizowanie i kontrolowanie pracy działu handlowego.": (
        "Organized and controlled day-to-day sales department operations."
    ),
    "Pozyskiwanie klientów, organizacja spotkań i prezentacja oferty.": (
        "Acquired clients, organized meetings, and presented the service offering."
    ),
    "Sprzedaż produktów i usług, obsługa zamówień i przetargów.": (
        "Managed product and service sales, orders, and tenders."
    ),
    "Analiza rynku i rozwój kanałów dystrybucji.": (
        "Analyzed markets and developed distribution channels."
    ),
}


def translate_bullet_offline(bullet: str) -> str:
    text = (bullet or "").strip()
    if not text:
        return text
    if text in _BULLET_TRANSLATIONS_PL_EN:
        return _BULLET_TRANSLATIONS_PL_EN[text]
    normalized = text.replace("–", "-").replace("—", "-")
    for src, dst in _BULLET_TRANSLATIONS_PL_EN.items():
        if src.replace("–", "-").replace("—", "-") == normalized:
            return dst
    return text


def apply_offline_english_bullets(draft: CvDraftData) -> CvDraftData:
    """Last-resort EN bullets when LLM translation is unavailable."""
    from app.config import get_settings
    from app.services.cv.experience import _norm_exp_key, parse_experience_from_master

    master_by_key = {
        _norm_exp_key(e.title, e.company): e for e in parse_experience_from_master(get_settings())
    }
    localized: List[ExperienceEntry] = []
    for entry in draft.experience_entries:
        key = _norm_exp_key(entry.title, entry.company)
        source_bullets = entry.bullets
        master_entry = master_by_key.get(key)
        if master_entry and master_entry.bullets:
            source_bullets = master_entry.bullets
        bullets = [translate_bullet_offline(b) for b in source_bullets]
        bullets = [b for b in bullets if b and not text_looks_polish(b)]
        if not bullets and source_bullets:
            bullets = [translate_bullet_offline(source_bullets[0])]
        localized.append(
            ExperienceEntry(
                period=entry.period,
                title=entry.title,
                company=entry.company,
                location=entry.location,
                bullets=bullets,
            )
        )
    draft.experience_entries = localized
    return draft


def normalize_cv_language(language: str | None) -> str:
    code = (language or "pl").strip().lower()
    if code.startswith("en") or code in ("english", "angielski"):
        return "en"
    return "pl"


def cv_language_label(language: str) -> str:
    return "English" if normalize_cv_language(language) == "en" else "Polish"


def languages_line_for(language: str) -> str:
    from app.services.profile.language_skills import languages_line_fallback

    return languages_line_fallback(normalize_cv_language(language))


def languages_line_from_profile(
    skills: list,
    cv_lang: str,
) -> str:
    from app.services.profile.language_skills import format_languages_cv_line

    if skills:
        return format_languages_cv_line(skills, normalize_cv_language(cv_lang))
    return languages_line_for(cv_lang)


def references_line_for(language: str) -> str:
    if normalize_cv_language(language) == "en":
        return "Available upon request."
    return "Więcej referencji na żądanie."


def text_looks_polish(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) < 12:
        return False
    if _POLISH_DIACRITICS.search(t):
        return True
    return bool(_POLISH_WORDS.search(t))


def text_looks_english(text: str) -> bool:
    t = (text or "").strip()
    if not t or text_looks_polish(t):
        return False
    return bool(_ENGLISH_WORDS.search(t))


def _draft_texts(draft: CvDraftData) -> List[str]:
    texts = [draft.profile_statement, draft.languages_line, draft.references_line]
    texts.extend(draft.awards)
    for entry in draft.experience_entries:
        texts.extend([entry.title, entry.company, entry.location, *entry.bullets])
    for edu in draft.education_entries:
        texts.extend([edu.degree, edu.institution, edu.detail])
    return [t for t in texts if t]


def pdf_entries_language_mismatch(draft: CvDraftData, language: str) -> bool:
    from app.services.cv.experience import select_experience_for_pdf

    entries = select_experience_for_pdf(
        draft.experience_entries,
        draft.emphasis_jobs,
        max_entries=6,
    )
    texts: List[str] = []
    for entry in entries:
        texts.extend([entry.title, *entry.bullets])
    if not texts:
        return draft_has_language_mismatch(draft, language)
    lang = normalize_cv_language(language)
    pl_hits = sum(1 for t in texts if text_looks_polish(t))
    en_hits = sum(1 for t in texts if text_looks_english(t))
    if lang == "en":
        return pl_hits > 0
    return en_hits > 0


def draft_has_language_mismatch(draft: CvDraftData, language: str) -> bool:
    lang = normalize_cv_language(language)
    texts = _draft_texts(draft)
    if not texts:
        return False
    pl_hits = sum(1 for t in texts if text_looks_polish(t))
    en_hits = sum(1 for t in texts if text_looks_english(t))
    if lang == "en":
        return pl_hits > 0
    return en_hits > 0


def localize_job_title(title: str, language: str) -> str:
    if normalize_cv_language(language) != "en":
        return title
    key = (title or "").strip().lower()
    return _TITLE_EN.get(key, title)


def _localize_city_fragment(text: str) -> str:
    part = (text or "").strip()
    if not part:
        return part
    mapped = _CITY_EN.get(part.lower())
    return mapped if mapped else part


def localize_location(location: str, language: str) -> str:
    if normalize_cv_language(language) != "en":
        return location
    loc = (location or "").strip()
    for src, dst in _LOCATION_EN.items():
        loc = loc.replace(src, dst)
    loc = loc.replace("woj. zachodniopomorskie,", "").replace("  ", " ").strip(" ,")
    if loc.endswith("Polska"):
        loc = loc.replace("Polska", "Poland").strip(" ,")
    if " / " in loc:
        loc = " / ".join(_localize_city_fragment(p) for p in loc.split(" / "))
    elif "/" in loc:
        loc = " / ".join(_localize_city_fragment(p) for p in loc.split("/"))
    else:
        loc = _localize_city_fragment(loc)
    return loc or location


def _localize_experience_entries(
    entries: List[ExperienceEntry],
    language: str,
) -> List[ExperienceEntry]:
    lang = normalize_cv_language(language)
    localized: List[ExperienceEntry] = []
    for entry in entries:
        period = (entry.period or "").replace("obecnie", "Present").replace("Obecnie", "Present")
        localized.append(
            ExperienceEntry(
                period=period,
                title=localize_job_title(entry.title, lang),
                company=entry.company,
                location=localize_location(entry.location, lang),
                bullets=list(entry.bullets),
            )
        )
    return localized


def localize_identity(identity: dict, language: str) -> dict:
    out = dict(identity)
    if normalize_cv_language(language) == "en":
        out["location"] = localize_location(out.get("location", ""), language)
    return out


def localize_education_entries(entries: List[EducationEntry], language: str) -> List[EducationEntry]:
    if normalize_cv_language(language) != "en":
        return entries
    out: List[EducationEntry] = []
    for ed in entries:
        degree = ed.degree
        if degree.lower() == "licencjat":
            degree = "Bachelor's Degree"
        detail = ed.detail
        if "Informatyka i Ekonometria" in detail:
            detail = "Computer Science and Econometrics"
        institution = ed.institution
        if "Zachodniopomorska Szkoła Biznesu" in institution:
            institution = "West Pomeranian Business School (University of Applied Sciences)"
        out.append(
            EducationEntry(
                period=ed.period,
                degree=degree,
                institution=institution,
                location=localize_location(ed.location, language),
                detail=detail,
            )
        )
    return out


def _english_experience_from_profile(profile_md: str) -> List[ExperienceEntry]:
    from app.services.cv.experience import (
        _is_placeholder_bullet,
        merge_experience_bullets,
        parse_experience_from_profile,
    )

    english_entries: List[ExperienceEntry] = []
    for entry in parse_experience_from_profile(profile_md):
        bullets = [
            b
            for b in entry.bullets
            if not _is_placeholder_bullet(b) and not text_looks_polish(b)
        ]
        if bullets:
            english_entries.append(
                ExperienceEntry(
                    period=entry.period,
                    title=entry.title,
                    company=entry.company,
                    location=entry.location,
                    bullets=bullets,
                )
            )
    return english_entries


def polish_pdf_bullet_samples(draft: CvDraftData, language: str, *, limit: int = 2) -> List[str]:
    from app.services.cv.experience import select_experience_for_pdf

    lang = normalize_cv_language(language)
    if lang != "en":
        return []
    samples: List[str] = []
    for entry in select_experience_for_pdf(draft.experience_entries, draft.emphasis_jobs, max_entries=6):
        for bullet in entry.bullets:
            if text_looks_polish(bullet):
                samples.append(bullet[:120])
                if len(samples) >= limit:
                    return samples
    return samples


def apply_static_cv_language(
    draft: CvDraftData,
    language: str,
    *,
    profile_md: str = "",
) -> CvDraftData:
    """Non-LLM labels: languages line, references, titles, education."""
    from app.services.cv.experience import merge_experience_bullets

    lang = normalize_cv_language(language)
    draft.cv_language = lang
    draft.languages_line = languages_line_for(lang)
    draft.references_line = references_line_for(lang)
    draft.education_entries = localize_education_entries(draft.education_entries, lang)
    draft.experience_entries = _localize_experience_entries(draft.experience_entries, lang)
    if lang == "en" and profile_md:
        profile_en = _english_experience_from_profile(profile_md)
        if profile_en:
            draft.experience_entries = merge_experience_bullets(
                draft.experience_entries, profile_en
            )
    if lang == "en":
        draft.awards = [a for a in draft.awards if not text_looks_polish(a)]
    if lang == "en" and pdf_entries_language_mismatch(draft, lang):
        draft = apply_offline_english_bullets(draft)
        draft.experience_entries = _localize_experience_entries(draft.experience_entries, lang)
    return draft
