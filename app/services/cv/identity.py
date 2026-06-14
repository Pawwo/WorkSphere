"""Profile identity and education parsing."""

from __future__ import annotations

import re
from typing import List

from app.services.cv.types import EducationEntry


def parse_identity(profile_md: str) -> dict:
    fields = {}
    for line in profile_md.splitlines():
        m = re.match(r"- \*\*([^:*]+):\*\* (.+)", line.strip())
        if m:
            fields[m.group(1).lower().replace(" ", "_")] = m.group(2).strip()
    name = fields.get("name", "Candidate")
    parts = name.split(maxsplit=1)
    linkedin = fields.get("linkedin", "")
    github = fields.get("github", "")
    extra_parts = []
    if linkedin and linkedin not in ("—", "-", ""):
        extra_parts.append(f"\\href{{{linkedin}}}{{LinkedIn}}")
    if github and github not in ("—", "-", ""):
        extra_parts.append(f"\\href{{{github}}}{{GitHub}}")
    return {
        "first": parts[0] if parts else "First",
        "last": parts[1] if len(parts) > 1 else "Last",
        "name": name,
        "email": fields.get("email", "email@example.com"),
        "phone": fields.get("phone", ""),
        "linkedin": linkedin,
        "location": fields.get("location", ""),
        "languages": fields.get("languages", ""),
        "extrainfo": ", ".join(extra_parts),
    }


def parse_education_from_profile(profile_md: str) -> List[EducationEntry]:
    rows: List[EducationEntry] = []
    for line in profile_md.splitlines():
        if not line.strip().startswith("|") or "---" in line or "Degree" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) >= 4:
            rows.append(
                EducationEntry(
                    degree=cols[0],
                    period=cols[1],
                    institution=cols[2],
                    detail=cols[3] if len(cols) > 3 else "",
                )
            )
    if rows:
        return rows
    return [
        EducationEntry(
            period="2003--2006",
            degree="Bachelor's in Computer Science and Econometrics",
            institution="Zachodniopomorska School of Business (University of Applied Sciences)",
            location="Szczecin, Poland",
            detail="Computer science, econometrics, quantitative methods.",
        )
    ]


def parse_certifications_from_profile(profile_md: str) -> List[str]:
    certs: List[str] = []
    in_certs = False
    for line in profile_md.replace("\\n", "\n").splitlines():
        stripped = line.strip()
        if stripped.startswith("## Certifications"):
            in_certs = True
            inline = stripped.split("## Certifications", 1)[-1].strip().lstrip("-").strip()
            if inline:
                certs.append(inline)
            continue
        if in_certs and stripped.startswith("## "):
            break
        if in_certs and stripped.startswith("- "):
            certs.append(stripped[2:].strip())
    return certs


def default_competencies_from_profile(profile_md: str) -> List[str]:
    comps: List[str] = []
    in_domain = False
    for line in profile_md.splitlines():
        if line.strip().startswith("### Domain Expertise"):
            in_domain = True
            continue
        if in_domain and line.strip().startswith("### "):
            break
        if in_domain and line.strip().startswith("- "):
            comps.append(line.strip()[2:].strip())
    if comps:
        return [
            "Operations & ERP leadership: Odoo ERP, delivery operations, KPI, P&L, process automation",
            "AI transformation: LLM, RAG, agentic AI, AI-first operating models, EU AI Act awareness",
            f"Domain expertise: {', '.join(comps[:4])}",
            "Tools: Odoo, Docker, Ollama, Jira, Confluence, CI/CD, analytics dashboards",
            "Methods: Agile/Scrum, change management, cross-functional leadership, business development",
        ]
    return [
        "Operations & ERP leadership: Odoo ERP, delivery operations, KPI, P&L, CI/CD",
        "AI transformation: LLM, RAG, agentic AI, AI-first operating models, governance",
        "Business development: B2B growth, client retention, pre-sales, solution architecture",
        "Methods: Agile/Scrum, change management, cross-functional leadership",
        "Tools: Odoo, Docker, Ollama, Jira, analytics dashboards",
    ]
