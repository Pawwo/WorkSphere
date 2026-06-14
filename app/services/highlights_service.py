"""Generate high-match highlights (job-scraper SKILL Step 5)."""

from __future__ import annotations

import logging
from typing import List, Optional

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.llm.structured import extract_json
from app.llm.token_budgets import HIGHLIGHTS
from app.models.jobs import ScrapeResultItem, SeenJobEntry
from app.prompts.loader import render_prompt
from app.storage.files import load_seen_jobs, read_profile_excerpt, save_seen_jobs, seen_key

logger = logging.getLogger(__name__)


async def enrich_highlights_for_new_jobs(
    new_items: List[ScrapeResultItem],
    *,
    settings: Optional[Settings] = None,
) -> None:
    settings = settings or get_settings()
    high = [j for j in new_items if j.fit == "high"]
    if not high:
        return

    llm = BielikClient(settings)
    if not await llm.is_ready(probe=True):
        return

    max_jobs = max(1, int(getattr(settings, "scrape_highlights_max_per_run", 10)))
    seen = load_seen_jobs(settings.seen_jobs_path)
    profile = read_profile_excerpt(settings)
    enriched = 0

    for job in high:
        if enriched >= max_jobs:
            break
        key = seen_key(job.url, job.company or "", job.title)
        entry = seen.get(key)
        if not entry or entry.highlights:
            continue
        try:
            prompt = render_prompt(
                "job_highlights.jinja2",
                profile_excerpt=profile,
                job={
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "description": (job.description or "")[:1500],
                },
            )
            raw = await llm.chat_complete(
                [
                    {
                        "role": "system",
                        "content": "JSON only. Bez markdown i komentarzy.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=HIGHLIGHTS,
                temperature=0.2,
            )
            parsed = extract_json(raw)
            if isinstance(parsed, dict) and parsed.get("highlights"):
                entry.highlights = [str(h) for h in parsed["highlights"][:3]]
                seen[key] = entry
                enriched += 1
        except Exception as exc:
            logger.warning("highlights for %s failed: %s", job.url, exc)

    save_seen_jobs(settings.seen_jobs_path, seen)
