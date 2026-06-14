"""Shared LaTeX escaping utilities."""

from __future__ import annotations


def coerce_latex_text(text: object) -> str:
    """Normalize LLM / JSON values to a single LaTeX-safe string."""
    if text is None:
        return ""
    if isinstance(text, list):
        return " ".join(coerce_latex_text(part) for part in text if part is not None)
    return str(text)


def normalize_tex_chars(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("\u2013", "--")
        .replace("\u2014", "---")
        .replace("\u2019", "'")
        .replace("\u00a0", " ")
    )


def escape_latex(text: object) -> str:
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = normalize_tex_chars(coerce_latex_text(text))
    for char, escaped in repl.items():
        out = out.replace(char, escaped)
    return out


def cventry_item(period: str, title: str, org: str, location: str, body: str) -> str:
    return (
        f"\\item{{\\cventry{{{escape_latex(period)}}}"
        f"{{{escape_latex(title)}}}"
        f"{{{escape_latex(org)}}}"
        f"{{{escape_latex(location)}}}{{}}{{\\vspace{{1pt}}\n"
        f"{body}\n}}}}\n"
    )
