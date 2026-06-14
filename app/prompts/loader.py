from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache
def get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(name: str, **kwargs) -> str:
    template = get_env().get_template(name)
    return template.render(**kwargs)
