"""Profile markdown generators."""

from __future__ import annotations

from pathlib import Path
from typing import List

from app.config import Settings


def gen_01(settings: Settings, s1, s2, s3, s4, s5, s8) -> str:
    from app.services.cv_builder import _norm_exp_key, parse_experience_from_master
    from app.services.profile.language_skills import format_languages_line

    languages_display = (
        format_languages_line(s1.language_skills)
        if getattr(s1, "language_skills", None)
        else (s1.languages or "—")
    )

    master_lookup = {
        _norm_exp_key(e.title, e.company): e.bullets
        for e in parse_experience_from_master(settings)
        if e.bullets
    }

    edu_rows = "\n".join(
        f"| {e.degree} | {e.years} | {e.institution} | {e.topics or e.field or ''} |"
        for e in s2.education
    ) or "| — | — | — | — |"

    exp_blocks = []
    for e in s3.experience:
        bullets = [b for b in (e.bullets or []) if b.strip() and b.strip() != "(uzupełnij)"]
        if not bullets:
            bullets = master_lookup.get(_norm_exp_key(e.title, e.company), [])
        bullet_lines = "\n".join(f"- {b}" for b in bullets) or "- (uzupełnij)"
        loc = f"\n{e.location}" if e.location else ""
        exp_blocks.append(
            f"### {e.title} - {e.company} ({e.start} - {e.end}){loc}\n{bullet_lines}"
        )
    experience = "\n\n".join(exp_blocks) or "### (brak doświadczenia — uzupełnij)"

    projects = "\n".join(f"- {p}" for p in s3.projects) or "- (brak projektów)"
    pubs = "\n".join(f"1. {p}" for p in s5.publications) or "<!-- brak -->"
    awards = "\n".join(f"- {a}" for a in s5.awards) or "<!-- brak -->"
    refs = "\n".join(
        f"- {r.name}, {r.title or ''}, {r.company or ''} ({r.email or ''})"
        for r in s8.references
    ) or "Więcej referencji na żądanie."

    certs = "\n".join(f"- {c}" for c in s2.certifications)

    return f"""# Candidate Profile

## Identity
- **Name:** {s1.full_name}
- **Location:** {s1.location}
- **Phone:** {s1.phone or '—'}
- **Email:** {s1.email}
- **LinkedIn:** {s1.linkedin or '—'}
- **GitHub:** {s1.github or '—'}
- **Languages:** {languages_display}
- **Status:** {s1.employment_status}
- **Constraints:** {s1.constraints or '—'}

## Education

| Degree | Period | Institution | Key Topics |
|--------|--------|-------------|------------|
{edu_rows}

{f'## Certifications\\n{certs}' if certs else ''}

## Professional Experience

{experience}

## Independent Projects
{projects}

## Technical Skills

### Programming & ML
- **Programming:** {s4.programming_skills or '—'}
- **ML/AI:** {s4.ml_skills or '—'}

### Domain Expertise
- {s4.domain_expertise or '—'}

### Software & Tools
- {s4.tools or '—'}
{f'- {s4.other_skills}' if s4.other_skills else ''}

## Publications
{pubs}

## Awards
{awards}

## References
{refs}
"""

