"""
Generate LaTeX (and optional PDF) from the latest investor executive summary markdown.

This keeps PDF output aligned with the markdown source of truth instead of maintaining
parallel handcrafted templates.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from src.config import PROJECT_ROOT


def detect_engine(preferred_engine: str | None) -> str:
    if preferred_engine:
        return preferred_engine
    if shutil.which("xelatex"):
        return "xelatex"
    if shutil.which("pdflatex"):
        return "pdflatex"
    raise RuntimeError("No LaTeX engine found. Install xelatex or pdflatex.")


def latex_escape(value: str) -> str:
    escaped = value
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "#": r"\#",
        "$": r"\$",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
    }
    for old, new in replacements.items():
        escaped = escaped.replace(old, new)
    return escaped


def extract_title_page_fields(markdown_text: str) -> dict[str, str] | None:
    lines = [line.strip() for line in markdown_text.splitlines()]
    # Skip front matter
    if lines[:1] == ["---"]:
        try:
            end = lines.index("---", 1)
            lines = lines[end + 1 :]
        except ValueError:
            pass

    def find_line(prefix: str) -> str | None:
        for line in lines:
            if line.startswith(prefix):
                return line
        return None

    title = None
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    as_of = find_line("As-of (latest monitoring observation):")
    generated = find_line("Report generated:")
    evidence = find_line("Evidence window (verified baseline):")
    reference = find_line("Reference SUMR price used in this memo:")

    if not all([title, as_of, generated, evidence, reference]):
        return None
    return {
        "title": title,
        "as_of": as_of,  # type: ignore[return-value]
        "generated": generated,  # type: ignore[return-value]
        "evidence": evidence,  # type: ignore[return-value]
        "reference": reference,  # type: ignore[return-value]
    }


def build_custom_title_page(fields: dict[str, str]) -> str:
    title = fields["title"]
    title_line_1 = title
    title_line_2 = ""
    title_line_3 = ""
    if " — " in title and title.endswith(" Draft"):
        left, right = title.rsplit(" — ", 1)
        if right.endswith(" Draft"):
            title_line_1 = left
            title_line_2 = "— " + right[: -len(" Draft")]
            title_line_3 = "Draft"
    elif title.endswith(" Draft"):
        title_line_1 = title[: -len(" Draft")]
        title_line_3 = "Draft"

    title_1 = latex_escape(title_line_1)
    title_2 = latex_escape(title_line_2)
    title_3 = latex_escape(title_line_3)
    as_of = latex_escape(fields["as_of"])
    generated = latex_escape(fields["generated"])
    evidence = latex_escape(fields["evidence"])
    reference = latex_escape(fields["reference"])

    title_block = "{\\fontsize{19}{24}\\selectfont\\bfseries " + title_1 + "\\par}\n"
    if title_2:
        title_block += "\\vspace{0.35cm}\n{\\fontsize{19}{24}\\selectfont\\bfseries " + title_2 + "\\par}\n"
    if title_3:
        title_block += "\\vspace{0.35cm}\n{\\fontsize{19}{24}\\selectfont\\bfseries " + title_3 + "\\par}\n"

    return (
        "\\begin{titlepage}\n"
        "\\thispagestyle{empty}\n"
        "\\centering\n"
        "\\vspace*{2.4cm}\n"
        f"{title_block}"
        "\\vspace{2.1cm}\n"
        "{\\large " + as_of + "\\par}\n"
        "\\vspace{0.95cm}\n"
        "{\\large " + generated + "\\par}\n"
        "\\vspace{0.95cm}\n"
        "{\\large " + evidence + "\\par}\n"
        "\\vspace{0.95cm}\n"
        "{\\large " + reference + "\\par}\n"
        "\\end{titlepage}\n\n"
    )


def build_tex_from_markdown(markdown_path: Path, tex_path: Path) -> None:
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_text = markdown_path.read_text(encoding="utf-8")
    title_fields = extract_title_page_fields(markdown_text)
    cmd = [
        "pandoc",
        markdown_path.name,
        "--from",
        "markdown+raw_tex+tex_math_dollars+pipe_tables",
        "--to",
        "latex",
        "--standalone",
        "-V",
        "geometry:margin=1in",
        "-V",
        "linestretch=1.5",
        "-V",
        "colorlinks=true",
        "-o",
        tex_path.name,
    ]
    subprocess.run(cmd, cwd=markdown_path.parent, check=True)
    # Keep markdown text layer unchanged while ensuring key unicode inequality
    # symbols render reliably across default LaTeX font stacks.
    tex_content = tex_path.read_text(encoding="utf-8")
    tex_content = tex_content.replace("\\maketitle\n\n", "")
    tex_content = re.sub(
        r"\{\s*\\hypersetup\{linkcolor=\}\s*\\setcounter\{tocdepth\}\{3\}\s*\\tableofcontents\s*\}\s*",
        "",
        tex_content,
        count=1,
        flags=re.S,
    )
    if title_fields:
        title_marker = "\\hypertarget{sumr-investor-executive-summary-narrative-draft}"
        body_marker = "\\hypertarget{how-to-read-this-memo}"
        start = tex_content.find(title_marker)
        end = tex_content.find(body_marker)
        if start != -1 and end != -1 and end > start:
            tex_content = tex_content[:start] + build_custom_title_page(title_fields) + tex_content[end:]
    tex_content = tex_content.replace("≥", "$\\geq$")
    tex_content = tex_content.replace("≤", "$\\leq$")
    tex_path.write_text(tex_content, encoding="utf-8")


def compile_pdf(tex_path: Path, engine: str | None = None) -> Path:
    selected_engine = detect_engine(engine)
    cmd = [selected_engine, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    for _ in range(2):
        subprocess.run(cmd, cwd=tex_path.parent, check=True)
    return tex_path.with_suffix(".pdf")


def run(
    markdown_path: Path,
    output_tex_path: Path,
    compile_output: bool,
    engine: str | None,
) -> None:
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown summary not found: {markdown_path}")

    build_tex_from_markdown(markdown_path=markdown_path, tex_path=output_tex_path)
    print(f"Wrote LaTeX report to {output_tex_path}")

    if compile_output:
        pdf_path = compile_pdf(output_tex_path, engine=engine)
        print(f"Compiled PDF to {pdf_path}")


def main() -> None:
    default_markdown = PROJECT_ROOT / "paper" / "investor_executive_summary.md"
    default_output_tex = PROJECT_ROOT / "paper" / "investor_executive_summary.tex"

    parser = argparse.ArgumentParser(description="Generate investor LaTeX/PDF from markdown executive summary.")
    parser.add_argument("--markdown-path", type=Path, default=default_markdown)
    parser.add_argument("--output-path", type=Path, default=default_output_tex)
    parser.add_argument("--compile", action="store_true", help="Compile PDF after writing .tex")
    parser.add_argument("--engine", type=str, default=None, help="LaTeX engine (xelatex or pdflatex)")
    args = parser.parse_args()

    run(
        markdown_path=args.markdown_path,
        output_tex_path=args.output_path,
        compile_output=bool(args.compile),
        engine=args.engine,
    )


if __name__ == "__main__":
    main()
