from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.latex import LatexIssue, LatexReport

_TEXT_MACROS = {
    "section": 1,
    "subsection": 1,
    "subsubsection": 1,
    "resumeItem": 1,
    "resumeSubItem": 1,
    "resumeSubheading": 4,
    "resumeProjectHeading": 3,
    "resumeSubSubheading": 2,
    "cvitem": 2,
    "cventry": 4,
    "cvlistitem": 1,
    "datedsubsection": 2,
    "name": 1,
    "address": 1,
    "position": 1,
    "quote": 1,
    "item": 0,
}

_SECURITY_PATTERNS: tuple[tuple[str, str, str], ...] = (    ("write18", r"\\write18", "error"),
    ("shell_escape", r"\\usepackage(?:\[[^\]]*\])?\{shellesc\}", "error"),
    ("immediate_write", r"\\immediate\s*\\write", "error"),
    ("openout", r"\\openout", "error"),
    ("direct_lua", r"\\directlua", "error"),
    ("path_traversal", r"\\(?:input|include|openin)\s*\{[^}]*\.\.[^}]*\}", "error"),
    ("absolute_input", r"\\(?:input|include)\s*\{\s*(?:/|[A-Za-z]:[\\/])", "error"),
)

_ATS_PATTERNS: tuple[tuple[str, str, str, str | None], ...] = (
    ("fontawesome", r"\\usepackage(?:\[[^\]]*\])?\{fontawesome5?\}", "Icon fonts are usually invisible to ATS parsers.", "Replace icons with plain text labels."),
    ("icon_font", r"\\fa[A-Z][A-Za-z]+|\\icons?\{", "Icon glyphs do not extract as text.", "Remove icon glyphs from contact and section headings."),
    ("tabular_layout", r"\\begin\{tabular\}", "Tables are commonly flattened out of reading order by ATS parsers.", "Use stacked sections instead of tabular layout."),
    ("multi_column", r"\\begin\{multicols\}|\\begin\{minipage\}\s*\{0?\.\d", "Multi-column layouts interleave text in extraction.", "Use a single-column layout."),
    ("graphics_text", r"\\includegraphics", "Text inside images cannot be parsed. Verify no critical text is in the image.", None),
    ("letter_spacing", r"\\hspace\{[^}]*\}\s*[A-Za-z]", "Manual letter spacing parses as broken words.", None),
    ("minted", r"\\usepackage(?:\[[^\]]*\])?\{minted\}", "Minted requires shell-escape, which this engine refuses to enable.", "Use a plain listings configuration or remove code blocks."),
)


@dataclass
class _Finding:
    code: str
    severity: str
    message: str
    line: int | None = None
    evidence: str | None = None
    auto_fix: str | None = None
    security_relevant: bool = False


_DATE_LIKE_RE = re.compile(
    r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*'?\d{2,4}$"
    r"|^\d{4}$|^present$|^current$|^now$",
    re.IGNORECASE,
)


def _is_date_like(value: str) -> bool:
    return bool(_DATE_LIKE_RE.match(value.strip()))


def strip_comments(tex: str) -> str:
    """Remove LaTeX comments while preserving escaped percent signs."""

    output: list[str] = []
    for line in tex.splitlines():
        index = 0
        cut = len(line)
        while index < len(line):
            char = line[index]
            if char == "\\":
                index += 2
                continue
            if char == "%":
                cut = index
                break
            index += 1
        output.append(line[:cut])
    return "\n".join(output)


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _balanced_groups(text: str) -> list[tuple[int, str]]:
    """Yield (index, group_content) for top-level brace groups."""

    groups: list[tuple[int, str]] = []
    depth = 0
    start = 0
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                groups.append((start, text[start:index]))
    return groups


