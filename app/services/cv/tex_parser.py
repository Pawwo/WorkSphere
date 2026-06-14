"""Parse LaTeX cover letter sources back into cover_data dicts."""

from __future__ import annotations

import re
from typing import List


def unescape_latex_text(text: str) -> str:
    """Reverse common escape_latex sequences for plain-text fields."""
    if not text:
        return ""
    out = text
    replacements = (
        (r"\textbackslash{}", "\\"),
        (r"\textasciitilde{}", "~"),
        (r"\textasciicircum{}", "^"),
        (r"\%", "%"),
        (r"\&", "&"),
        (r"\$", "$"),
        (r"\#", "#"),
        (r"\_", "_"),
        (r"\{", "{"),
        (r"\}", "}"),
    )
    for escaped, plain in replacements:
        out = out.replace(escaped, plain)
    return out


def _extract_braced_command_values(tex: str, command: str) -> List[str]:
    """Extract argument bodies for ``\\command{...}`` with nested braces."""
    needle = f"\\{command}{{"
    results: List[str] = []
    pos = 0
    while True:
        idx = tex.find(needle, pos)
        if idx == -1:
            break
        i = idx + len(needle)
        depth = 1
        chunks: List[str] = []
        while i < len(tex) and depth:
            ch = tex[i]
            if ch == "\\" and i + 1 < len(tex):
                chunks.append(ch)
                chunks.append(tex[i + 1])
                i += 2
                continue
            if ch == "{":
                depth += 1
                if depth > 1:
                    chunks.append(ch)
            elif ch == "}":
                depth -= 1
                if depth > 0:
                    chunks.append(ch)
            else:
                chunks.append(ch)
            i += 1
        results.append(unescape_latex_text("".join(chunks)))
        pos = i
    return results


def parse_cover_tex(tex: str) -> dict:
    """Rebuild cover_data from a cover.cls LaTeX document."""
    letters = _extract_braced_command_values(tex, "lettercontent")
    bullets = [
        unescape_latex_text(m.group(1).strip())
        for m in re.finditer(r"\\item\s+(.+)", tex)
    ]
    return {
        "salutation": letters[0] if len(letters) > 0 else "",
        "opening": letters[1] if len(letters) > 1 else "",
        "body": letters[2] if len(letters) > 2 else "",
        "bullets": bullets,
        "motivation": letters[3] if len(letters) > 3 else "",
        "closing": letters[4] if len(letters) > 4 else "",
    }
