from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _read_braced_argument(tex: str, start: int) -> tuple[int, int] | None:
    """Return (arg_start, end_after_closing_brace) for a {...} group at `start`."""
    if start >= len(tex) or tex[start] != "{":
        return None
    depth = 0
    pos = start
    while pos < len(tex):
        ch = tex[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, pos + 1
        pos += 1
    return None


def _find_cvjob_spans(tex: str) -> List[tuple[int, int]]:
    spans: List[tuple[int, int]] = []
    marker = "\\cvjob{"
    pos = 0
    while True:
        start = tex.find(marker, pos)
        if start < 0:
            break
        cursor = start + len(marker) - 1
        end = None
        for _ in range(3):
            parsed = _read_braced_argument(tex, cursor)
            if not parsed:
                end = None
                break
            _, cursor = parsed
        else:
            while cursor < len(tex) and tex[cursor] in " \t\n\r":
                cursor += 1
            end = cursor
        if end is not None:
            spans.append((start, end))
        pos = start + len(marker)
    return spans


def _remove_last_cvjob(tex: str) -> str:
    exp_marker = "\\cvsection{Professional Experience}"
    edu_marker = "\\cvsection{Education}"
    exp_idx = tex.find(exp_marker)
    if exp_idx < 0:
        return tex
    edu_idx = tex.find(edu_marker, exp_idx)
    if edu_idx < 0:
        return tex
    section_spans = [
        (s, e) for s, e in _find_cvjob_spans(tex) if exp_idx < s < edu_idx
    ]
    if not section_spans:
        return tex
    start, end = section_spans[-1]
    return tex[:start] + tex[end:]


def _bin_available(cmd: str) -> bool:
    if "/" in cmd:
        return Path(cmd).is_file() and os.access(cmd, os.X_OK)
    return bool(shutil.which(cmd))


def _tinytex_bin_dir() -> Optional[Path]:
    import platform

    base = Path.home() / ".TinyTeX" / "bin" / f"{platform.machine()}-linux"
    if (base / "lualatex").is_file():
        return base
    return None


def resolve_latex_commands(settings: Optional[Settings] = None) -> tuple[str, str]:
    """Resolve lualatex/xelatex paths (runtime — nie polega wyłącznie na cache settings)."""
    env_dir = os.environ.get("LATEX_BIN_DIR")
    if env_dir:
        base = Path(env_dir).expanduser()
        lua, xe = base / "lualatex", base / "xelatex"
        if lua.is_file() and xe.is_file():
            return str(lua), str(xe)

    settings = settings or get_settings()
    if settings.latex_bin_dir:
        base = Path(settings.latex_bin_dir)
        lua, xe = base / "lualatex", base / "xelatex"
        if lua.is_file() and xe.is_file():
            return str(lua), str(xe)

    tinytex = _tinytex_bin_dir()
    if tinytex:
        return str(tinytex / "lualatex"), str(tinytex / "xelatex")

    return "lualatex", "xelatex"


class LatexService:
    CV_TARGET_PAGES = 2
    COVER_TARGET_PAGES = 1
    MAX_COMPILE_ATTEMPTS = 3

    def __init__(
        self,
        repo_root: Path,
        lualatex: Optional[str] = None,
        xelatex: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        settings = settings or get_settings()
        default_lua, default_xe = resolve_latex_commands(settings)
        self.repo_root = repo_root
        self.cv_dir = repo_root / "cv"
        self.cover_dir = repo_root / "cover_letters"
        self.lualatex = lualatex or default_lua
        self.xelatex = xelatex or default_xe
        self._env_path_prefix = str(settings.latex_bin_dir) if settings.latex_bin_dir else ""

    def tools_available(self) -> dict:
        return {
            "lualatex": _bin_available(self.lualatex),
            "xelatex": _bin_available(self.xelatex),
            "pdfinfo": bool(shutil.which("pdfinfo")),
            "lualatex_path": self.lualatex,
            "xelatex_path": self.xelatex,
        }

    def count_pdf_pages(self, pdf_path: Path) -> Optional[int]:
        pdfinfo = shutil.which("pdfinfo")
        if pdfinfo:
            import subprocess

            try:
                out = subprocess.run(
                    [pdfinfo, str(pdf_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                for line in out.stdout.splitlines():
                    if line.startswith("Pages:"):
                        return int(line.split(":", 1)[1].strip())
            except Exception:
                pass
        try:
            from pypdf import PdfReader  # type: ignore

            return len(PdfReader(str(pdf_path)).pages)
        except Exception:
            return None

    async def pdf_page_count(self, pdf_path: Path) -> Optional[int]:
        return self.count_pdf_pages(pdf_path)

    async def _run(self, cmd: List[str], cwd: Path) -> Tuple[bool, str]:
        env = os.environ.copy()
        if self._env_path_prefix:
            env["PATH"] = f"{self._env_path_prefix}:{env.get('PATH', '')}"
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        out, _ = await proc.communicate()
        text = out.decode(errors="replace")
        return proc.returncode == 0, text[-3000:]

    async def compile_cv(self, tex_name: str) -> Tuple[bool, str, Optional[Path]]:
        tex_path = self.cv_dir / tex_name
        if not tex_path.exists():
            return False, f"Brak pliku {tex_path}", None
        log_parts = []
        for _ in range(2):
            _, log = await self._run(
                [self.lualatex, "-interaction=nonstopmode", tex_name],
                self.cv_dir,
            )
            log_parts.append(log)
        pdf = self.cv_dir / tex_name.replace(".tex", ".pdf")
        ok = pdf.exists()
        return ok, "\n".join(log_parts), pdf if ok else None

    async def compile_cover(self, tex_name: str) -> Tuple[bool, str, Optional[Path]]:
        tex_path = self.cover_dir / tex_name
        if not tex_path.exists():
            return False, f"Brak pliku {tex_path}", None
        log_parts = []
        for _ in range(2):
            _, log = await self._run(
                [self.xelatex, "-interaction=nonstopmode", tex_name],
                self.cover_dir,
            )
            log_parts.append(log)
        pdf = self.cover_dir / tex_name.replace(".tex", ".pdf")
        ok = pdf.exists()
        return ok, "\n".join(log_parts), pdf if ok else None

    def trim_cv_for_page_limit(self, tex: str, attempt: int) -> str:
        if attempt <= 0:
            return tex
        # Remove oldest job entries (last \cvjob before Education)
        for _ in range(attempt):
            tex = _remove_last_cvjob(tex)
        # Drop trailing bullets from remaining jobs
        for _ in range(attempt):
            tex = re.sub(
                r"  \\item [^\n]+\n(?=\\end\{itemize\})",
                "",
                tex,
                count=1,
            )
        if attempt >= 2:
            tex = tex.replace(
                "\\usepackage[margin=12mm]{geometry}",
                "\\usepackage[margin=10mm]{geometry}",
            )
        return tex

    def trim_cover_for_page_limit(self, tex: str, attempt: int) -> str:
        if attempt <= 0:
            return tex
        tex = re.sub(r"\\item [^\n]+\n", "", tex, count=attempt)
        return tex

    async def compile_and_verify(
        self,
        cv_tex_path: Path,
        cover_tex_path: Path,
        cv_name: str,
        cover_name: str,
    ) -> Tuple[List[str], List[str], List[str]]:
        pdf_files: List[str] = []
        warnings: List[str] = []
        tools = self.tools_available()

        if not tools["lualatex"]:
            warnings.append(f"lualatex niedostępny ({self.lualatex}) — uruchom: bash scripts/install_latex.sh")
            return pdf_files, warnings, ["fail: brak lualatex"]

        if not tools["xelatex"]:
            warnings.append(f"xelatex niedostępny ({self.xelatex}) — uruchom: bash scripts/install_latex.sh")
            return pdf_files, warnings, ["fail: brak xelatex"]

        cv_tex = cv_tex_path.read_text(encoding="utf-8")
        cover_tex = cover_tex_path.read_text(encoding="utf-8")
        cv_pages: Optional[int] = None
        cover_pages: Optional[int] = None
        cover_stale = True
        cached_cover: Tuple[bool, str, Optional[Path]] = (False, "", None)

        for attempt in range(self.MAX_COMPILE_ATTEMPTS):
            cv_tex_path.write_text(cv_tex, encoding="utf-8")
            if cover_stale:
                cover_tex_path.write_text(cover_tex, encoding="utf-8")
                cv_result, cover_result = await asyncio.gather(
                    self.compile_cv(cv_name),
                    self.compile_cover(cover_name),
                )
                cv_ok, cv_log, cv_pdf = cv_result
                cover_ok, cover_log, cover_pdf = cover_result
                cached_cover = (cover_ok, cover_log, cover_pdf)
            else:
                cv_ok, cv_log, cv_pdf = await self.compile_cv(cv_name)
                cover_ok, cover_log, cover_pdf = cached_cover

            if not cv_ok:
                warnings.append(f"Kompilacja CV nieudana (próba {attempt + 1}): {cv_log[-200:]}")
            if not cover_ok:
                warnings.append(f"Kompilacja listu nieudana (próba {attempt + 1}): {cover_log[-200:]}")

            pdf_files = []
            cv_pages = cover_pages = None
            if cv_pdf:
                cv_pages = await self.pdf_page_count(cv_pdf)
                pdf_files.append(str(cv_pdf.relative_to(self.repo_root)))
                self.cleanup_artifacts(cv_tex_path)
            if cover_pdf:
                cover_pages = await self.pdf_page_count(cover_pdf)
                pdf_files.append(str(cover_pdf.relative_to(self.repo_root)))
                self.cleanup_artifacts(cover_tex_path)

            if cv_ok and cover_ok and cv_pages == self.CV_TARGET_PAGES and cover_pages == self.COVER_TARGET_PAGES:
                return pdf_files, warnings, [
                    f"pass: CV {cv_pages} stron",
                    f"pass: List {cover_pages} stron",
                ]

            cover_stale = False
            if attempt < self.MAX_COMPILE_ATTEMPTS - 1:
                if cv_pages and cv_pages > self.CV_TARGET_PAGES:
                    cv_tex = self.trim_cv_for_page_limit(cv_tex, attempt + 1)
                    warnings.append(f"CV ma {cv_pages} stron — przycinam treść (próba {attempt + 2})")
                if cover_pages and cover_pages > self.COVER_TARGET_PAGES:
                    trimmed = self.trim_cover_for_page_limit(cover_tex, attempt + 1)
                    if trimmed != cover_tex:
                        cover_tex = trimmed
                        cover_stale = True
                        warnings.append(f"List ma {cover_pages} stron — przycinam (próba {attempt + 2})")

        cv_status = (
            f"pass: CV {cv_pages} stron"
            if cv_pages == self.CV_TARGET_PAGES
            else f"fail: CV {cv_pages or '?'} stron (cel {self.CV_TARGET_PAGES})"
        )
        cover_status = (
            f"pass: List {cover_pages} stron"
            if cover_pages == self.COVER_TARGET_PAGES
            else f"fail: List {cover_pages or '?'} stron (cel {self.COVER_TARGET_PAGES})"
        )
        if cv_pages == self.CV_TARGET_PAGES and cover_pages == self.COVER_TARGET_PAGES:
            return pdf_files, warnings, [cv_status, cover_status]

        return pdf_files, warnings, [cv_status, cover_status]

    def cleanup_artifacts(self, base_path: Path) -> None:
        for ext in (".aux", ".log", ".out"):
            p = base_path.with_suffix(ext)
            if p.exists():
                p.unlink()