def latex_to_text(tex: str) -> str:
    """Best-effort text extraction from a .tex source for structuring.

    This is a plain-text approximation, not a full TeX engine. Compiling the
    document and extracting from the PDF is the authoritative path (Phase 2).
    """

    body = strip_comments(tex)

    # Only the document body carries resume content; the preamble is markup.
    begin = re.search(r"\\begin\{document\}", body)
    if begin:
        body = body[begin.end() :]
    end = re.search(r"\\end\{document\}", body)
    if end:
        body = body[: end.start()]

    body = re.sub(r"\\(?:documentclass|usepackage|RequirePackage|input|include)\*?(?:\[[^\]]*\])?\{[^}]*\}", "\n", body)
    body = re.sub(r"\\(?:newcommand|renewcommand|def)\b", "\n", body)
    body = re.sub(r"\\(?:begin|end)\{(?:document|itemize|enumerate)\}", "\n", body)
    body = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\[[^\]]*\])?(?:\{[^}]*\})*", "\n", body)

    # Structural macros: keep their text arguments, one per line.
    def structural(match: re.Match[str]) -> str:
        name = match.group(1)
        rest = match.group(2)
        groups = [content for _, content in _balanced_groups(rest)]
        if name in {"section", "subsection", "subsubsection"}:
            return "\n## " + (groups[0] if groups else "") + "\n"
        if name in {"resumeSubheading", "cventry"}:
            if len(groups) >= 4 and _is_date_like(groups[-2]) and _is_date_like(groups[-1]):
                head = " | ".join(groups[:-2])
                return f"\n{head} | {groups[-2]} - {groups[-1]}\n"
            return "\n" + " | ".join(groups) + "\n"
        if name in {"resumeProjectHeading", "resumeSubSubheading", "datedsubsection"}:
            return "\n" + " | ".join(groups) + "\n"
        if name in {"resumeItem", "resumeSubItem", "cvlistitem"}:
            return "\n- " + (groups[0] if groups else "") + "\n"
        if name == "item":
            return "\n- "
        return "\n" + (groups[0] if groups else "") + "\n"

    body = re.sub(
        r"\\(section|subsection|subsubsection|resumeItem|resumeSubItem|resumeSubheading|"
        r"resumeProjectHeading|resumeSubSubheading|cvitem|cventry|cvlistitem|item|name|address|position)\*?"
        r"((?:\s*(?:\[[^\]]*\])?\s*\{[^{}]*\})+)",
        structural,
        body,
    )

    # Remaining commands: drop the name, keep brace contents.
    body = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?", " ", body)
    body = body.replace("\\\\", "\n").replace("\\par", "\n")
    body = body.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_")
    body = body.replace("\\#", "#").replace("\\$", "$").replace("\\{", "{").replace("\\}", "}")
    body = body.replace("~", " ")
    body = body.replace("{", "").replace("}", "")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n\n", body)
    return body.strip()