def gen_02(s1, s6) -> str:
    strengths = []
    if s6.thrive_in:
        strengths.append(f"- **Dobrze pracuje w:** {s6.thrive_in}")
    if s6.team_style:
        strengths.append(f"- **Styl zespołowy:** {s6.team_style}")
    if s6.communication_style:
        strengths.append(f"- **Komunikacja:** {s6.communication_style}")
    strengths_text = "\n".join(strengths) or "- (uzupełnij po setup)"

    work_best = []
    if s6.thrive_in:
        work_best.append(f"- {s6.thrive_in}")
    if s6.decision_style:
        work_best.append(f"- {s6.decision_style}")

    growth = []
    if s6.drains_energy:
        growth.append(f"- **Obszar uwagi:** {s6.drains_energy} — warto omówić oczekiwania zespołu")

    return f"""# Behavioral Profile

## Overview
{s1.full_name} — profil behawioralny na podstawie setup wizard.
{s6.notes or ''}

## Strongest Behaviors
{strengths_text}

## How You Work Best
{chr(10).join(work_best) or '- (uzupełnij)'}

## Growth Areas (frame positively in applications)
{chr(10).join(growth) or '- (uzupełnij)'}

## Mapping to Job Posting Language

When a job posting mentions collaboration, ownership, or analytical work — likely **strong fit**.
When a job posting emphasizes high-pressure sales or micromanagement — flag as **potential friction**.
"""

def gen_04(profile_dir: Path, s4, s7) -> str:
    path = profile_dir / "04-job-evaluation.md"
    base = path.read_text(encoding="utf-8") if path.exists() else ""
    primary = s4.programming_skills or "Python"
    secondary = ", ".join(filter(None, [s4.ml_skills, s4.domain_expertise, s4.tools]))
    goals = ", ".join(s7.target_roles) if s7.target_roles else "role techniczne"
    must = s7.must_haves or "—"
    deal = s7.deal_breakers or "—"

    replacements = {
        "[YOUR_PRIMARY_SKILLS]": primary,
        "[YOUR_SECONDARY_SKILLS]": secondary or primary,
        "[SKILLS_YOU_LACK]": "(do uzupełnienia w trakcie nauki)",
        "[YOUR_DIRECT_EXPERIENCE_DOMAINS]": s4.domain_expertise or primary,
        "[YOUR_ADJACENT_EXPERIENCE]": secondary or "—",
        "[ROLES_WITH_LIMITED_EXPERIENCE]": "—",
    }
    for old, new in replacements.items():
        base = base.replace(old, new)

    if "## Career Goals" not in base:
        base += f"""

## Career Goals (from setup)
- **Target roles:** {goals}
- **Must-haves:** {must}
- **Deal-breakers:** {deal}
- **Location:** {s7.location_constraints or '—'}
"""
    return base

def gen_05(s1, s4, s7) -> str:
    roles = s7.target_roles or ["Software Developer"]
    statements = []
    for role in roles[:3]:
        statements.append(
            f"### Profile statement — {role}\n"
            f"Experienced professional with strengths in {s4.programming_skills or 'software development'}. "
            f"Seeking {role} opportunities."
        )
    return f"""# CV Templates

## Base candidate
- **Name:** {s1.full_name}
- **Location:** {s1.location}

## Role-specific profile statements

{chr(10).join(statements)}
"""

def gen_07(s3) -> str:
    stubs = []
    for e in s3.experience[:4]:
        achievement = e.bullets[0] if e.bullets else f"Key work at {e.company}"
        stubs.append(
            f"""### {e.title} @ {e.company}
**Source:** CV / setup wizard
**What happened:** {achievement}
**Why it matters:** Leadership, problem-solving, technical depth
**S/T/A/R stub:**
- Situation:
- Task:
- Action:
- Result:
"""
        )
    stubs_text = "\n".join(stubs) or "<!-- Dodaj STAR po setup -->"
    return f"""# Interview Preparation

## STAR Candidates (Complete Manually)

{stubs_text}
"""

