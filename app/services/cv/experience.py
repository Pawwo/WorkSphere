"""Experience parsing and merging."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from app.config import Settings, get_settings
from app.services.cv.master import resolve_master_cv_text
from app.services.cv.types import ExperienceEntry


def parse_experience_from_profile(profile_md: str) -> List[ExperienceEntry]:
    entries: List[ExperienceEntry] = []
    current: Optional[ExperienceEntry] = None
    in_experience = False

    for line in profile_md.splitlines():
        if line.strip().startswith("## Professional Experience"):
            in_experience = True
            continue
        if in_experience and line.startswith("## ") and "Professional Experience" not in line:
            break
        if not in_experience:
            continue

        hm = re.match(r"^### (.+?) - (.+?) \((.+?)\)\s*$", line.strip())
        if hm:
            if current:
                entries.append(current)
            title, company, period = hm.group(1).strip(), hm.group(2).strip(), hm.group(3).strip()
            period = period.replace("present", "Present").replace("obecnie", "Present")
            current = ExperienceEntry(period=period, title=title, company=company)
            continue

        if current and line.strip().startswith("- "):
            current.bullets.append(line.strip()[2:].strip())

        if current and not current.location and line.strip() and not line.startswith("-") and not line.startswith("#"):
            if re.search(r"Szczecin|Warszawa|remote|hybrid", line, re.I):
                current.location = line.strip()

    if current:
        entries.append(current)
    return entries


_PLACEHOLDER_BULLET_RE = re.compile(
    r"^\((?:uzupełnij|brak[^)]*)\)$|^\[PLACEHOLDER\]$",
    re.I,
)


def _is_placeholder_bullet(text: str) -> bool:
    t = (text or "").strip()
    return not t or bool(_PLACEHOLDER_BULLET_RE.match(t))


def _norm_exp_key(title: str, company: str) -> str:
    def norm(s: str) -> str:
        s = s.lower()
        s = re.sub(r"\([^)]*\)", "", s)
        s = re.sub(r"\bsp\.?\s*z\.?\s*o\.?\s*o\.?\b", "", s)
        return re.sub(r"[^\w]+", "", s)

    return f"{norm(title)}|{norm(company)}"


def _parse_master_job_header(line: str) -> Optional[tuple[str, str, str, str]]:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 3:
        return None
    period = parts[-1]
    if not re.search(r"\d{2}\.\d{4}", period):
        return None
    if len(parts) == 3:
        return parts[0], parts[1], "", period
    return parts[0], parts[1], parts[2], period


def parse_experience_from_master(
    settings: Optional[Settings] = None,
    *,
    master_text: Optional[str] = None,
) -> List[ExperienceEntry]:
    settings = settings or get_settings()
    text = (master_text if master_text is not None else resolve_master_cv_text(settings)).strip()
    if not text:
        return []
    m = re.search(
        r"DOŚWIADCZENIE ZAWODOWE\s*\n(.*?)(?:\nDOŚWIADCZENIE EKSPERCKIE|\Z)",
        text,
        re.S,
    )
    if not m:
        return []
    section = m.group(1)
    entries: List[ExperienceEntry] = []
    current: Optional[ExperienceEntry] = None
    mode: Optional[str] = None

    for line in section.splitlines():
        header = _parse_master_job_header(line.strip())
        if header:
            if current:
                entries.append(current)
            title, company, location, period = header
            period = (
                period.replace("obecnie", "Present")
                .replace("–", "-")
                .replace("—", "-")
                .strip()
            )
            current = ExperienceEntry(
                period=period,
                title=title,
                company=company,
                location=location,
                bullets=[],
            )
            mode = None
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("Zakres odpowiedzialności"):
            mode = "scope"
            continue
        if stripped.startswith("Udokumentowane efekty"):
            mode = "effects"
            continue
        if stripped.startswith("Słowa kluczowe") or stripped.startswith("Forma współpracy"):
            mode = None
            continue
        if mode in ("scope", "effects") and line.startswith("    ") and stripped:
            current.bullets.append(stripped)

    if current:
        entries.append(current)
    return entries


def parse_experience_from_wizard(settings: Optional[Settings] = None) -> List[ExperienceEntry]:
    settings = settings or get_settings()
    from app.services.profile_service import ProfileService

    state = ProfileService(settings).load_wizard_state()
    if not state.section3 or not state.section3.experience:
        return []
    entries: List[ExperienceEntry] = []
    for e in state.section3.experience:
        period = f"{e.start} - {e.end}".replace("present", "Present").replace("obecnie", "Present")
        bullets = [b for b in (e.bullets or []) if not _is_placeholder_bullet(b)]
        entries.append(
            ExperienceEntry(
                period=period,
                title=e.title,
                company=e.company,
                location=e.location or "",
                bullets=bullets,
            )
        )
    return entries


def _experience_lookup(entries: List[ExperienceEntry]) -> dict[str, ExperienceEntry]:
    lookup: dict[str, ExperienceEntry] = {}
    for e in entries:
        if e.bullets and not all(_is_placeholder_bullet(b) for b in e.bullets):
            lookup[_norm_exp_key(e.title, e.company)] = e
    return lookup


def merge_experience_bullets(
    primary: List[ExperienceEntry],
    *fallbacks: List[ExperienceEntry],
) -> List[ExperienceEntry]:
    """Keep job structure from primary; fill bullets from wizard / master when placeholders."""
    lookups = [_experience_lookup(src) for src in fallbacks]
    if not primary:
        for src in fallbacks:
            if src:
                return src
        return []

    merged: List[ExperienceEntry] = []
    for pe in primary:
        bullets = [b for b in pe.bullets if not _is_placeholder_bullet(b)]
        location = pe.location
        if not bullets:
            key = _norm_exp_key(pe.title, pe.company)
            for lookup in lookups:
                fb = lookup.get(key)
                if fb and fb.bullets:
                    bullets = list(fb.bullets)
                    location = location or fb.location
                    break
        merged.append(
            ExperienceEntry(
                period=pe.period,
                title=pe.title,
                company=pe.company,
                location=location,
                bullets=bullets,
            )
        )
    return merged


def _period_end_key(period: str) -> tuple[int, int]:
    """Sort key for reverse-chronological order (higher = more recent)."""
    p = (period or "").replace("obecnie", "Present").replace("–", "-").replace("—", "-")
    if re.search(r"present", p, re.I):
        return (9999, 12)
    end_part = p.split("-")[-1].strip() if "-" in p else p.strip()
    m = re.search(r"(\d{2})\.(\d{4})", end_part)
    if m:
        return (int(m.group(2)), int(m.group(1)))
    m = re.search(r"\b(20\d{2})\b", end_part)
    if m:
        return (int(m.group(1)), 12)
    return (0, 0)


def select_experience_for_pdf(
    entries: List[ExperienceEntry],
    emphasis_jobs: Optional[List[str]] = None,
    max_entries: int = 6,
) -> List[ExperienceEntry]:
    """Pick 5–6 roles for a 2-page PDF: emphasis_jobs first, then reverse-chronological."""
    emphasis_jobs = emphasis_jobs or []
    sorted_entries = sorted(entries, key=lambda e: _period_end_key(e.period), reverse=True)

    def title_matches(entry: ExperienceEntry) -> bool:
        title_low = entry.title.lower()
        title_norm = re.sub(r"[^\w]+", "", title_low)
        for job in emphasis_jobs:
            jl = job.lower()
            if jl in title_low or title_low in jl:
                return True
            en = re.sub(r"[^\w]+", "", jl)
            if en and (en in title_norm or title_norm in en):
                return True
            if "chief operating officer" in jl and title_norm == "coo":
                return True
            job_words = set(re.findall(r"\w{3,}", jl))
            title_words = set(re.findall(r"\w{3,}", title_low))
            if len(job_words & title_words) >= 2:
                return True
        return False

    picked: List[ExperienceEntry] = []
    seen: set[str] = set()

    for entry in sorted_entries:
        if title_matches(entry):
            key = _norm_exp_key(entry.title, entry.company)
            if key not in seen and entry.bullets:
                picked.append(entry)
                seen.add(key)

    for entry in sorted_entries:
        if len(picked) >= max_entries:
            break
        key = _norm_exp_key(entry.title, entry.company)
        if key not in seen and entry.bullets:
            picked.append(entry)
            seen.add(key)

    picked.sort(key=lambda e: _period_end_key(e.period), reverse=True)
    return picked[:max_entries]


def _entries_have_real_bullets(entries: List[ExperienceEntry]) -> bool:
    return any(
        e.bullets and not all(_is_placeholder_bullet(b) for b in e.bullets) for e in entries
    )


def resolve_experience_entries(
    profile_md: str,
    settings: Optional[Settings] = None,
) -> List[ExperienceEntry]:
    profile_exp = parse_experience_from_profile(profile_md)
    wizard_exp = parse_experience_from_wizard(settings)
    master_exp = parse_experience_from_master(settings)

    if profile_exp and not _entries_have_real_bullets(profile_exp) and master_exp:
        base = master_exp
    elif profile_exp:
        base = profile_exp
    else:
        base = wizard_exp or master_exp

    return merge_experience_bullets(base, master_exp, wizard_exp)
