from unittest.mock import AsyncMock, patch

import pytest

from app.llm.client import BielikClient, clear_probe_cache
from app.llm.exceptions import LlmDegradedError


@pytest.fixture(autouse=True)
def _clear_probe():
    clear_probe_cache()


@pytest.mark.asyncio
async def test_is_ready_requires_valid_json_probe():
    client = BielikClient()
    with patch.object(client, "healthcheck", AsyncMock(return_value={"ok": True})):
        with patch.object(
            client,
            "probe_chat",
            AsyncMock(return_value=False),
        ):
            assert await client.is_ready(probe=True) is False


@pytest.mark.asyncio
async def test_is_ready_ok_when_health_and_probe_pass():
    client = BielikClient()
    with patch.object(client, "healthcheck", AsyncMock(return_value={"ok": True})):
        with patch.object(client, "probe_chat", AsyncMock(return_value=True)):
            assert await client.is_ready(probe=True) is True


@pytest.mark.asyncio
async def test_is_ready_probe_rescues_failed_healthcheck():
    client = BielikClient()
    with patch.object(client, "healthcheck", AsyncMock(return_value={"ok": False})):
        with patch.object(client, "probe_chat", AsyncMock(return_value=True)):
            assert await client.is_ready(probe=True) is True


@pytest.mark.asyncio
async def test_healthcheck_extended_marks_inference_fail():
    client = BielikClient()
    with patch.object(client, "healthcheck", AsyncMock(return_value={"ok": True, "status": "ready"})):
        with patch.object(client, "probe_chat", AsyncMock(return_value=False)):
            ext = await client.healthcheck_extended(force_probe=True)
            assert ext["models_ok"] is True
            assert ext["inference_ok"] is False
            assert ext["ok"] is False


@pytest.mark.asyncio
async def test_wait_until_ready_succeeds_when_probe_passes():
    client = BielikClient()
    with patch.object(client, "is_ready", AsyncMock(return_value=True)):
        with patch.object(
            client,
            "healthcheck_extended",
            AsyncMock(return_value={"ok": True, "inference_ok": True, "status": "ready"}),
        ):
            ext = await client.wait_until_ready(timeout=1, poll_interval=0.01)
            assert ext["ok"] is True


@pytest.mark.asyncio
async def test_chat_complete_raises_on_esc_degradation():
    client = BielikClient()
    bad = '{"overall_fit":\x1b\x1b\x1b'
    with patch.object(client, "resolve_model", AsyncMock(return_value="test-model")):
        with patch.object(client, "_post_completion", AsyncMock(return_value=bad)):
            with pytest.raises(LlmDegradedError):
                await client.chat_complete(
                    [{"role": "user", "content": "Return JSON"}],
                    max_tokens=128,
                )
