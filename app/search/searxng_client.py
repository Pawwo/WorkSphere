from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class SearchResult:
    def __init__(self, title: str, url: str, snippet: str):
        self.title = title
        self.url = url
        self.snippet = snippet

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class SearXNGClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.searxng_base_url.rstrip("/")

    async def healthcheck(self) -> dict:
        try:
            results = await self.search("test", limit=1)
            return {
                "ok": True,
                "url": self.base_url,
                "sample_results": len(results),
            }
        except Exception as exc:
            logger.warning("SearXNG healthcheck failed: %s", exc)
            return {"ok": False, "url": self.base_url, "error": str(exc)}

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        language: Optional[str] = None,
        categories: str = "general",
    ) -> List[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "language": language or self.settings.searxng_language,
            "categories": categories,
        }
        url = f"{self.base_url}/search"
        async with httpx.AsyncClient(timeout=self.settings.searxng_timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in (data.get("results") or [])[:limit]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", "") or item.get("snippet", ""),
                )
            )
        return results

    async def search_company(self, company: str, limit: int = 5) -> List[SearchResult]:
        return await self.search(f"{company} Polska kariera o firmie", limit=limit)

    async def search_learning(self, skill: str, limit: int = 5) -> List[SearchResult]:
        return await self.search(f"{skill} kurs tutorial dokumentacja", limit=limit)
