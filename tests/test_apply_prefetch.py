"""Tests for apply service prefetch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.apply_service import ApplyService


@pytest.mark.asyncio
async def test_prefetch_company_search_warms_cache():
    svc = ApplyService()
    result = MagicMock()
    result.to_dict = MagicMock(return_value={"title": "Pearson", "snippet": "EdTech"})
    with patch.object(svc.search, "search_company", AsyncMock(return_value=[result])) as search:
        await svc.prefetch_company_search("Pearson")
        await svc.prefetch_company_search("Pearson")
    search.assert_awaited_once()
    assert "pearson" in svc._searxng_cache
