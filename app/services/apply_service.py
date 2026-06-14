from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.llm.token_budgets import EVALUATE, INTERVIEW_PREP, REVIEW
from app.llm.structured import extract_json
from app.models.apply import ApplyRequest, ApplyResponse, FitEvaluation, JobParsed, ReviewerResult
from app.prompts.loader import render_prompt
from app.search.searxng_client import SearXNGClient
from app.services.cv_builder import (
    CvDraftData,
    baseline_cv_draft,
    build_cv_tex as render_cv_tex,
    parse_identity,
)
from app.services.apply_prompt_utils import (
    REVIEWER_JOB_MAX,
    REVIEWER_PROFILE_MAX,
    framework_excerpt_for_eval,
    job_posting_excerpt,
    language_assessment_for_eval,
    llm_failure_note,
    profile_excerpt_for_cv,
    profile_excerpt_for_eval,
    sanitize_false_english_gap,
    sanitize_posting_gaps,
    tex_excerpt_for_review,
)
from app.services.cv_tailor_service import CvTailorService
from app.services.latex_utils import escape_latex
from app.services.latex_service import LatexService
from app.services.profile_service import ProfileService
from app.services.salary_service import SalaryService
from app.storage.db import Database

logger = logging.getLogger(__name__)


def slugify(value: str) -> str:
    s = value.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "_", s)
    return s[:40].strip("_") or "company"


_LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"sp\.?\s*z\s*o\.?\s*o\.?|s\.?\s*a\.?|spółka|spolka|llc|inc|gmbh|"
    r"polska|poland|group|holding"
    r")\b",
    re.I,
)


_POLISH_FILENAME_MAP = str.maketrans(
    {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
        "Ą": "A",
        "Ć": "C",
        "Ę": "E",
        "Ł": "L",
        "Ń": "N",
        "Ó": "O",
        "Ś": "S",
        "Ź": "Z",
        "Ż": "Z",
    }
)


def filename_token(value: str, *, max_len: int = 40) -> str:
    """ASCII-safe token for filenames (words joined with underscores)."""
    import unicodedata

    s = (value or "").strip().translate(_POLISH_FILENAME_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "_", s.strip())
    return s.strip("_")[:max_len] or "unknown"


def short_company_name(company: str) -> str:
    """Short recruiter-facing company label for filenames."""
    s = _LEGAL_SUFFIX_RE.sub("", (company or "").strip())
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split()
    if len(words) > 2:
        s = " ".join(words[:2])
    return filename_token(s, max_len=30)


def application_cv_filename(full_name: str, company: str, ext: str) -> str:
    return f"Resume_{filename_token(full_name)}_{short_company_name(company)}{ext}"


def application_cover_filename(full_name: str, company: str, ext: str) -> str:
    return f"Cover_{filename_token(full_name)}_{short_company_name(company)}{ext}"


