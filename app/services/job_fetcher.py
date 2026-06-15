from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import httpx

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.llm.token_budgets import JOB_PARSE
from app.llm.structured import extract_json
from app.models.apply import JobParsed
from app.prompts.loader import render_prompt
from app.storage.files import is_http_url, load_seen_jobs
from app.storage.job_repository import JobRepository

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"^https?://", re.I)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _is_indeed_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "indeed." in host


async def _fetch_indeed_via_skill(url: str, *, settings: Settings) -> str:
    """
    Indeed aggressively blocks plain HTTP fetches (403 / security check).
    Prefer the existing Playwright-based skill when available.
    """
    cli: Path = settings.skills_path / "indeed-pl-search" / "cli" / "src" / "cli.ts"
    if not cli.exists():
        raise ValueError(
            "Indeed blokuje pobieranie (403). Skill indeed-pl-search nie jest zainstalowany na serwerze."
        )
    cmd = [
        settings.bun_path,
        "run",
        str(cli),
        "detail",
        url,
        "--format",
        "json",
    ]
    env = os.environ.copy()
    browser_path = env.get("INDEED_BROWSER_PATH", "").strip()
    if browser_path:
        env["INDEED_BROWSER_PATH"] = browser_path
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(settings.skills_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    timeout = int(settings.scrapers_portal_timeouts.get("indeed-pl", 240))
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise ValueError(
            f"Indeed: timeout po {timeout}s. Spróbuj ponownie lub wklej treść oferty ręcznie w /apply."
        ) from None
    if proc.returncode != 0:
        err = (stderr or b"").decode(errors="replace").strip()
        # Keep the message actionable for /applications/{id}.
        raise ValueError(
            "Indeed blokuje automatyczne pobieranie (403 / captcha). "
            "Otwórz ofertę w przeglądarce i wklej treść do /apply (pole text), "
            f"albo wyłącz indeed-pl w portalach. Szczegóły: {err or 'detail failed'}"
        )
    text = (stdout or b"").decode(errors="replace").strip()
    try:
        data = json.loads(text)
        # scraper-shared usually returns a JobCard-like object
        desc = (data.get("description") or "").strip() if isinstance(data, dict) else ""
        if desc:
            return desc
    except Exception:
        pass
    # Fallback: treat output as plain text
    return text

def decode_html_entities(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    out = text.strip()
    prev = None
    while prev != out:
        prev = out
        out = html.unescape(out)
    return out


def _looks_like_sentence_role(role: Optional[str]) -> bool:
    if not role:
        return True
    low = role.lower()
    if len(role) > 100:
        return True
    markers = (
        " zatrudnia ",
        " zatrudnia na ",
        " hiring ",
        " is hiring",
        " rekrutuje ",
        " poszukuje ",
        " szuka ",
    )
    return any(m in f" {low} " for m in markers)


def _role_from_linkedin_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/jobs/view/([^/?#]+)", url, re.I)
    if not m:
        return None
    slug = m.group(1)
    slug = re.sub(r"-\d{8,}$", "", slug)
    role_part = slug.split("-at-")[0] if "-at-" in slug else slug
    role = role_part.replace("-", " ").strip()
    if len(role) < 4:
        return None
    return decode_html_entities(role)


def _strip_html(html_text: str) -> str:
    html_text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
    html_text = re.sub(r"(?is)<style.*?>.*?</style>", " ", html_text)
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_LINKEDIN_JD_START_MARKERS = (
    " IS HIRING",
    " IS HIRING!",
    "Requirements:",
    "Essential Qualifications",
    "Responsibilities:",
    "About the job",
    "Job description",
    "What you'll do",
    "What you will do",
    "Wymagania",
    "Obowiązki",
    "O projekcie",
    "Opis stanowiska",
)

_LINKEDIN_JD_END_MARKERS = (
    "Podobne oferty pracy",
    "Similar jobs",
    "People also viewed",
    "Poziom w hierarchii",
    "Polecenia",
    "Referrals",
    "Set alert",
    "Utwórz alert",
)


def extract_linkedin_job_body(text: str) -> str:
    """Strip LinkedIn chrome (cookies, nav, similar jobs) keeping the job description."""
    if not text or len(text) < 400:
        return text
    low = text.lower()
    if "linkedin" not in low[:300] and "prywatność" not in low[:600] and "cookie" not in low[:600]:
        return text

    start = 0
    for marker in _LINKEDIN_JD_START_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            start = idx
            break
    if start == 0:
        for show in ("Show more Show less", "Show more", "Pokaż więcej"):
            idx = text.find(show)
            if idx >= 0:
                start = idx + len(show)
                break

    body = text[start:].strip() if start else text
    for end_marker in _LINKEDIN_JD_END_MARKERS:
        idx = body.find(end_marker)
        if idx > 250:
            body = body[:idx].strip()
            break

    if len(body) >= 200:
        return body
    return text


_LINKEDIN_CHROME_MARKERS = (
    "poziom w hierarchii",
    "nie pamiętam hasła",
    "zaloguj się",
    "sign in",
    "join now",
    "email or phone",
    "warunki linkedin",
    "user agreement",
    "ustaw alert",
    "set alert",
    "polecenia",
    "referrals",
    "cookie",
    "prywatność",
)

_JD_MARKERS = (
    "requirements",
    "responsibilities",
    "about the job",
    "what you'll",
    "what you will",
    "qualifications",
    "wymagania",
    "obowiązki",
    "opis stanowiska",
    "o projekcie",
    "essential qualifications",
)


def _linkedin_body_usable(text: str) -> bool:
    """True when stripped HTML text looks like a job description, not login chrome."""
    if not text or len(text) < 200:
        return False
    low = text.lower()
    if sum(1 for m in _JD_MARKERS if m in low) >= 1:
        return True
    role_terms = (
        "experience",
        "automation",
        "engineer",
        "consultant",
        "responsibilit",
        "qualification",
        "hands-on",
    )
    if any(t in low for t in role_terms):
        chrome_hits = sum(1 for m in _LINKEDIN_CHROME_MARKERS if m in low)
        return chrome_hits < 3
    return False


def _extract_json_ld_description(html_text: str) -> Optional[str]:
    """JobPosting description from JSON-LD (when visible without login)."""
    for block in re.findall(
        r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text
    ):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            types = item.get("@type", "")
            if isinstance(types, list):
                is_job = any("JobPosting" in str(t) for t in types)
            else:
                is_job = "JobPosting" in str(types)
            if not is_job:
                continue
            desc = item.get("description")
            if not desc:
                continue
            text = _strip_html(str(desc)) if "<" in str(desc) else str(desc)
            text = decode_html_entities(text.strip()) or ""
            if len(text) >= 80:
                return text
    return None


def _lookup_seen_description(url: str, settings: Optional[Settings] = None) -> Optional[str]:
    """Rich posting text from inbox/seen_jobs when live fetch hits a login wall."""
    from app.services.scrape.posting_extract.extract import extract_key_description

    settings = settings or get_settings()
    found = JobRepository(settings.seen_jobs_path).get_by_url(url)
    if not found:
        return None
    _key, entry = found
    desc = (entry.description or "").strip()
    if len(desc) < 40:
        return None
    extracted = extract_key_description(desc, portal=entry.portal or "", url=url)
    return extracted if len(extracted) >= 80 else desc


def _enrich_linkedin_raw_text(
    raw: str,
    *,
    html_text: str,
    url: str,
    settings: Settings,
) -> str:
    """Replace login-wall chrome with JSON-LD or inbox description when possible."""
    if _linkedin_body_usable(raw):
        return raw
    json_ld = _extract_json_ld_description(html_text)
    if json_ld and len(json_ld) >= 80:
        logger.info("LinkedIn fetch: using json-ld description for %s", url[:80])
        return json_ld
    seen = _lookup_seen_description(url, settings)
    if seen and len(seen) >= 80:
        logger.info("LinkedIn fetch: using seen_jobs description for %s", url[:80])
        return seen
    return raw


def _role_implies_english(role: str) -> bool:
    if not role or role in ("Position",):
        return False
    if re.search(r"[ąćęłńóśźż]", role, re.I):
        return False
    words = re.findall(r"[a-z]{3,}", role.lower())
    stop = {"and", "the", "for", "with", "mfd", "mfx", "nb", "remote"}
    content = [w for w in words if w not in stop]
    return len(content) >= 2


def _resolve_job_language(role: str, raw_text: str) -> str:
    if _role_implies_english(role):
        return "en"
    return _detect_language(raw_text)


def _meta_content(html_text: str, prop: str) -> Optional[str]:
    for pat in (
        rf'<meta\s+property="{prop}"\s+content="([^"]+)"',
        rf'<meta\s+content="([^"]+)"\s+property="{prop}"',
        rf'<meta\s+name="{prop}"\s+content="([^"]+)"',
        rf'<meta\s+content="([^"]+)"\s+name="{prop}"',
    ):
        m = re.search(pat, html_text, re.I)
        if m:
            return decode_html_entities(unquote(m.group(1).strip()))
    return None


def _extract_json_ld(html_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    for block in re.findall(
        r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text
    ):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            types = item.get("@type", "")
            if isinstance(types, list):
                is_job = any("JobPosting" in str(t) for t in types)
            else:
                is_job = "JobPosting" in str(types)
            if not is_job:
                continue
            org = item.get("hiringOrganization") or {}
            if isinstance(org, dict):
                company = org.get("name")
            else:
                company = str(org) if org else None
            role = item.get("title") or item.get("name")
            loc = item.get("jobLocation")
            location = None
            if isinstance(loc, dict):
                addr = loc.get("address") or {}
                if isinstance(addr, dict):
                    location = addr.get("addressLocality") or addr.get("addressRegion")
            elif isinstance(loc, list) and loc:
                first = loc[0]
                if isinstance(first, dict):
                    addr = first.get("address") or {}
                    if isinstance(addr, dict):
                        location = addr.get("addressLocality")
            return (
                decode_html_entities(company),
                decode_html_entities(role),
                decode_html_entities(location),
            )
    return None, None, None


def _parse_linkedin(html_text: str, url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    og_title = _meta_content(html_text, "og:title") or _meta_content(html_text, "twitter:title")
    if not og_title:
        return None, None, None
    title = og_title.replace(" | LinkedIn", "").replace(" | LinkedIn Poland", "").strip()

    m = re.match(r"(?i)^(.+?)\s+at\s+(.+)$", title)
    if m:
        return (
            decode_html_entities(m.group(2).strip()),
            decode_html_entities(m.group(1).strip()),
            None,
        )

    m = re.match(r"(?i)^(.+?)\s+hiring\s+(.+)$", title)
    if m:
        return (
            decode_html_entities(m.group(1).strip()),
            decode_html_entities(m.group(2).strip()),
            None,
        )

    m = re.match(
        r"(?i)^(.+?)\s+zatrudnia\s+na\s+stanowisko\s+(.+?)\s+w\s+(.+)$",
        title,
    )
    if m:
        return (
            decode_html_entities(m.group(1).strip()),
            decode_html_entities(m.group(2).strip()),
            decode_html_entities(m.group(3).strip()),
        )

    m = re.match(r"(?i)^(.+?)\s+zatrudnia\s+na\s+stanowisko\s+(.+)$", title)
    if m:
        return (
            decode_html_entities(m.group(1).strip()),
            decode_html_entities(m.group(2).strip()),
            None,
        )

    m = re.match(r"(?i)^(.+?)\s+rekrutuje\s+na\s+stanowisko\s+(.+?)\s+w\s+(.+)$", title)
    if m:
        return (
            decode_html_entities(m.group(1).strip()),
            decode_html_entities(m.group(2).strip()),
            decode_html_entities(m.group(3).strip()),
        )

    return None, None, None


def _lookup_seen_job(
    url: str, settings: Optional[Settings] = None
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    settings = settings or get_settings()
    seen = load_seen_jobs(settings.seen_jobs_path)
    for key, job in seen.items():
        if job.url == url or key == url:
            return (
                decode_html_entities(job.company),
                decode_html_entities(job.title),
                decode_html_entities(job.location),
            )
    return None, None, None


def _pick_role(
    *,
    seen: Optional[str],
    linkedin: Optional[str],
    json_ld: Optional[str],
    guessed: Optional[str],
    url: Optional[str],
) -> str:
    url_role = _role_from_linkedin_url(url)
    for candidate in (seen, linkedin, json_ld, url_role, guessed):
        if candidate and candidate not in ("Position",) and not _looks_like_sentence_role(candidate):
            return candidate
    return seen or linkedin or json_ld or url_role or guessed or "Position"


def _pick_company(*candidates: Optional[str]) -> str:
    for c in candidates:
        if c and c not in ("Unknown",):
            return c
    return "Unknown"


def _merge_job_fields(
    *,
    seen: tuple[Optional[str], Optional[str], Optional[str]] = (None, None, None),
    json_ld: tuple[Optional[str], Optional[str], Optional[str]] = (None, None, None),
    linkedin: tuple[Optional[str], Optional[str], Optional[str]] = (None, None, None),
    guessed: tuple[str, str, Optional[str]] = ("Unknown", "Position", None),
    url: Optional[str] = None,
) -> tuple[str, str, Optional[str]]:
    s_company, s_role, s_loc = seen
    j_company, j_role, j_loc = json_ld
    l_company, l_role, l_loc = linkedin
    g_company, g_role, g_loc = guessed

    company = _pick_company(l_company, s_company, j_company, g_company)
    role = _pick_role(
        seen=s_role,
        linkedin=l_role,
        json_ld=j_role,
        guessed=g_role if g_role != "Position" else None,
        url=url,
    )
    location = s_loc or l_loc or j_loc or g_loc
    return company, role, location


def _guess_company_role(text: str, url: Optional[str] = None) -> tuple[str, str, Optional[str]]:
    company = "Unknown"
    role = "Position"
    location = None

    patterns = [
        (r"(?i)firma[:\s]+([^\n,]{2,80})", None),
        (r"(?i)company[:\s]+([^\n,]{2,80})", None),
        (r"(?i)stanowisko[:\s]+([^\n]{2,100})", "role"),
        (r"(?i)position[:\s]+([^\n]{2,100})", "role"),
        (r"(?i)lokalizacja[:\s]+([^\n,]{2,60})", "loc"),
        (r"(?i)location[:\s]+([^\n,]{2,60})", "loc"),
        (r"(?i)zatrudniający[:\s]+([^\n,]{2,80})", None),
    ]
    for pat, kind in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        val = decode_html_entities(m.group(1).strip())
        if kind == "role":
            role = val or role
        elif kind == "loc":
            location = val or location
        else:
            company = val or company

    if url:
        host = urlparse(url).netloc.lower()
        if "linkedin" not in host and company == "Unknown":
            for portal, name in (
                ("justjoin", "JustJoin"),
                ("nofluffjobs", "NoFluffJobs"),
                ("pracuj", "Pracuj"),
                ("theprotocol", "TheProtocol"),
                ("rocketjobs", "RocketJobs"),
            ):
                if portal in host:
                    company = name
                    break

    first_line = decode_html_entities(text.split("\n", 1)[0].strip()[:120])
    if role == "Position" and first_line and 5 < len(first_line) < 100:
        if not _looks_like_sentence_role(first_line):
            role = first_line

    return company, role, location


async def _llm_parse_job(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        llm = BielikClient()
        if not (await llm.healthcheck()).get("ok"):
            return None, None, None
        prompt = render_prompt("job_parse.jinja2", text=text[:2000])
        raw = await llm.chat_complete(
            [{"role": "system", "content": "JSON only"}, {"role": "user", "content": prompt}],
            max_tokens=JOB_PARSE,
            temperature=0.0,
        )
        parsed = extract_json(raw)
        if isinstance(parsed, dict):
            return (
                decode_html_entities(parsed.get("company")),
                decode_html_entities(parsed.get("role")),
                decode_html_entities(parsed.get("location")),
            )
    except Exception as exc:
        logger.warning("LLM job parse failed: %s", exc)
    return None, None, None


def _detect_language(text: str) -> str:
    pl_markers = ["wymagania", "obowiązk", "stanowisko", "doświadczenie", "mile widziane", "oferujemy"]
    en_markers = ["requirements", "responsibilities", "experience", "about the role", "we offer"]
    pl_score = sum(1 for w in pl_markers if w in text.lower())
    en_score = sum(1 for w in en_markers if w in text.lower())
    return "pl" if pl_score >= en_score else "en"


def _manual_seen_posting(settings: Settings, ref: str) -> tuple[str, str, tuple[Optional[str], Optional[str], Optional[str]]]:
    found = JobRepository(settings.seen_jobs_path).get_by_url(ref)
    if not found:
        raise ValueError("Nie znaleziono oferty w skrzynce (brak URL)")
    _key, entry = found
    raw = (entry.description or "").strip()
    if len(raw) < 30:
        loc = f" ({entry.location})" if entry.location else ""
        raw = f"{entry.title} at {entry.company}{loc}. Imported manually without posting URL."
    seen = (
        decode_html_entities(entry.company),
        decode_html_entities(entry.title),
        decode_html_entities(entry.location),
    )
    return raw, "text", seen


async def fetch_job_posting(*, url: Optional[str] = None, text: Optional[str] = None) -> JobParsed:
    settings = get_settings()
    html_text = ""
    seen_override: tuple[Optional[str], Optional[str], Optional[str]] | None = None
    if url and is_http_url(url):
        url = url.strip()
        if _is_indeed_url(url):
            raw = await _fetch_indeed_via_skill(url, settings=settings)
            source = "url"
            html_text = ""
        else:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                try:
                    response = await client.get(url, headers={"User-Agent": _BROWSER_UA})
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code if exc.response else None
                    if code == 403 and _is_indeed_url(url):
                        raw = await _fetch_indeed_via_skill(url, settings=settings)
                        source = "url"
                        html_text = ""
                    else:
                        raise
                else:
                    html_text = response.text
                    content_type = response.headers.get("content-type", "")
                    if "html" in content_type:
                        raw = _strip_html(html_text)
                        if "linkedin" in url.lower():
                            raw = extract_linkedin_job_body(raw)
                            raw = _enrich_linkedin_raw_text(
                                raw, html_text=html_text, url=url, settings=settings
                            )
                    else:
                        raw = response.text
                    source = "url"
    elif text and text.strip():
        raw = text.strip()
        url = None
        source = "text"
    elif url and url.strip():
        raw, source, seen_override = _manual_seen_posting(settings, url.strip())
        url = url.strip()
        html_text = ""
    else:
        raise ValueError("Podaj url lub text ogłoszenia")

    if len(raw) < 30:
        raise ValueError("Treść ogłoszenia za krótka")

    seen = seen_override if seen_override is not None else (None, None, None)
    if seen_override is None and url:
        seen = _lookup_seen_job(url, settings)

    json_ld = (None, None, None)
    if html_text:
        json_ld = _extract_json_ld(html_text)

    linkedin = (None, None, None)
    if html_text and url and "linkedin" in url.lower():
        linkedin = _parse_linkedin(html_text, url)

    guessed = _guess_company_role(raw, url)

    company, role, location = _merge_job_fields(
        seen=seen,
        json_ld=json_ld,
        linkedin=linkedin,
        guessed=guessed,
        url=url,
    )

    if company == "Unknown" or role == "Position":
        lc, lr, ll = await _llm_parse_job(raw)
        company, role, location = _merge_job_fields(
            seen=(company if company != "Unknown" else None, role if role != "Position" else None, location),
            json_ld=(lc, lr, ll),
            linkedin=(None, None, None),
            guessed=(company, role, location),
            url=url,
        )

    company = company or "Unknown"
    role = role or "Position"
    role = decode_html_entities(role) or role
    company = decode_html_entities(company) or company

    portal = ""
    if url:
        host = url.lower()
        if "linkedin" in host:
            portal = "linkedin"
        elif "pracuj" in host:
            portal = "pracuj"
        elif "nofluff" in host:
            portal = "nofluffjobs"

    from app.services.scrape.posting_extract import description_for_storage

    stored = description_for_storage(raw, portal=portal, url=url or "")
    if len(stored) >= 80:
        raw = stored

    language = _resolve_job_language(role, raw)

    return JobParsed(
        company=company,
        role=role,
        location=location,
        language=language,
        raw_text=raw[:15000],
        source=source,
    )