def gen_claude(profile_dir: Path, s1, s2, s3, s4, s5, s6, s7) -> str:
    from app.services.profile.language_skills import format_languages_line

    path = profile_dir / "CLAUDE.md"
    base = path.read_text(encoding="utf-8") if path.exists() else ""
    name = s1.full_name
    languages_text = (
        format_languages_line(s1.language_skills)
        if getattr(s1, "language_skills", None)
        else (s1.languages or "—")
    )
    replacements = {
        "[YOUR_NAME]": name,
        "[YOUR_CITY]": s1.location.split(",")[0].strip() if s1.location else "—",
        "[YOUR_COUNTRY]": "Polska",
        "[YOUR_COMMUTE_CONSTRAINTS]": s1.constraints or "—",
        "[YOUR_LANGUAGES]": languages_text,
        "[YOUR_EMPLOYMENT_STATUS]": s1.employment_status,
        "[YOUR_LINKEDIN_HEADLINE]": f"{s3.experience[0].title if s3.experience else 'Professional'}",
        "[YOUR_PRIMARY_SKILLS]": s4.programming_skills or "—",
        "[YOUR_SECONDARY_SKILLS]": s4.ml_skills or "—",
        "[YOUR_DOMAIN_EXPERTISE]": s4.domain_expertise or "—",
        "[YOUR_TOOLS_AND_SOFTWARE]": s4.tools or "—",
        "[PLACEHOLDER]": name,
    }
    for old, new in replacements.items():
        base = base.replace(old, new)

    if s3.experience and "[JOB_TITLE]" in base:
        e = s3.experience[0]
        base = base.replace("[JOB_TITLE]", e.title)
        base = base.replace("[COMPANY]", e.company)
        base = base.replace("[START_DATE]", e.start)
        base = base.replace("[END_DATE]", e.end)
        base = base.replace("[LOCATION]", e.location or "")

    return base

def gen_search_queries(s4, s7, s9) -> str:
    city = s9.city or "Warszawa"
    roles = [r.strip() for r in (s9.role_titles or s7.target_roles or []) if r and r.strip()]
    skills = [s.strip() for s in (s9.key_skills or []) if s and s.strip()]
    if not skills and s4.programming_skills:
        skills = [p.strip() for p in s4.programming_skills.split(",") if p.strip()]

    ideal = ", ".join(s9.ideal_locations) if s9.ideal_locations else city
    acceptable = ", ".join(s9.acceptable_locations) if s9.acceptable_locations else f"{city}, remote"
    borderline = ", ".join(s9.borderline_locations) if s9.borderline_locations else "hybrid poza regionem"
    too_far = ", ".join(s9.too_far_locations) if s9.too_far_locations else "on-site poza Polską"

    p1_lines = [f'"{role}" {city}' for role in roles]
    if roles:
        p1_lines.append(f'"{roles[0]}" remote')

    p2_lines: List[str] = []
    for skill in skills:
        p2_lines.append(f'"{skill}" {city}')
        p2_lines.append(f'"{skill}" {city} hybrid')
    if s4.domain_expertise:
        p2_lines.append(f"{s4.domain_expertise} polska")

    adjacent = [a.strip() for a in (s9.adjacent_roles or []) if a and a.strip()]
    p3_lines = [f'"{a}" {city}' for a in adjacent]

    p4_lines: List[str] = []
    if skills:
        p4_lines.append(f"{skills[0]} developer {city}")
    p4_lines.append('"software engineer" remote polska')

    def block(lines: List[str]) -> str:
        return "\n".join(lines) if lines else "(brak — uzupełnij sekcję 9 w /setup)"

    return f"""# Search Queries for Job Scraper

## Search Portals (CLI)

**Primary** (fast, IT-focused — use on every scrape):
- pracuj, justjoin, nofluffjobs, theprotocol, praca_pl, rocketjobs

**Broad** (slower — use with broad=true):
- indeed, linkedin

## Query Categories

### Priority 1: Target roles

```
{block(p1_lines)}
```

### Priority 2: Keywords and domain

```
{block(p2_lines)}
```

### Priority 3: Adjacent roles

```
{block(p3_lines)}
```

### Priority 4: Broader technical

```
{block(p4_lines)}
```

## Location Filter

- **Ideal:** {ideal}
- **Acceptable:** {acceptable}
- **Borderline:** {borderline}
- **Too far:** {too_far}

## Default portals for API

{", ".join(s9.portals)}
"""