"""LLM client errors."""

from __future__ import annotations


class LlmDegradedError(RuntimeError):
    """Inference returned ESC garbage or unparseable JSON after retries."""
