"""Persistent cache for quick_fit LLM results."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from app.config import ROOT, get_settings

FitLevel = Literal["high", "medium", "low"]

logger = logging.getLogger(__name__)

_memory: dict[str, FitLevel] = {}
_loaded = False
_cache_path: Path | None = None


def _default_cache_path() -> Path:
    return get_settings().data_dir / "fit_cache.json"


def _resolve_path(path: Path | None = None) -> Path:
    global _cache_path
    if path is not None:
        _cache_path = path
    if _cache_path is None:
        _cache_path = _default_cache_path()
    return _cache_path


def _cache_key(url: str, title: str, company: str) -> str:
    raw = f"{url}|{title}|{company}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _ensure_loaded(path: Path | None = None) -> None:
    global _loaded
    if _loaded:
        return
    p = _resolve_path(path)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if v in ("high", "medium", "low"):
                        _memory[str(k)] = v  # type: ignore[assignment]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("fit_cache load failed: %s", exc)
    _loaded = True


def _persist() -> None:
    p = _resolve_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_memory, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError as exc:
        logger.warning("fit_cache persist failed: %s", exc)


def get_fit(url: str, title: str, company: str) -> FitLevel | None:
    _ensure_loaded()
    return _memory.get(_cache_key(url, title, company))


def set_fit(url: str, title: str, company: str, fit: FitLevel) -> None:
    _ensure_loaded()
    _memory[_cache_key(url, title, company)] = fit
    _persist()


def clear_fit_cache(path: Path | None = None) -> None:
    global _loaded, _cache_path
    _memory.clear()
    _loaded = False
    p = _resolve_path(path)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
    if path is not None:
        _cache_path = path


def configure_fit_cache_for_tests(path: Path | None = None) -> None:
    """Point cache at a temp file (tests)."""
    global _loaded, _cache_path
    _loaded = False
    _memory.clear()
    _cache_path = path or (ROOT / "data" / "test_fit_cache.json")