class ApplyService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.llm = BielikClient(self.settings)
        self.search = SearXNGClient(self.settings)
        self.profile = ProfileService(self.settings)
        self.latex = LatexService(self.settings.repo_root, settings=self.settings)
        self.db = Database(self.settings.db_path)
        self.salary = SalaryService(self.settings)
        self.cv_dir = self.settings.repo_root / "cv"
        self.cover_dir = self.settings.repo_root / "cover_letters"
        self._llm_health: Optional[dict] = None
        self._last_tailor_degraded = False
        self._last_job_targets: dict = {}
        self._searxng_cache: dict[str, list] = {}

    async def prefetch_company_search(self, company: str) -> None:
        """Warm SearXNG cache during draft so review skips network wait."""
        if not company:
            return
        cache_key = slugify(company)
        if cache_key in self._searxng_cache:
            return
        try:
            results = await self.search.search_company(company, limit=3)
            self._searxng_cache[cache_key] = [r.to_dict() for r in results]
        except Exception as exc:
            logger.debug("prefetch company search failed: %s", exc)
            self._searxng_cache[cache_key] = []

    async def _llm_ready(self) -> bool:
        """Reuse pipeline probe when available; avoid duplicate probe_chat calls."""
        hc = self._llm_health
        if hc and hc.get("inference_ok"):
            return True
        ready = await self.llm.is_ready(probe=True)
        if ready:
            self._llm_health = {**(hc or {}), "ok": True, "inference_ok": True}
        return ready

    def _read_profile_bundle(self) -> dict:
        files = {}
        for name in (
            "01-candidate-profile.md",
            "02-behavioral-profile.md",
            "03-writing-style.md",
            "04-job-evaluation.md",
            "05-cv-templates.md",
            "06-cover-letter-templates.md",
        ):
            try:
                files[name] = self.profile.read_file(name)
            except FileNotFoundError:
                files[name] = ""
        return files

    async def evaluate(self, job: JobParsed, bundle: dict) -> FitEvaluation:
        llm_ok = await self._llm_ready()
        profile_md = bundle.get("01-candidate-profile.md", "")
        assessment = self.salary.assess(
            title=job.role,
            salary=None,
            description=job.raw_text,
        )
        salary_payload = assessment.to_dict()

        llm_error: Optional[Exception] = None
        if llm_ok:
            salary_note = (
                f"Wynagrodzenie (B2B/mies. szac.): {assessment.monthly_b2b_median} PLN, "
                f"próg: {self.salary.threshold_pln} PLN, "
                f"źródło: {assessment.source}, "
                f"{'OK' if assessment.meets_threshold else 'PONIŻEJ PROGU'}."
            )
            lang_note, english_ok = language_assessment_for_eval(profile_md, job.raw_text)
            prompt = render_prompt(
                "evaluate_fit.jinja2",
                profile_excerpt=profile_excerpt_for_eval(profile_md),
                evaluation_framework=framework_excerpt_for_eval(bundle.get("04-job-evaluation.md", "")),
                job_posting=job_posting_excerpt(job.raw_text),
                salary_assessment=salary_note,
                language_assessment=lang_note,
            )
            try:
                raw = await self.llm.chat_complete(
                    [
                        {
                            "role": "system",
                            "content": (
                                "Zwracasz wyłącznie poprawny JSON. Bez markdown. "
                                "Pole recommendation zawsze po polsku. "
                                "Przy ocenie języków używaj wyłącznie bloku CEFR z promptu."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=EVALUATE,
                    temperature=0.1,
                )
                parsed = extract_json(raw)
                if isinstance(parsed, dict):
                    parsed = sanitize_false_english_gap(parsed, english_ok)
                    parsed = sanitize_posting_gaps(parsed, job.raw_text)
                if isinstance(parsed, dict) and parsed.get("overall_fit"):
                    overall = parsed.get("overall_fit", "moderate")
                    if overall not in ("strong", "moderate", "weak"):
                        overall = "moderate"
                    overall = self.salary.adjust_overall_fit(overall, assessment)
                    rec = parsed.get("recommendation", "")
                    if not assessment.meets_threshold:
                        rec = (
                            f"[Wynagrodzenie poniżej progu B2B {self.salary.threshold_pln} PLN] {rec}"
                        ).strip()
                    return FitEvaluation(
                        skills_match=parsed.get("skills_match", {}),
                        experience_match=parsed.get("experience_match", {}),
                        behavioral_match=parsed.get("behavioral_match", {}),
                        location_match=parsed.get("location_match", {}),
                        salary_benchmark=salary_payload,
                        overall_fit=overall,
                        recommendation=rec,
                    )
                llm_error = ValueError("LLM nie zwrócił poprawnego JSON oceny dopasowania")
                logger.warning(
                    "evaluate_fit invalid JSON (type=%s, preview=%r)",
                    type(parsed).__name__,
                    (raw or "")[:120],
                )
            except Exception as exc:
                llm_error = exc
                logger.warning("evaluate_fit LLM failed: %s", exc)

        overall = self.salary.adjust_overall_fit("moderate", assessment)
        rec = llm_failure_note(llm_error, llm_ok) if llm_error else (
            "LLM niedostępny — kontynuuj ręczną weryfikację dopasowania."
        )
        if not assessment.meets_threshold:
            rec = f"[Wynagrodzenie poniżej progu B2B {self.salary.threshold_pln} PLN] {rec}"
        return FitEvaluation(
            skills_match={"score": 60, "note": "Ocena offline — uruchom Bielik dla pełnej analizy"},
            experience_match={"score": 60},
            behavioral_match={"score": 60},
            location_match={"pass": True},
            salary_benchmark=salary_payload,
            overall_fit=overall,
            recommendation=rec,
        )

    async def _draft_content(
        self,
        job: JobParsed,
        bundle: dict,
        *,
        company_slug: str = "",
        job_url: Optional[str] = None,
        on_progress=None,
    ) -> Tuple[CvDraftData, dict, List[str]]:
        profile = bundle.get("01-candidate-profile.md", "")
        behavioral = bundle.get("02-behavioral-profile.md", "")

        cv_baseline = baseline_cv_draft(
            role=job.role,
            company=job.company,
            profile_md=profile,
            language=job.language,
            settings=self.settings,
        )

        cover_default = {
            "salutation": "Dear Hiring Manager," if job.language == "en" else "Szanowny Zespół Rekrutacyjny,",
            "opening": f"I am writing to apply for the {job.role} position at {job.company}.",
            "body": "My background aligns with the requirements described in your posting.",
            "bullets": [
                "15+ years in operations, ERP (Odoo), and AI-enabled delivery leadership",
                "Track record reducing delivery time by 20% and improving KPI visibility",
                "Experience scaling B2B technology organizations from founder stage to COO level",
            ],
            "motivation": f"I am motivated to contribute to {job.company}'s operational excellence.",
            "closing": "I look forward to hearing from you.",
        }

        tailor = CvTailorService(
            self.settings,
            llm_health=getattr(self, "_llm_health", None),
            on_progress=on_progress,
            company_slug=company_slug,
            job_url=job_url,
        )
        result = await tailor.tailor_application_with_fallback(
            job,
            baseline=cv_baseline,
            profile_md=profile,
            behavioral_md=behavioral,
            cover_default=cover_default,
        )
        self._last_tailor_degraded = result.llm_degraded
        self._last_job_targets = result.job_targets or {}
        return result.cv_draft, result.cover_data, result.tailoring_decisions

    def _parse_identity(self, profile_md: str) -> dict:
        return parse_identity(profile_md)

    def build_cv_tex(self, company_slug: str, cv_data: CvDraftData, identity: dict) -> str:
        return render_cv_tex(cv_data, identity, company_slug)

    def build_cover_tex(self, company_slug: str, role_slug: str, cover_data: dict, identity: dict) -> str:
        bullets = "\n".join(
            f"    \\item {escape_latex(b)}" for b in cover_data.get("bullets", [])
        )
        linkedin = identity.get("linkedin", "")
        linkedin_part = f"\\href{{{linkedin}}}{{LinkedIn}} | " if linkedin and linkedin != "—" else ""

        return f"""\\documentclass[]{{cover}}
\\usepackage{{fancyhdr}}
\\pagestyle{{fancy}}
\\fancyhf{{}}
\\thispagestyle{{empty}}
\\renewcommand{{\\headrulewidth}}{{0pt}}
\\begin{{document}}
\\namesection{{}}{{\\Huge{{{escape_latex(identity['name'])}}}}}{{  \\href{{mailto:{identity['email']}}}{{{escape_latex(identity['email'])}}} | {escape_latex(identity['phone'])} | {linkedin_part}}}
\\currentdate{{\\today}}
\\lettercontent{{{escape_latex(cover_data.get('salutation',''))}}}
\\lettercontent{{{escape_latex(cover_data.get('opening',''))}}}
\\lettercontent{{{escape_latex(cover_data.get('body',''))}}}
{{\\raggedright\\fontspec[Path = OpenFonts/fonts/raleway/]{{Raleway-Medium}}\\fontsize{{11pt}}{{13pt}}\\selectfont
\\begin{{itemize}}
{bullets}
\\end{{itemize}}\\par}}
\\lettercontent{{{escape_latex(cover_data.get('motivation',''))}}}
\\lettercontent{{{escape_latex(cover_data.get('closing',''))}}}
\\begin{{flushright}}
\\closing{{Kind regards,}}
\\signature{{{escape_latex(identity['name'])}}}
\\end{{flushright}}
\\end{{document}}
"""

    def _apply_edits(self, content: str, edits: List[dict], file_key: str) -> str:
        for edit in edits or []:
            if not isinstance(edit, dict):
                continue
            f = edit.get("file", "")
            if f and file_key not in str(f) and not str(f).endswith(file_key):
                continue
            old = edit.get("old_string", "")
            new = edit.get("new_string", "")
            if isinstance(old, list):
                old = " ".join(str(x) for x in old)
            if isinstance(new, list):
                new = " ".join(str(x) for x in new)
            old, new = str(old), str(new)
            if old and old in content:
                content = content.replace(old, new, 1)
        return content

    def _complete_interview_prep_sections(self, text: str, job: JobParsed) -> str:
        """Uzupełnij brakujące sekcje, gdy model obetnie odpowiedź."""
        role = job.role or "to stanowisko"
        company = job.company or "firmę"
        fallbacks = [
            (
                "## Pytania, które warto zadać rekruterowi",
                f"""## Pytania, które warto zadać rekruterowi
- Jak wygląda typowy dzień pracy na stanowisku {role}?
- Jakie są najważniejsze wyzwania zespołu w najbliższych 6 miesiącach?
- Jak mierzycie sukces osoby na tej roli w {company}?
- Jaki jest następny etap procesu rekrutacyjnego i jego harmonogram?
- Czego oczekujecie od nowej osoby w pierwszych 90 dniach?""",
            ),
            (
                "## Trudne pytania — jak odpowiadać",
                f"""## Trudne pytania — jak odpowiadać
- **Dlaczego chcesz pracować w {company}?** — Połącz misję firmy z Twoim doświadczeniem operacyjnym i motywacją do skalowania procesów.
- **Opowiedz o sytuacji, gdy coś poszło nie tak.** — Użyj formatu STAR: konkretna sytuacja, Twoja odpowiedzialność, działania naprawcze, mierzalny efekt.
- **Czego brakuje Ci do idealnego dopasowania?** — Wskaż 1 lukę i jak aktywnie ją domykasz (kurs, projekt, mentoring) — bez deprecjonowania siebie.""",
            ),
            (
                "## Checklist na 24 h przed rozmową",
                """## Checklist na 24 h przed rozmową
- [ ] Przejrzyj CV i list motywacyjny wysłany do tej oferty
- [ ] Przygotuj 2–3 przykłady STAR i przećwicz je na głos
- [ ] Sprawdź link/ adres, nagłówki, kamerę i mikrofon (jeśli online)
- [ ] Przygotuj notatnik z pytaniami do rekrutera
- [ ] Zaplanuj 15 min buforu przed rozmową i wyłącz powiadomienia""",
            ),
        ]
        for marker, block in fallbacks:
            if marker not in text:
                text = text.rstrip() + "\n\n" + block + "\n"
        return text

    async def _generate_interview_prep(
        self,
        job: JobParsed,
        bundle: dict,
        company_slug: str,
        *,
        skip_llm: bool = False,
        llm_health: Optional[dict] = None,
    ) -> Optional[str]:
        if not getattr(self.settings, "pipeline_interview_prep_enabled", False):
            return None
        if skip_llm:
            return None
        framework = ""
        try:
            framework = self.profile.read_file("07-interview-prep.md")
        except FileNotFoundError:
            framework = bundle.get("04-job-evaluation.md", "")

        hc = llm_health if llm_health is not None else await self.llm.healthcheck()
        llm_ok = hc.get("ok", False)
        if not llm_ok or hc.get("inference_ok") is False:
            return None

        prompt = render_prompt(
            "interview_prep.jinja2",
            interview_framework=framework_excerpt_for_eval(framework, max_chars=400),
            profile=profile_excerpt_for_cv(bundle.get("01-candidate-profile.md", ""), max_chars=400),
            job_posting=job_posting_excerpt(job.raw_text, max_chars=600),
            role=job.role,
            company=job.company,
        )
        try:
            raw = await self.llm.chat_complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Jesteś coachem kariery. Pisz wyłącznie poprawny markdown po polsku. "
                            "Bez kodu ANSI, bez komentarzy meta, bez angielskich nagłówków."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=INTERVIEW_PREP,
                temperature=0.3,
                _skip_esc_guard=True,
            )
        except Exception as exc:
            logger.warning("interview prep failed: %s", exc)
            return None

        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw)
        text = text.replace("\x1b", "").strip()
        text = self._complete_interview_prep_sections(text, job)
        out_dir = self.settings.data_dir / "applications" / company_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "interview_prep.md"
        out_path.write_text(text, encoding="utf-8")
        return str(out_path.relative_to(self.settings.repo_root))

    async def _review(
        self,
        job: JobParsed,
        cv_tex: str,
        cover_tex: str,
        bundle: dict,
        *,
        skip_llm: bool = False,
        llm_health: Optional[dict] = None,
    ) -> ReviewerResult:
        cache_key = slugify(job.company)
        snippets = self._searxng_cache.get(cache_key)
        if snippets is None:
            snippets = []
            try:
                results = await self.search.search_company(job.company, limit=3)
                snippets = [r.to_dict() for r in results]
                self._searxng_cache[cache_key] = snippets
            except Exception as exc:
                logger.warning("company search failed: %s", exc)
                self._searxng_cache[cache_key] = []

        if skip_llm:
            return ReviewerResult(
                company_research_notes="; ".join(s["snippet"][:120] for s in snippets[:2]),
                overall_verdict="approve",
            )

        hc = llm_health if llm_health is not None else await self.llm.healthcheck()
        llm_ok = hc.get("ok", False)
        if not llm_ok:
            return ReviewerResult(
                company_research_notes="; ".join(s["snippet"][:120] for s in snippets[:2]),
                overall_verdict="approve",
            )

        prompt = render_prompt(
            "reviewer.jinja2",
            profile_excerpt=profile_excerpt_for_eval(
                bundle.get("01-candidate-profile.md", ""), max_chars=REVIEWER_PROFILE_MAX
            ),
            job_posting=job_posting_excerpt(job.raw_text, max_chars=REVIEWER_JOB_MAX),
            cv_draft=tex_excerpt_for_review(cv_tex),
            cover_draft=tex_excerpt_for_review(cover_tex),
            company_snippets=snippets,
        )
        try:
            raw = await self.llm.chat_complete(
                [{"role": "system", "content": "JSON only. Bez markdown."}, {"role": "user", "content": prompt}],
                max_tokens=REVIEW,
                temperature=0.2,
            )
            parsed = extract_json(raw)
            if isinstance(parsed, dict):
                return ReviewerResult(
                    structured_edits=parsed.get("structured_edits", []),
                    narrative=parsed.get("narrative", {}),
                    company_research_notes=parsed.get("company_research_notes", ""),
                    overall_verdict=parsed.get("overall_verdict", "revise"),
                )
        except Exception as exc:
            logger.warning("reviewer LLM failed: %s", exc)
            note = llm_failure_note(exc, llm_ok)
            return ReviewerResult(company_research_notes=f"Review skipped ({note})")

        return ReviewerResult(company_research_notes="Review skipped (LLM offline)")

    async def run(self, request: ApplyRequest) -> ApplyResponse:
        from app.services.pipeline_service import PipelineService

        return await PipelineService(self.settings).run_sync(request)
