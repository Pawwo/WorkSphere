"""URL helpers for job portal detection."""

from __future__ import annotations

import re


def norm_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().rstrip("/").lower()
    u = re.sub(r"\?.*", "", u)
    u = re.sub(r"#.*", "", u)
    u = u.replace("www.", "")
    m = re.search(r"jobs/view/[^/]+-at-[^/]+-(\d+)", u)
    if m:
        return f"linkedin:{m.group(1)}"
    m = re.search(r"oferta,(\d+)", u)
    if m:
        return f"pracuj:{m.group(1)}"
    m = re.search(r"_(\d+)\.html", u)
    if m:
        return f"praca-pl:{m.group(1)}"
    m = re.search(r"job-offer/([^/]+)", u)
    if m:
        return f"justjoin:{m.group(1)}"
    m = re.search(r"/oferta-pracy/([^/]+)", u)
    if m:
        return f"rocketjobs:{m.group(1)}"
    m = re.search(r"indeed\.com/rc/clk\?jk=([^&]+)", u)
    if m:
        return f"indeed:{m.group(1)}"
    return u


def portal_from_url(url: str) -> str:
    u = norm_url(url)
    raw = url.lower()
    if u.startswith("justjoin:") or "justjoin" in raw:
        return "justjoin"
    if "nofluffjobs" in raw:
        return "nofluffjobs"
    if u.startswith("rocketjobs:") or "rocketjobs" in raw:
        return "rocketjobs"
    if "theprotocol" in raw:
        return "theprotocol"
    if u.startswith("pracuj:") or "pracuj.pl" in raw:
        return "pracuj"
    if u.startswith("praca-pl:") or "praca.pl" in raw:
        return "praca-pl"
    if u.startswith("linkedin:") or "linkedin" in raw:
        return "linkedin-pl"
    return "other"
