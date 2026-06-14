"""LaTeX preamble and macros for the custom CV article template."""

from __future__ import annotations


def cv_tex_preamble(pdf_title: str) -> str:
    """Shared document preamble matching the HTML reference design."""
    return rf"""\documentclass[10.5pt,a4paper]{{extarticle}}

\usepackage{{fontspec}}
\IfFontExistsTF{{TeX Gyre Heros}}{{
  \setmainfont{{TeX Gyre Heros}}
}}{{
  \setmainfont{{Latin Modern Sans}}
}}
\usepackage[margin=12mm]{{geometry}}
\usepackage{{xcolor}}
\usepackage{{enumitem}}
\usepackage{{hyperref}}

\definecolor{{cvNavy}}{{HTML}}{{1A365D}}
\definecolor{{cvTitle}}{{HTML}}{{4A5568}}
\definecolor{{cvMuted}}{{HTML}}{{718096}}
\definecolor{{cvText}}{{HTML}}{{2D3748}}
\definecolor{{cvRule}}{{HTML}}{{E2E8F0}}
\definecolor{{cvAccent}}{{HTML}}{{CBD5E1}}

\color{{cvText}}
\setlength{{\parskip}}{{0pt}}
\setlength{{\parindent}}{{0pt}}

\newcommand{{\cvBodyLeading}}{{15.75pt}}
\newcommand{{\cvListLeading}}{{15.2pt}}
\newcommand{{\cvSectionBefore}}{{10pt}}
\newcommand{{\cvSectionAfter}}{{6pt}}
\newcommand{{\cvJobGap}}{{10pt}}
\newcommand{{\cvSkillBarHeight}}{{12pt}}

\hypersetup{{
    colorlinks=true,
    linkcolor=cvNavy,
    urlcolor=cvNavy,
    pdftitle={{{pdf_title}}},
}}

\setlist[itemize]{{leftmargin=18pt, topsep=0pt, itemsep=2pt, parsep=0pt, partopsep=0pt, label=\textbullet}}

\AtBeginDocument{{\fontsize{{10.5}}{{\cvBodyLeading}}\selectfont}}

\newcommand{{\cvsection}}[1]{{
  \vspace{{\cvSectionBefore}}
  {{\color{{cvNavy}}\bfseries\fontsize{{12}}{{14}}\selectfont\MakeUppercase{{#1}}\par}}
  \vspace{{4pt}}
  {{\color{{cvRule}}\rule{{\linewidth}}{{2pt}}}}
  \vspace{{\cvSectionAfter}}
}}

\newcommand{{\cvheader}}[3]{{
  {{\fontsize{{28}}{{32}}\bfseries\color{{cvNavy}}#1\par}}
  \vspace{{2pt}}
  {{\fontsize{{14}}{{17}}\bfseries\color{{cvTitle}}#2\par}}
  \vspace{{4pt}}
  {{\begingroup\fontsize{{9.5}}{{14}}\color{{cvMuted}}#3\par\endgroup}}
  \vspace{{6pt}}
  {{\color{{cvNavy}}\rule{{\linewidth}}{{3pt}}}}
  \vspace{{10pt}}
}}

\newcommand{{\cvskillcategory}}[2]{{
  \vspace{{2pt}}
  \noindent
  \llap{{\textcolor{{cvAccent}}{{\rule{{3pt}}{{12pt}}}}}}\hspace{{6pt}}%
  \hangindent=9pt\hangafter=1
  \textbf{{\color{{cvNavy}}#1}}: #2\par
}}

\newcommand{{\cvjob}}[3]{{
  {{\fontsize{{11}}{{14}}\bfseries\color{{cvText}}#1\par}}
  \nopagebreak[2]
  \vspace{{1pt}}
  {{\fontsize{{9.5}}{{14}}\color{{cvMuted}}#2\par}}
  \vspace{{3pt}}
  \begingroup\fontsize{{10.5}}{{\cvListLeading}}\selectfont
  #3
  \endgroup
  \vspace{{\cvJobGap}}
}}

\newcommand{{\cveducation}}[2]{{
  #1\par
  \vspace{{2pt}}
  {{\fontsize{{9.5}}{{14}}\color{{cvMuted}}#2\par}}
  \vspace{{6pt}}
}}

"""
