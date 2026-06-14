"""Polskie etykiety UI — wspólne dla Python i JS."""

from __future__ import annotations

import json

LABELS: dict[str, dict[str, str]] = {
    "job_status": {
        "new": "Nowa",
        "evaluated": "Oceniona",
        "skipped": "Pominięta",
    },
    "fit": {
        "high": "Wysoki",
        "medium": "Średni",
        "low": "Niski",
        "strong": "Silny",
        "moderate": "Umiarkowany",
        "weak": "Słaby",
    },
    "tier": {
        "priority": "Priorytet",
        "review": "Do przeglądu",
        "skip": "Pomiń",
        "evaluate": "Kolejka oceny",
    },
    "hiring_stage": {
        "draft": "Szkic",
        "ready_to_send": "Gotowe do wysłania",
        "applied": "Wysłane",
        "screening": "Screening",
        "interview": "Rozmowa",
        "offer": "Oferta",
        "rejected": "Odrzucona",
        "archived": "Archiwum",
    },
    "pipeline_stage": {
        "parse": "Parsowanie",
        "evaluate": "Ocena",
        "proceed": "Decyzja",
        "draft": "Szkic CV",
        "review": "Recenzja",
        "pdf": "PDF",
        "checklist": "Checklist",
        "interview_prep": "Przygotowanie",
        "tracker": "Gotowe do wysłania",
        "done": "Gotowe",
    },
    "pipeline_status": {
        "pending": "Oczekuje",
        "running": "W toku",
        "waiting": "Czeka",
        "done": "Gotowe",
        "failed": "Błąd",
    },
    "doc_category": {
        "cv": "CV",
        "linkedin": "LinkedIn",
        "diplomas": "Dyplomy",
        "references": "Referencje",
        "applications": "Aplikacje",
    },
    "skip_reason": {
        "wrong_scoring": "Błędny scoring",
        "english_level": "Niewystarczający poziom języka angielskiego",
        "missing_skill": "Brak umiejętności lub certyfikatu",
        "domain_knowledge": "Brak wiedzy domenowej",
        "salary_low": "Zbyt niskie widełki płacowe",
        "other": "Inne",
        "auto_low_fit": "Niskie dopasowanie (quick fit)",
        "auto_low_score": "Zbyt niski wynik triażu",
        "auto_low_fit_and_score": "Niskie dopasowanie i niski wynik triażu",
        "auto_english_level": "Wymagany wysoki poziom angielskiego (fluent/C1+)",
        "auto_language_level": "Wymagany wyższy poziom języka niż w profilu",
    },
    "skip_source": {
        "manual": "Ręcznie",
        "auto_triage": "Auto (triaż)",
    },
    "reviewer_verdict": {
        "approve": "Zatwierdzone",
        "revise": "Do poprawy",
        "reject": "Odrzuć",
    },
    "verify_category": {
        "factual": "Fakty",
        "targeting": "Dopasowanie",
        "ats": "ATS",
        "consistency": "Spójność",
        "quality": "Jakość",
        "pdf": "PDF",
    },
    "triage_reason_token": {
        "reject_keyword": "Słowo odrzucenia profilu",
        "salary_far_below_b2b_threshold": "Widełki znacznie poniżej progu B2B",
        "salary_below_b2b_threshold": "Widełki poniżej progu B2B",
        "salary_estimated_below_threshold": "Szacowana pensja poniżej progu",
        "operations": "Operacje",
        "transformation": "Transformacja",
        "generic": "Ogólne dopasowanie",
        "Poza triażem": "Poza triażem",
        "english_fluent": "Wymagany fluent angielski",
        "english_excellent": "Wymagany excellent angielski",
        "english_c1": "Wymagany angielski C1",
        "english_c1_plus": "Wymagany angielski C1+",
        "lang_gap": "Luka językowa względem profilu",
    },
}


def label(category: str, key: str | None) -> str:
    if not key:
        return "—"
    return LABELS.get(category, {}).get(key, key)


def labels_json() -> str:
    return json.dumps(LABELS, ensure_ascii=False)
