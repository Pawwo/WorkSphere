"""Jinja2 environment for CV/cover HTML templates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

CV_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "cv"


@lru_cache
def get_cv_template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(CV_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml", "jinja2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def load_cv_css(name: str = "cv.css") -> str:
    return (CV_TEMPLATES_DIR / name).read_text(encoding="utf-8")