def analyse_latex(tex: str, filename: str = "resume.tex") -> LatexReport:
    source = strip_comments(tex)
    report = LatexReport(main_file=filename)

    document_class = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]*)\}", source)
    if document_class:
        report.document_class = document_class.group(1).strip()

    report.packages = sorted(
        {
            match.group(2).strip()
            for match in re.finditer(
                r"\\usepackage(?:\[([^\]]*)\])?\{([^}]*)\}", source
            )
            if match.group(2)
        }
    )

    findings: list[_Finding] = []

    for code, pattern, severity in _SECURITY_PATTERNS:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            findings.append(
                _Finding(
                    code=code,
                    severity=severity,
                    message=_security_message(code),
                    line=_line_at(source, match.start()),
                    evidence=match.group(0)[:120],
                    security_relevant=True,
                )
            )

    for code, pattern, message, auto_fix in _ATS_PATTERNS:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            findings.append(
                _Finding(
                    code=code,
                    severity="warning",
                    message=message,
                    line=_line_at(source, match.start()),
                    evidence=match.group(0)[:120],
                    auto_fix=auto_fix,
                )
            )

    # Hidden or microscopic white text is a known gaming signal.
    for match in re.finditer(r"\\color\{white\}|\\textcolor\{white\}", source, re.IGNORECASE):
        findings.append(
            _Finding(
                code="letter_spacing",
                severity="error",
                message="White text is treated as keyword stuffing by recruiters and ATS audits.",
                line=_line_at(source, match.start()),
                evidence=match.group(0),
                auto_fix="Remove hidden text entirely.",
            )
        )

    if report.packages and report.document_class not in {"article", "moderncv"}:
        pass  # unknown class is allowed; the macro registry handles it

    uses_pdflatex = "fontspec" not in report.packages
    has_glyph_map = "glyphtounicode" in source and "pdfgentounicode" in source
    if uses_pdflatex and not has_glyph_map:
        findings.append(
            _Finding(
                code="missing_glyphtounicode",
                severity="warning",
                message="pdfLaTeX output lacks a ToUnicode map, so ligatures and symbols may extract as garbage.",
                auto_fix="\\input{glyphtounicode}\\pdfgentounicode=1",
            )
        )
    if uses_pdflatex and "fontenc" not in source:
        findings.append(
            _Finding(
                code="missing_fontenc",
                severity="warning",
                message="No T1 font encoding declared; accented characters may not extract correctly.",
                auto_fix="\\usepackage[T1]{fontenc}",
            )
        )

    # Macro registry: built-ins plus popular resume template macros.
    defined: dict[str, int] = dict(_TEXT_MACROS)
    for match in re.finditer(
        r"\\(?:newcommand|renewcommand)\*?\s*\{?\\([A-Za-z@]+)\}?\s*(?:\[(\d)\])?", source
    ):
        defined[match.group(1)] = int(match.group(2) or 0)
    used = {
        match.group(1)
        for match in re.finditer(r"\\([A-Za-z@]+)\*?", source)
        if not match.group(1).startswith(("begin", "end"))
    }
    report.macros = {name: defined[name] for name in sorted(used) if name in defined}
    unknown = sorted(used - set(defined) - _TEX_PRIMITIVES)
    if unknown:
        findings.append(
            _Finding(
                code="unknown_macro",
                severity="info",
                message=(
                    f"{len(unknown)} macro(s) are not in the registry. The engine will "
                    "fall back to compile-and-extract for these."
                ),
                evidence=", ".join(unknown[:12]),
            )
        )

    report.issues = [
        LatexIssue(
            code=finding.code,  # type: ignore[arg-type]
            severity=finding.severity,  # type: ignore[arg-type]
            message=finding.message,
            line=finding.line,
            evidence=finding.evidence,
            auto_fix=finding.auto_fix,
            security_relevant=finding.security_relevant,
        )
        for finding in findings
    ]
    report.uses_shell_escape = any(
        issue.security_relevant for issue in report.issues
    )
    report.is_hostile = any(
        issue.security_relevant and issue.severity == "error" for issue in report.issues
    )

    penalty = 0.0
    for issue in report.issues:
        if issue.severity == "error":
            penalty += 25
        elif issue.severity == "warning":
            penalty += 8
        else:
            penalty += 1
    report.ats_risk_score = max(0.0, 100.0 - penalty)

    if uses_pdflatex:
        report.suggested_preamble = [
            "\\usepackage[T1]{fontenc}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage{lmodern}",
            "\\input{glyphtounicode}",
            "\\pdfgentounicode=1",
        ]
    return report


def _security_message(code: str) -> str:
    return {
        "write18": "\\write18 enables shell execution and is rejected.",
        "shell_escape": "The shellesc package enables shell execution and is rejected.",
        "immediate_write": "\\immediate\\write can overwrite files and is rejected.",
        "openout": "\\openout can write arbitrary files and is rejected.",
        "direct_lua": "\\directlua can execute code and is rejected.",
        "path_traversal": "A file reference escapes the sandbox with '..'.",
        "absolute_input": "An absolute path input can read host files.",
    }.get(code, "Unsafe LaTeX construct.")


_TEX_PRIMITIVES = frozenset(
    ["documentclass", "usepackage", "RequirePackage", "input", "include", "includeonly", "begin", "end", "item", "textbf", "textit", "emph", "underline", "texttt", "textsc", "textrm", "textsf", "textsl", "textup", "section", "subsection", "subsubsection", "paragraph", "subparagraph", "label", "ref", "pageref", "cite", "bibliography", "bibliographystyle", "maketitle", "tableofcontents", "newpage", "clearpage", "vspace", "hspace", "vfill", "hfill", "noindent", "centering", "raggedright", "linebreak", "newline", "par", "small", "large", "Large", "LARGE", "huge", "Huge", "tiny", "scriptsize", "footnotesize", "normalsize", "fontsize", "selectfont", "color", "textcolor", "definecolor", "fontfamily", "fontseries", "fontshape", "usefont", "href", "url", "hyperlink", "hypertarget", "pdfgentounicode", "glyphtounicode", "setlength", "addtolength", "setcounter", "thepage", "thispagestyle", "pagestyle", "newcommand", "renewcommand", "providecommand", "def", "let", "newenvironment", "renewenvironment", "if", "else", "fi", "ifx", "ifnum", "else", "fi", "relax", "expandafter", "csname", "endcsname", "write", "openout", "read", "closein", "closeout", "immediate", "catcode", "makeatletter", "makeatother"]
)
