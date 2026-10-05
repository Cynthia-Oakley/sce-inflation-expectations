#!/usr/bin/env python3
"""Render the current proposal with the team's agreed typography.

Requires pandoc, xelatex, fc-match, Kaiti SC and Times New Roman locally.
The Markdown text is unchanged; LaTeX intermediates stay under ignored build/.
"""

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
STEM = "proposal_submission_candidate_20261005"
HEADER = r"""
\usepackage{indentfirst}
\usepackage{titlesec}
\setlength{\parindent}{2em}
\setlength{\parskip}{2pt}
\titleformat{\section}{\Large\bfseries}{}{0pt}{}
\titleformat{\subsection}{\large\bfseries}{}{0pt}{}
\titlespacing*{\section}{0pt}{0pt}{7pt}
\titlespacing*{\subsection}{0pt}{8pt}{4pt}
\setlength{\tabcolsep}{5pt}
\setlength{\arrayrulewidth}{0.4pt}
\setlength{\LTpre}{5pt}
\setlength{\LTpost}{5pt}
"""


def grid_table(match: re.Match) -> str:
    table = match.group(0)
    # Three columns, including padding and all four vertical rules in the width.
    columns = "|" + "|".join(
        r">{\raggedright\arraybackslash}p{(\linewidth - 6\tabcolsep - 4\arrayrulewidth) * \real{"
        + width
        + "}}"
        for width in ("0.13", "0.57", "0.30")
    ) + "|"
    table = re.sub(
        r"\\begin\{longtable\}\[\]\{.*?\n\\toprule\\noalign\{\}",
        lambda _: r"\begin{longtable}[]{" + columns + "}\n" + r"\hline",
        table,
        count=1,
        flags=re.S,
    )
    table = table.replace(r"\midrule\noalign{}", r"\hline")
    # Every body row has a rule; the final row also supplies the bottom border.
    table = table.replace(r"\bottomrule\noalign{}", "")
    head, body = table.split(r"\endlastfoot", 1)
    body = body.replace(" \\\\\n", " \\\\\n\\hline\n")
    return head + r"\endlastfoot" + body


def main() -> None:
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    header = build / "proposal_typography.tex"
    header.write_text(HEADER, encoding="utf-8")
    # macOS downloadable fonts may be invisible to XeTeX by family name.
    # Resolve the actual TTC and select its Simplified-Chinese regular/bold faces.
    kaiti = subprocess.run(
        ["fc-match", "-f", "%{file}", "Kaiti SC"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not Path(kaiti).is_file() or Path(kaiti).name != "Kaiti.ttc":
        raise RuntimeError("Kaiti SC font collection is not available")
    result = subprocess.run(
        [
            "pandoc", str(ROOT / f"{STEM}.md"), "--standalone", "--to=latex",
            "-V", "mainfont=Times New Roman", "-V", "CJKmainfont=Kaiti.ttc",
            "-V", f"CJKoptions=Path={{{Path(kaiti).parent}/}},FontIndex=0,BoldFont=Kaiti.ttc,BoldFeatures={{FontIndex=3}}",
            "-V", "fontsize=10pt", "-V", "papersize=a4", "-V", "indent=true",
            "-V", "linestretch=1.25", "-V", "geometry:margin=18mm",
            "-V", "colorlinks=true", "-V", "urlcolor=black",
            "--include-in-header", str(header),
        ],
        capture_output=True, text=True, check=True,
    )
    latex, count = re.subn(
        r"\\begin\{longtable\}.*?\\end\{longtable\}",
        grid_table, result.stdout, flags=re.S,
    )
    if count != 1 or latex.count(r"\hline") != 5:
        raise RuntimeError("Expected exactly one P/E/B table with five horizontal rules")
    # The competition line is a subtitle, not an indented body paragraph.
    latex = latex.replace(r"\textbf{SocioVerse Challenge", r"\noindent\textbf{SocioVerse Challenge", 1)
    # Start validation on page two so its list does not straddle the page break.
    latex = latex.replace(r"\subsection{三、验证方案}", "\\newpage\n" + r"\subsection{三、验证方案}", 1)
    tex = build / f"{STEM}.tex"
    tex.write_text(latex, encoding="utf-8")
    for _ in range(2):
        subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
             f"-output-directory={build}", str(tex)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
    print(build / f"{STEM}.pdf")


if __name__ == "__main__":
    main()
