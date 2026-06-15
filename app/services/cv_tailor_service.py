"""LLM-driven CV tailoring to job postings (multi-pass for n_ctx=4096)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

DraftProgressFn = Optional[Callable[[str], Awaitable[None]]]

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.llm.structured import extract_json
from app.llm.token_budgets import (
    CV_COVER,
    CV_EXPERIENCE,
    CV_HEADER,
    CV_TARGETS,
    CV_TARGETS_AND_HEADER,
    CV_TRANSLATE,
    CV_TRANSLATE_COMPACT,
)
from app.models.apply import JobParsed
from app.prompts.loader import render_prompt
from app.services.apply_prompt_utils import (
    CV_EXPERIENCE_BATCH_MAX,
    CV_EXPERIENCE_BATCH_SIZE,
    CV_PROFILE_MAX,
    CV_TAILOR_TOP_JOBS,
    CV_TARGETS_JOB_MAX,
    compact_job_targets,
    experience_source_for_cv,
    job_posting_excerpt,
    llm_failure_note,
    master_summary_excerpt,
    profile_excerpt_for_cv,
    safe_max_tokens,
)
from app.services.cv.ats_enrichment import apply_pm_ats_enrichment, normalize_job_targets
from app.services.cv.competencies import (
    ensure_role_in_profile_statement,
    merge_competencies,
    normalize_competency_line,
    role_headline_for_job,
)
from app.services.cv.experience import select_experience_for_pdf
from app.services.cv.language import (
    apply_static_cv_language,
    cv_language_label,
    draft_has_language_mismatch,
    normalize_cv_language,
    pdf_entries_language_mismatch,
    apply_offline_english_bullets,
    polish_pdf_bullet_samples,
    references_line_for,
    text_looks_polish,
)
from app.services.cv.master import load_master_ats_summary, resolve_master_cv_text
from app.services.cv.truth_guard import SkillTruthIndex, build_skill_truth_index
from app.services.job_fetcher import _role_implies_english
from app.services.cv_builder import (
    CvDraftData,
    ExperienceEntry,
    _norm_exp_key,
    cv_draft_from_llm_dict,
)
from app.services.latex_utils import coerce_latex_text

logger = logging.getLogger(__name__)

_COVER_TEXT_KEYS = frozenset({"salutation", "opening", "body", "motivation", "closing"})
_TARGET_KEYS = (
    "role_title",
    "must_have_keywords",
    "nice_to_have_keywords",
    "tools_explicit",
    "soft_skills",
    "normalized_skills",
    "keyword_placement_hints",
    "priority_themes",
    "emphasis_jobs",
    "profile_angle",
    "avoid_framing",
)


def _fallback_job_targets(
    job: JobParsed,
    *,
    truth: SkillTruthIndex,
    profile_md: str,
) -> dict:
    """Heuristic must_have/tools when LLM target extraction is incomplete."""
    from app.services.scrape.posting_extract import extract_key_description

    excerpt = extract_key_description(job.raw_text or "", url="")
    temp_job = job
    if len(excerpt) >= 80:
        temp_job = job.model_copy(update={"raw_text": excerpt})
    return normalize_job_targets(
        {"role_title": job.role, "must_have_keywords": [], "tools_explicit": []},
        job=temp_job,
        truth=truth,
        profile_md=profile_md,
    )


def _normalize_cover_fields(data: dict) -> dict:
    out: dict = {}
    for key, val in data.items():
        if key == "bullets":
            out[key] = [coerce_latex_text(b) for b in (val or []) if b is not None]
        elif key in _COVER_TEXT_KEYS:
            out[key] = coerce_latex_text(val)
    return out


class CvTailorError(ValueError):
    """CV generation requires LLM tailoring and it failed."""


@dataclass
class CvTailorResult:
    cv_draft: CvDraftData
    cover_data: dict
    job_targets: dict = field(default_factory=dict)
    tailoring_decisions: List[str] = field(default_factory=list)
    llm_degraded: bool = False


class CvTailorService:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        llm_health: Optional[dict] = None,
        on_progress: DraftProgressFn = None,
        company_slug: str = "",
        job_url: Optional[str] = None,
    ):
        self.settings = settings or get_settings()
        self.llm = BielikClient(self.settings)
        self.n_ctx = getattr(self.settings, "llm_context_size", 2048)
        self._json_failures = 0
        self._llm_health = llm_health
        self._truth_index: Optional[SkillTruthIndex] = None
        self._on_progress = on_progress
        self._company_slug = company_slug
        self._job_url = job_url

    async def _emit_progress(self, message: str) -> None:
        if self._on_progress:
            await self._on_progress(message)

    def _targets_cache_path(self) -> Optional[Path]:
        if not self._company_slug:
            return None
        return self.settings.data_dir / "applications" / self._company_slug / "job_targets_cache.json"

    def _load_targets_cache(self) -> tuple[Optional[dict], Optional[dict]]:
        path = self._targets_cache_path()
        if not path or not path.exists() or not self._job_url:
            return None, None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None, None
        if data.get("url") != self._job_url:
            return None, None
        targets = data.get("targets")
        if not isinstance(targets, dict) or not targets.get("must_have_keywords"):
            return None, None
        header = data.get("header")
        cached_header = header if isinstance(header, dict) and header.get("profile_statement") else None
        return targets, cached_header

    def _save_targets_cache(self, targets: dict, header: Optional[dict] = None) -> None:
        path = self._targets_cache_path()
        if not path or not self._job_url:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict = {"url": self._job_url, "targets": targets}
        if header is not None:
            payload["header"] = header
        elif path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing.get("header"), dict):
                    payload["header"] = existing["header"]
            except (json.JSONDecodeError, OSError):
                pass
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_header_cache(self, header: dict) -> None:
        path = self._targets_cache_path()
        if not path or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if data.get("url") != self._job_url:
            return
        data["header"] = header
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _ensure_truth_index(self, profile_md: str) -> SkillTruthIndex:
        if self._truth_index is None:
            self._truth_index = build_skill_truth_index(
                profile_md=profile_md, settings=self.settings
            )
        return self._truth_index

    async def _require_llm(self) -> None:
        if self._llm_health is None:
            self._llm_health = await self.llm.healthcheck()
        if self._llm_health.get("ok") and self._llm_health.get("inference_ok"):
            return
        if await self.llm.is_ready(probe=True):
            self._llm_health = {**(self._llm_health or {}), "ok": True, "inference_ok": True}
            return
        hc = self._llm_health or {}
        err = hc.get("error") or "nieznany błąd"
        raise CvTailorError(
            f"Generowanie CV wymaga działającego LLM (Bielik). "
            f"Sprawdź {self.llm.base_url} — {err}"
        )

    async def _chat_json(
        self,
        messages: List[dict],
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> dict:
        budget = safe_max_tokens(messages, max_tokens, n_ctx=self.n_ctx)
        if budget < 96:
            raise CvTailorError(
                f"Prompt za długi dla kontekstu LLM ({self.n_ctx} tokenów). "
                "Skróć ogłoszenie lub profil."
            )
        raw = await self.llm.chat_complete(
            messages,
            max_tokens=budget,
            temperature=temperature,
        )
        parsed = extract_json(raw)
        if not isinstance(parsed, dict) and self._json_failures == 0:
            repair_messages = messages + [
                {"role": "assistant", "content": raw[:800]},
                {"role": "user", "content": "Return valid JSON only. No markdown fences or commentary."},
            ]
            raw_retry = await self.llm.chat_complete(
                repair_messages,
                max_tokens=min(budget, 512),
                temperature=0.0,
            )
            parsed = extract_json(raw_retry)
        if not isinstance(parsed, dict):
            self._json_failures += 1
            raise CvTailorError("LLM zwrócił niepoprawny JSON.")
        if self._truth_index is not None:
            strict = getattr(self.settings, "ats_truth_guard_strict", True)
            parsed = self._truth_index.sanitize_dict(parsed, strict=strict)
        return parsed

    async def extract_job_targets(self, job: JobParsed, *, profile_md: str = "") -> dict:
        truth = self._ensure_truth_index(profile_md)
        prompt = render_prompt(
            "job_posting_targets.jinja2",
            role=job.role,
            company=job.company,
            job_posting=job_posting_excerpt(job.raw_text, max_chars=CV_TARGETS_JOB_MAX),
            allowed_tools_sample=truth.sample_for_prompt(40),
        )
        messages = [
            {"role": "system", "content": "JSON only."},
            {"role": "user", "content": prompt},
        ]
        parsed = await self._chat_json(messages, max_tokens=CV_TARGETS, temperature=0.0)
        if not parsed.get("must_have_keywords"):
            fallback = _fallback_job_targets(job, truth=truth, profile_md=profile_md)
            if fallback.get("must_have_keywords"):
                parsed["must_have_keywords"] = fallback["must_have_keywords"]
                for key in ("tools_explicit", "nice_to_have_keywords"):
                    if fallback.get(key) and not parsed.get(key):
                        parsed[key] = fallback[key]
            else:
                raise CvTailorError("LLM nie zwrócił analizy ogłoszenia (must_have_keywords).")
        must = truth.filter_keywords(parsed.get("must_have_keywords") or [])
        if must:
            parsed["must_have_keywords"] = must
        return normalize_job_targets(parsed, job=job, truth=truth, profile_md=profile_md)

    async def extract_targets_and_header(
        self,
        job: JobParsed,
        *,
        profile_md: str,
        competencies_baseline: List[str],
        master_summary: str,
        truth: SkillTruthIndex,
    ) -> tuple[dict, dict]:
        prompt = render_prompt(
            "draft_cv_targets_and_header.jinja2",
            role=job.role,
            company=job.company,
            job_posting=job_posting_excerpt(job.raw_text, max_chars=CV_TARGETS_JOB_MAX),
            profile=profile_excerpt_for_cv(profile_md, max_chars=CV_PROFILE_MAX),
            competencies_baseline="\n".join(f"- {c}" for c in competencies_baseline[:6]),
            master_summary=master_summary[:700],
            cv_language_name=cv_language_label(job.language),
            allowed_tools_sample=truth.sample_for_prompt(40),
        )
        messages = [
            {"role": "system", "content": "JSON only."},
            {"role": "user", "content": prompt},
        ]
        parsed = await self._chat_json(messages, max_tokens=CV_TARGETS_AND_HEADER, temperature=0.05)
        degrade_notes: List[str] = []
        if not parsed.get("must_have_keywords"):
            fallback = _fallback_job_targets(job, truth=truth, profile_md=profile_md)
            if fallback.get("must_have_keywords"):
                parsed["must_have_keywords"] = fallback["must_have_keywords"]
                for key in ("tools_explicit", "nice_to_have_keywords"):
                    if fallback.get(key) and not parsed.get(key):
                        parsed[key] = fallback[key]
                degrade_notes.append("targets: must_have z ekstrakcji ogłoszenia (LLM puste)")
            else:
                raise CvTailorError("LLM nie zwrócił analizy ogłoszenia (must_have_keywords).")
        profile_statement = parsed.get("profile_statement")
        if not profile_statement:
            profile_statement = ensure_role_in_profile_statement(master_summary[:700], job.role)
            degrade_notes.append("header: profile_statement z master_summary (LLM puste)")
        targets_raw = {k: parsed.get(k) for k in _TARGET_KEYS if parsed.get(k) is not None}
        must = truth.filter_keywords(targets_raw.get("must_have_keywords") or [])
        if must:
            targets_raw["must_have_keywords"] = must
        targets = normalize_job_targets(targets_raw, job=job, truth=truth, profile_md=profile_md)
        notes = [str(n) for n in (parsed.get("tailoring_notes") or []) if n]
        notes.extend(degrade_notes)
        header = {
            "profile_statement": profile_statement,
            "competencies": parsed.get("competencies") or [],
            "competency_keywords": parsed.get("competency_keywords") or [],
            "tailoring_notes": notes,
        }
        return targets, header

    async def _resolve_targets(
        self,
        job: JobParsed,
        *,
        profile_md: str,
        competencies_baseline: List[str],
        master_summary: str,
        truth: SkillTruthIndex,
    ) -> tuple[dict, Optional[dict]]:
        cached_targets, cached_header = self._load_targets_cache()
        if cached_targets:
            await self._emit_progress("draft: targets (cache)")
            if cached_header:
                await self._emit_progress("draft: header (cache)")
            return cached_targets, cached_header
        fast = getattr(self.settings, "pipeline_fast_draft", True)
        if fast:
            await self._emit_progress("draft: targets+header")
            targets, header = await self.extract_targets_and_header(
                job,
                profile_md=profile_md,
                competencies_baseline=competencies_baseline,
                master_summary=master_summary,
                truth=truth,
            )
            self._save_targets_cache(targets, header=header)
            return targets, header
        await self._emit_progress("draft: targets")
        targets = await self.extract_job_targets(job, profile_md=profile_md)
        self._save_targets_cache(targets)
        return targets, None

    async def _tailor_header(
        self,
        job: JobParsed,
        *,
        profile_md: str,
        targets_json: str,
        competencies_baseline: List[str],
        master_summary: str,
        truth: SkillTruthIndex,
    ) -> dict:
        prompt = render_prompt(
            "draft_cv_header.jinja2",
            role=job.role,
            company=job.company,
            job_targets_json=targets_json,
            profile=profile_excerpt_for_cv(profile_md, max_chars=CV_PROFILE_MAX),
            competencies_baseline="\n".join(f"- {c}" for c in competencies_baseline[:6]),
            master_summary=master_summary[:700],
            cv_language_name=cv_language_label(job.language),
            allowed_tools_sample=truth.sample_for_prompt(30),
        )
        messages = [
            {"role": "system", "content": "JSON only."},
            {"role": "user", "content": prompt},
        ]
        parsed = await self._chat_json(messages, max_tokens=CV_HEADER, temperature=0.1)
        if not parsed.get("profile_statement"):
            parsed["profile_statement"] = ensure_role_in_profile_statement(
                master_summary[:700], job.role
            )
            notes = list(parsed.get("tailoring_notes") or [])
            notes.append("header: profile_statement z master_summary (LLM puste)")
            parsed["tailoring_notes"] = notes
        return parsed

    async def _tailor_experience_batch(
        self,
        job: JobParsed,
        batch: List[ExperienceEntry],
        *,
        targets_json: str,
        first_batch: bool,
        truth: SkillTruthIndex,
    ) -> tuple[List[ExperienceEntry], List[str]]:
        prompt = render_prompt(
            "draft_cv_experience.jinja2",
            role=job.role,
            company=job.company,
            job_targets_json=targets_json,
            experience_source=experience_source_for_cv(
                batch, max_chars=CV_EXPERIENCE_BATCH_MAX, max_bullets=3
            ),
            first_batch=first_batch,
            cv_language_name=cv_language_label(job.language),
            allowed_tools_sample=truth.sample_for_prompt(30),
        )
        messages = [
            {"role": "system", "content": "JSON only. Tailor experience bullets."},
            {"role": "user", "content": prompt},
        ]
        parsed = await self._chat_json(messages, max_tokens=CV_EXPERIENCE, temperature=0.15)
        notes = [str(n) for n in (parsed.get("tailoring_notes") or []) if n]
        llm_by_key: dict[str, dict] = {}
        for e in parsed.get("experience_entries") or []:
            if isinstance(e, dict) and e.get("title"):
                llm_by_key[_norm_exp_key(str(e.get("title", "")), str(e.get("company", "")))] = e
        out: List[ExperienceEntry] = []
        for fb in batch:
            le = llm_by_key.get(_norm_exp_key(fb.title, fb.company))
            bullets = list(fb.bullets)
            period, title, company, location = fb.period, fb.title, fb.company, fb.location
            if le:
                llm_bullets = [str(b) for b in (le.get("bullets") or []) if b]
                if llm_bullets:
                    bullets = llm_bullets
                period = str(le.get("period") or period)
                title = str(le.get("title") or title)
                company = str(le.get("company") or company)
                location = str(le.get("location") or location)
            if not bullets:
                continue
            out.append(
                ExperienceEntry(
                    period=period,
                    title=title,
                    company=company,
                    location=location,
                    bullets=bullets,
                )
            )
        if not out:
            return list(batch), notes
        return out, notes

    async def _translate_draft(
        self,
        draft: CvDraftData,
        job: JobParsed,
        language: str,
        *,
        only_remaining: bool = False,
    ) -> CvDraftData:
        entries = select_experience_for_pdf(
            draft.experience_entries,
            draft.emphasis_jobs,
            max_entries=6,
        )
        if only_remaining and normalize_cv_language(language) == "en":
            entries = [e for e in entries if any(text_looks_polish(b) for b in e.bullets)]
        if not entries:
            return draft

        translate_profile = not only_remaining
        for batch_start in range(0, len(entries), 2):
            batch = entries[batch_start : batch_start + 2]
            payload: dict = {
                "experience_entries": [
                    {
                        "period": e.period,
                        "title": e.title,
                        "company": e.company,
                        "location": e.location,
                        "bullets": e.bullets,
                    }
                    for e in batch
                ],
            }
            if translate_profile and batch_start == 0:
                payload["profile_statement"] = draft.profile_statement
                payload["awards"] = draft.awards
                translate_profile = False
            prompt = render_prompt(
                "cv_translate.jinja2",
                role=job.role,
                company=job.company,
                cv_language_name=cv_language_label(language),
                draft_json=json.dumps(payload, ensure_ascii=False),
            )
            messages = [
                {"role": "system", "content": "JSON only. Translate CV content."},
                {"role": "user", "content": prompt},
            ]
            parsed = await self._chat_json(messages, max_tokens=CV_TRANSLATE, temperature=0.1)
            if parsed.get("profile_statement"):
                draft.profile_statement = coerce_latex_text(parsed.get("profile_statement"))
            if parsed.get("awards"):
                draft.awards = [str(a) for a in parsed.get("awards") if a][:3]
            translated_by_key = {
                _norm_exp_key(str(e.get("title", "")), str(e.get("company", ""))): e
                for e in (parsed.get("experience_entries") or [])
                if isinstance(e, dict) and e.get("title")
            }
            merged_exp: List[ExperienceEntry] = []
            for entry in draft.experience_entries:
                key = _norm_exp_key(entry.title, entry.company)
                te = translated_by_key.get(key)
                if not te:
                    merged_exp.append(entry)
                    continue
                bullets = [str(b) for b in (te.get("bullets") or []) if b] or list(entry.bullets)
                merged_exp.append(
                    ExperienceEntry(
                        period=str(te.get("period") or entry.period),
                        title=str(te.get("title") or entry.title),
                        company=str(te.get("company") or entry.company),
                        location=str(te.get("location") or entry.location),
                        bullets=bullets,
                    )
                )
            draft.experience_entries = merged_exp
        return draft

    async def translate_pdf_entries_only(
        self,
        draft: CvDraftData,
        job: JobParsed,
        language: str,
    ) -> CvDraftData:
        """Compact translation pass for PDF-selected experience only."""
        entries = select_experience_for_pdf(
            draft.experience_entries,
            draft.emphasis_jobs,
            max_entries=6,
        )
        if not entries:
            return draft
        payload = {
            "experience_entries": [
                {
                    "period": e.period,
                    "title": e.title,
                    "company": e.company,
                    "location": e.location,
                    "bullets": e.bullets[:4],
                }
                for e in entries
            ],
            "profile_statement": draft.profile_statement,
            "awards": draft.awards[:3],
        }
        prompt = render_prompt(
            "cv_translate.jinja2",
            role=job.role,
            company=job.company,
            cv_language_name=cv_language_label(language),
            draft_json=json.dumps(payload, ensure_ascii=False),
        )
        messages = [
            {"role": "system", "content": "JSON only. Translate CV content."},
            {"role": "user", "content": prompt},
        ]
        parsed = await self._chat_json(messages, max_tokens=CV_TRANSLATE_COMPACT, temperature=0.05)
        if parsed.get("profile_statement"):
            draft.profile_statement = coerce_latex_text(parsed.get("profile_statement"))
        if parsed.get("awards"):
            draft.awards = [str(a) for a in parsed.get("awards") if a][:3]
        translated_by_key = {
            _norm_exp_key(str(e.get("title", "")), str(e.get("company", ""))): e
            for e in (parsed.get("experience_entries") or [])
            if isinstance(e, dict) and e.get("title")
        }
        merged_exp: List[ExperienceEntry] = []
        for entry in draft.experience_entries:
            key = _norm_exp_key(entry.title, entry.company)
            te = translated_by_key.get(key)
            if not te:
                merged_exp.append(entry)
                continue
            bullets = [str(b) for b in (te.get("bullets") or []) if b] or list(entry.bullets)
            merged_exp.append(
                ExperienceEntry(
                    period=str(te.get("period") or entry.period),
                    title=str(te.get("title") or entry.title),
                    company=str(te.get("company") or entry.company),
                    location=str(te.get("location") or entry.location),
                    bullets=bullets,
                )
            )
        draft.experience_entries = merged_exp
        return draft

    def _align_cv_language_offline(
        self,
        draft: CvDraftData,
        job: JobParsed,
        *,
        profile_md: str = "",
    ) -> tuple[CvDraftData, List[str]]:
        lang = normalize_cv_language(job.language)
        warnings: List[str] = []
        draft = apply_static_cv_language(draft, lang, profile_md=profile_md)
        if lang == "en" and (
            pdf_entries_language_mismatch(draft, lang)
            or draft_has_language_mismatch(draft, lang)
        ):
            draft = apply_offline_english_bullets(draft)
            if not pdf_entries_language_mismatch(draft, lang):
                warnings.append("CV language aligned via offline bullet translation fallback.")
            else:
                samples = polish_pdf_bullet_samples(draft, lang)
                if samples:
                    warnings.append(
                        "CV language mismatch (PL bullets in EN CV): "
                        + " | ".join(samples)
                    )
        draft.profile_statement = ensure_role_in_profile_statement(
            draft.profile_statement, job.role
        )
        return draft, warnings

    async def _align_cv_language(
        self,
        draft: CvDraftData,
        job: JobParsed,
        *,
        profile_md: str = "",
        llm_degraded: bool = False,
    ) -> tuple[CvDraftData, List[str]]:
        if llm_degraded:
            return self._align_cv_language_offline(draft, job, profile_md=profile_md)
        lang = normalize_cv_language(job.language)
        warnings: List[str] = []
        draft = apply_static_cv_language(draft, lang, profile_md=profile_md)
        if not pdf_entries_language_mismatch(draft, lang) and not draft_has_language_mismatch(
            draft, lang
        ):
            draft.profile_statement = ensure_role_in_profile_statement(
                draft.profile_statement, job.role
            )
            return draft, warnings

        fast_en = lang == "en" and getattr(self.settings, "pipeline_fast_draft", True)
        if fast_en:
            draft = apply_offline_english_bullets(draft)
            draft = apply_static_cv_language(draft, lang, profile_md=profile_md)
            if not pdf_entries_language_mismatch(draft, lang) and not draft_has_language_mismatch(
                draft, lang
            ):
                warnings.append("CV language aligned via offline bullet translation.")
                draft.profile_statement = ensure_role_in_profile_statement(
                    draft.profile_statement, job.role
                )
                return draft, warnings
            await self._emit_progress("draft: translate (compact)")
            try:
                draft = await self.translate_pdf_entries_only(draft, job, lang)
                draft = apply_static_cv_language(draft, lang, profile_md=profile_md)
            except Exception as exc:
                logger.warning("compact EN translate failed: %s", exc)
            if not pdf_entries_language_mismatch(draft, lang) and not draft_has_language_mismatch(
                draft, lang
            ):
                warnings.append("CV language aligned via compact LLM translate.")
                draft.profile_statement = ensure_role_in_profile_statement(
                    draft.profile_statement, job.role
                )
                return draft, warnings

        try:
            draft = await self._translate_draft(draft, job, lang)
            retry_loops = 1 if fast_en else 2
            for _ in range(retry_loops):
                if not pdf_entries_language_mismatch(draft, lang):
                    break
                draft = await self._translate_draft(
                    draft, job, lang, only_remaining=True
                )
            if pdf_entries_language_mismatch(draft, lang):
                draft = await self.translate_pdf_entries_only(draft, job, lang)
        except Exception as exc:
            logger.warning("CV language translation failed, trying PDF-only pass: %s", exc)
            try:
                draft = await self.translate_pdf_entries_only(draft, job, lang)
            except Exception as pdf_exc:
                logger.warning("PDF-only translation failed: %s", pdf_exc)
                warnings.append(f"CV language translation failed: {str(exc)[:120]}")
        if pdf_entries_language_mismatch(draft, lang) and lang == "en":
            draft = apply_offline_english_bullets(draft)
            if pdf_entries_language_mismatch(draft, lang):
                samples = polish_pdf_bullet_samples(draft, lang)
                if samples:
                    warnings.append(
                        "CV language mismatch (PL bullets in EN CV): "
                        + " | ".join(samples)
                    )
            else:
                warnings.append("CV language aligned via offline bullet translation fallback.")
        draft.profile_statement = ensure_role_in_profile_statement(
            draft.profile_statement, job.role
        )
        return draft, warnings

    async def tailor_cv_draft(
        self,
        job: JobParsed,
        *,
        baseline: CvDraftData,
        profile_md: str,
        job_targets: dict,
        header: Optional[dict] = None,
    ) -> tuple[CvDraftData, List[str]]:
        truth = self._ensure_truth_index(profile_md)
        targets_json = compact_job_targets(job_targets)
        master_summary = load_master_ats_summary(
            self.settings, language=job.language
        ) or master_summary_excerpt(resolve_master_cv_text(self.settings), max_chars=700)
        if header is None:
            await self._emit_progress("draft: header")
            header = await self._tailor_header(
                job,
                profile_md=profile_md,
                targets_json=targets_json,
                competencies_baseline=baseline.competencies,
                master_summary=master_summary,
                truth=truth,
            )
            self._save_header_cache(header)
        all_notes = [str(n) for n in (header.get("tailoring_notes") or []) if n]

        entries = baseline.experience_entries
        tailor_count = min(len(entries), CV_TAILOR_TOP_JOBS)
        max_batches = int(getattr(self.settings, "ats_max_experience_llm_batches", 2) or 2)
        fast = getattr(self.settings, "pipeline_fast_draft", True)
        batch_size = CV_EXPERIENCE_BATCH_SIZE
        if fast and max_batches == 1:
            batch_size = min(4, CV_TAILOR_TOP_JOBS)
        llm_entry_cap = min(tailor_count, max_batches * batch_size)
        tailored: List[ExperienceEntry] = []
        batch_num = 0
        total_batches = max(1, (llm_entry_cap + batch_size - 1) // batch_size)

        for i in range(0, llm_entry_cap, batch_size):
            batch_num += 1
            await self._emit_progress(f"draft: experience {batch_num}/{total_batches}")
            batch = entries[i : i + batch_size]
            chunk, notes = await self._tailor_experience_batch(
                job,
                batch,
                targets_json=targets_json,
                first_batch=(i == 0),
                truth=truth,
            )
            tailored.extend(chunk)
            all_notes.extend(notes)

        # Starsze stanowiska — bez LLM, z baseline (oszczędność kontekstu)
        if len(entries) > llm_entry_cap:
            tailored.extend(entries[llm_entry_cap:])

        merged_competencies = merge_competencies(
            baseline.competencies,
            [
                coerce_latex_text(normalize_competency_line(c))
                for c in (header.get("competencies") or [])
            ],
            job_targets,
            competency_keywords=truth.filter_keywords(
                [str(k) for k in (header.get("competency_keywords") or []) if k]
            ),
        )
        merged_dict = {
            "profile_statement": coerce_latex_text(header.get("profile_statement")),
            "competencies": merged_competencies,
            "emphasis_jobs": list(job_targets.get("emphasis_jobs") or []),
            "role_headline": role_headline_for_job(job.role),
            "experience_entries": [
                {
                    "period": e.period,
                    "title": e.title,
                    "company": e.company,
                    "location": e.location,
                    "bullets": e.bullets,
                }
                for e in tailored
            ],
            "education_entries": [
                {
                    "period": ed.period,
                    "degree": ed.degree,
                    "institution": ed.institution,
                    "location": ed.location,
                    "detail": ed.detail,
                }
                for ed in baseline.education_entries
            ],
            "languages_line": baseline.languages_line,
            "publications": baseline.publications,
            "awards": baseline.awards,
            "certifications": baseline.certifications,
            "references_line": references_line_for(job.language),
            "cv_language": normalize_cv_language(job.language),
        }
        draft = cv_draft_from_llm_dict(merged_dict, baseline)
        if not draft.experience_entries:
            raise CvTailorError("LLM zwrócił CV bez sekcji doświadczenia.")
        draft, lang_warnings = await self._align_cv_language(draft, job, profile_md=profile_md)
        all_notes.extend(lang_warnings)

        enrich_enabled = getattr(self.settings, "ats_enrich_pm_roles", True)
        min_lead_kw = int(getattr(self.settings, "ats_summary_min_lead_keywords", 2) or 2)
        enriched_summary, enriched_comp, enriched_exp, enrich_notes = apply_pm_ats_enrichment(
            profile_statement=draft.profile_statement,
            competencies=draft.competencies,
            experience_entries=draft.experience_entries,
            job=job,
            profile_md=profile_md,
            job_targets=job_targets,
            truth=truth,
            enabled=enrich_enabled,
            min_lead_keywords=min_lead_kw,
        )
        draft.profile_statement = enriched_summary
        draft.competencies = enriched_comp
        draft.experience_entries = enriched_exp
        all_notes.extend(enrich_notes)
        cv_lang = normalize_cv_language(job.language)
        draft = apply_static_cv_language(draft, cv_lang, profile_md=profile_md)
        if cv_lang == "en":
            draft, post_enrich_warnings = self._align_cv_language_offline(
                draft, job, profile_md=profile_md
            )
            all_notes.extend(post_enrich_warnings)
        elif not pdf_entries_language_mismatch(draft, cv_lang) and not draft_has_language_mismatch(
            draft, cv_lang
        ):
            draft.profile_statement = ensure_role_in_profile_statement(
                draft.profile_statement, job.role
            )
        else:
            draft, post_enrich_warnings = await self._align_cv_language(
                draft, job, profile_md=profile_md
            )
            all_notes.extend(post_enrich_warnings)
        return draft, all_notes

    async def tailor_cover(
        self,
        job: JobParsed,
        *,
        profile_md: str,
        behavioral_md: str,
        job_targets: dict,
        cover_default: dict,
    ) -> dict:
        prompt = render_prompt(
            "draft_cover.jinja2",
            profile=profile_excerpt_for_cv(profile_md, max_chars=450),
            behavioral=behavioral_md[:400],
            job_posting=job_posting_excerpt(job.raw_text, max_chars=600),
            job_targets_json=compact_job_targets(job_targets),
            role=job.role,
            company=job.company,
            language=job.language,
        )
        messages = [
            {"role": "system", "content": "JSON only."},
            {"role": "user", "content": prompt},
        ]
        parsed = await self._chat_json(messages, max_tokens=CV_COVER, temperature=0.25)
        cover_default.update(_normalize_cover_fields(parsed))
        return cover_default

    def _decisions_from_targets(self, job: JobParsed, targets: dict, llm_notes: List[str]) -> List[str]:
        decisions = [
            f"ATS keywords: {', '.join(targets.get('must_have_keywords', [])[:8])}",
            f"Kąt profilu: {(targets.get('profile_angle') or '')[:160]}",
            f"Dopasowanie pod {job.role} @ {job.company}",
            f"Multi-pass LLM (n_ctx={self.n_ctx})",
        ]
        themes = targets.get("priority_themes") or []
        if themes:
            decisions.append(f"Tematy: {', '.join(themes[:5])}")
        ats_notes = [n for n in llm_notes if n.startswith("ATS enrichment")]
        other_notes = [n for n in llm_notes if not n.startswith("ATS enrichment")]
        for note in ats_notes[:2] + other_notes[:3]:
            prefix = "" if note.startswith("ATS enrichment") else "Tailoring: "
            decisions.append(f"{prefix}{note[:140]}")
        if self._truth_index and self._truth_index.violations:
            decisions.append(
                f"Truth guard: {len(self._truth_index.violations)} sanitized term(s)"
            )
        return decisions[:8]

    def _parallel_cover_enabled(self) -> bool:
        if not getattr(self.settings, "pipeline_parallel_cover", True):
            return False
        return max(1, int(getattr(self.settings, "llm_concurrency", 1))) >= 2

    async def _tailor_cv_and_cover(
        self,
        job: JobParsed,
        *,
        baseline: CvDraftData,
        profile_md: str,
        behavioral_md: str,
        cover_default: dict,
        targets: dict,
        header: Optional[dict],
    ) -> tuple[CvDraftData, dict, List[str]]:
        """Run CV tailoring; optionally overlap cover LLM when llm_concurrency >= 2."""
        parallel = self._parallel_cover_enabled()
        cover_task: asyncio.Task | None = None
        if parallel:
            cover_task = asyncio.create_task(
                self.tailor_cover(
                    job,
                    profile_md=profile_md,
                    behavioral_md=behavioral_md,
                    job_targets=targets,
                    cover_default=dict(cover_default),
                )
            )
        cv_draft, llm_notes = await self.tailor_cv_draft(
            job,
            baseline=baseline,
            profile_md=profile_md,
            job_targets=targets,
            header=header,
        )
        await self._emit_progress("draft: cover")
        if cover_task is not None:
            cover = await cover_task
        else:
            cover = await self.tailor_cover(
                job,
                profile_md=profile_md,
                behavioral_md=behavioral_md,
                job_targets=targets,
                cover_default=dict(cover_default),
            )
        return cv_draft, cover, llm_notes

    async def tailor_application(
        self,
        job: JobParsed,
        *,
        baseline: CvDraftData,
        profile_md: str,
        behavioral_md: str,
        cover_default: dict,
    ) -> CvTailorResult:
        await self._require_llm()
        self._truth_index = None
        try:
            truth = self._ensure_truth_index(profile_md)
            master_summary = load_master_ats_summary(
                self.settings, language=job.language
            ) or master_summary_excerpt(resolve_master_cv_text(self.settings), max_chars=700)
            targets, header = await self._resolve_targets(
                job,
                profile_md=profile_md,
                competencies_baseline=baseline.competencies,
                master_summary=master_summary,
                truth=truth,
            )
            cv_draft, cover, llm_notes = await self._tailor_cv_and_cover(
                job,
                baseline=baseline,
                profile_md=profile_md,
                behavioral_md=behavioral_md,
                cover_default=cover_default,
                targets=targets,
                header=header,
            )
        except CvTailorError:
            raise
        except Exception as exc:
            raise CvTailorError(llm_failure_note(exc, True, n_ctx=self.n_ctx)) from exc

        decisions = self._decisions_from_targets(job, targets, llm_notes)
        return CvTailorResult(
            cv_draft=cv_draft,
            cover_data=cover,
            job_targets=targets,
            tailoring_decisions=decisions,
        )

    async def _baseline_only_fallback(
        self,
        job: JobParsed,
        *,
        baseline: CvDraftData,
        profile_md: str,
        cover_default: dict,
        exc: CvTailorError,
        skipped_tailor_calls: int = 0,
        llm_degraded: bool = False,
    ) -> CvTailorResult:
        logger.warning("CV tailor failed, using baseline: %s", exc)
        if skipped_tailor_calls:
            note = (
                f"LLM fallback: offline baseline, skipped {skipped_tailor_calls} tailor calls. "
                f"{str(exc)[:160]}"
            )
        else:
            note = f"CV baseline — LLM niedostępny: {str(exc)[:200]}"
        effective_lang = normalize_cv_language(job.language)
        if effective_lang != "en" and _role_implies_english(job.role):
            effective_lang = "en"
        draft = apply_static_cv_language(baseline, effective_lang, profile_md=profile_md)
        draft.role_headline = role_headline_for_job(job.role)
        if effective_lang == "en":
            draft = apply_offline_english_bullets(draft)
        draft, lang_warnings = await self._align_cv_language(
            draft, job, profile_md=profile_md, llm_degraded=llm_degraded or skipped_tailor_calls > 0
        )
        return CvTailorResult(
            cv_draft=draft,
            cover_data=dict(cover_default),
            tailoring_decisions=[note, *lang_warnings],
            llm_degraded=llm_degraded or skipped_tailor_calls > 0,
        )

    async def tailor_application_with_fallback(
        self,
        job: JobParsed,
        *,
        baseline: CvDraftData,
        profile_md: str,
        behavioral_md: str,
        cover_default: dict,
    ) -> CvTailorResult:
        """LLM tailoring with baseline CV+cover when Bielik is offline or errors."""
        self._json_failures = 0
        self._truth_index = None
        try:
            await self._require_llm()
        except CvTailorError as exc:
            return await self._baseline_only_fallback(
                job,
                baseline=baseline,
                profile_md=profile_md,
                cover_default=dict(cover_default),
                exc=exc,
                llm_degraded=True,
            )
        try:
            truth = self._ensure_truth_index(profile_md)
            master_summary = load_master_ats_summary(
                self.settings, language=job.language
            ) or master_summary_excerpt(resolve_master_cv_text(self.settings), max_chars=700)
            targets, header = await self._resolve_targets(
                job,
                profile_md=profile_md,
                competencies_baseline=baseline.competencies,
                master_summary=master_summary,
                truth=truth,
            )
        except CvTailorError as exc:
            degraded = "niepoprawny JSON" in str(exc)
            return await self._baseline_only_fallback(
                job,
                baseline=baseline,
                profile_md=profile_md,
                cover_default=dict(cover_default),
                exc=exc,
                skipped_tailor_calls=4,
                llm_degraded=degraded,
            )
        try:
            cv_draft, cover, llm_notes = await self._tailor_cv_and_cover(
                job,
                baseline=baseline,
                profile_md=profile_md,
                behavioral_md=behavioral_md,
                cover_default=cover_default,
                targets=targets,
                header=header,
            )
        except CvTailorError as exc:
            skipped = 3 + max(0, self._json_failures)
            degraded = "niepoprawny JSON" in str(exc) or self._json_failures > 0
            return await self._baseline_only_fallback(
                job,
                baseline=baseline,
                profile_md=profile_md,
                cover_default=dict(cover_default),
                exc=exc,
                skipped_tailor_calls=skipped,
                llm_degraded=degraded,
            )
        except Exception as exc:
            raise CvTailorError(llm_failure_note(exc, True, n_ctx=self.n_ctx)) from exc

        decisions = self._decisions_from_targets(job, targets, llm_notes)
        return CvTailorResult(
            cv_draft=cv_draft,
            cover_data=cover,
            job_targets=targets,
            tailoring_decisions=decisions,
        )
