"""Shared fit-tier sorting helpers."""

from __future__ import annotations

from typing import Callable, Iterable, TypeVar

FIT_SORT_KEY = {"high": 0, "medium": 1, "low": 2}


def fit_sort_key(fit: str | None) -> int:
    if not fit:
        return 9
    return FIT_SORT_KEY.get(fit, 9)


T = TypeVar("T")


def sort_by_fit(items: Iterable[T], getter: Callable[[T], str | None]) -> list[T]:
    return sorted(items, key=lambda item: fit_sort_key(getter(item)))
