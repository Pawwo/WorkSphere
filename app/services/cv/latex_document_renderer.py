"""LaTeX document renderer (legacy path)."""

from __future__ import annotations

from app.services.cv.tex_builder import build_cv_tex
from app.services.cv.types import CvDraftData
from app.services.latex_utils import escape_latex


class LatexDocumentRenderer:
    @property
    def file_extension(self) -> str:
        return ".tex"

    def render_cv(self, draft: CvDraftData, identity: dict, company_slug: str = "") -> str:
        return build_cv_tex(draft, identity, company_slug)

    def render_cover(
        self,
        cover_data: dict,
        identity: dict,
        company_slug: str,
        role_slug: str,
    ) -> str:
        bullets = "\n".join(
            f"    \\item {escape_latex(b)}" for b in cover_data.get("bullets", [])
        )
        linkedin = identity.get("linkedin", "")
        linkedin_part = (
            f"\\href{{{linkedin}}}{{LinkedIn}} | " if linkedin and linkedin != "—" else ""
        )
        return f"""\\documentclass[]{{cover}}
\\usepackage{{fancyhdr}}
\\pagestyle{{fancy}}
\\fancyhf{{}}
\\thispagestyle{{empty}}
\\renewcommand{{\\headrulewidth}}{{0pt}}
\\begin{{document}}
\\namesection{{}}{{\\Huge{{{escape_latex(identity['name'])}}}}}{{  \\href{{mailto:{identity['email']}}}{{{escape_latex(identity['email'])}}} | {escape_latex(identity['phone'])} | {linkedin_part}}}
\\currentdate{{\\today}}
\\lettercontent{{{escape_latex(cover_data.get('salutation',''))}}}
\\lettercontent{{{escape_latex(cover_data.get('opening',''))}}}
\\lettercontent{{{escape_latex(cover_data.get('body',''))}}}
{{\\raggedright\\fontspec[Path = OpenFonts/fonts/raleway/]{{Raleway-Medium}}\\fontsize{{11pt}}{{13pt}}\\selectfont
\\begin{{itemize}}
{bullets}
\\end{{itemize}}\\par}}
\\lettercontent{{{escape_latex(cover_data.get('motivation',''))}}}
\\lettercontent{{{escape_latex(cover_data.get('closing',''))}}}
\\begin{{flushright}}
\\closing{{Kind regards,}}
\\signature{{{escape_latex(identity['name'])}}}
\\end{{flushright}}
\\end{{document}}
"""
