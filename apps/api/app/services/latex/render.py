"""Render a canonical resume to an ATS-safe single-column LaTeX document.

This is the validation/export renderer used by the compile guard. It is not a
replacement for the user's original template; it intentionally avoids tables,
columns, icons, and shell-escape-heavy packages so a successful compile is a
strong signal that the content itself is parseable.
"""

from __future__ import annotations

from app.schemas.resume import Resume, ResumeDocument

_REPLACEMENTS = {
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


def escape_latex(value: str) -> str:
    return "".join(_REPLACEMENTS.get(char, char) for char in value)


def _contact_line(resume: Resume) -> str:
    basics = resume.basics
    parts = [
        basics.email,
        basics.phone,
        basics.url,
        *(profile.url for profile in basics.profiles),
    ]
    return " $\\cdot$ ".join(escape_latex(part) for part in parts if part)


def _date_range(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{escape_latex(start)} -- {escape_latex(end)}"
    if start:
        return escape_latex(start)
    if end:
        return escape_latex(end)
    return ""


def render_resume_tex(document: ResumeDocument) -> str:
    resume = document.canonical
    lines: list[str] = [
        r"\documentclass[10pt,letterpaper]{article}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{lmodern}",
        r"\usepackage[margin=0.7in]{geometry}",
        r"\usepackage{enumitem}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\input{glyphtounicode}",
        r"\pdfgentounicode=1",
        r"\setlength{\parindent}{0pt}",
        r"\pagestyle{empty}",
        r"\begin{document}",
    ]

    basics = resume.basics
    if basics.name:
        lines.append(r"\begin{center}")
        lines.append(r"{\LARGE \textbf{" + escape_latex(basics.name) + "}}")
        if basics.label:
            lines.append(r"\\ " + escape_latex(basics.label))
        contact = _contact_line(resume)
        if contact:
            lines.append(r"\\ " + contact)
        lines.append(r"\end{center}")

    if basics.summary:
        lines.extend([r"\section*{Summary}", escape_latex(basics.summary)])

    if resume.work:
        lines.append(r"\section*{Experience}")
        for work in resume.work:
            title = " ".join(filter(None, [work.position, work.name]))
            dates = _date_range(work.startDate, work.endDate)
            if title:
                lines.append(
                    r"\textbf{" + escape_latex(title) + "}"
                    + (r" \hfill " + dates if dates else "")
                    + r"\par"
                )
            if work.summary:
                lines.append(escape_latex(work.summary))
            if work.highlights:
                lines.append(r"\begin{itemize}[leftmargin=1.2em,itemsep=2pt,topsep=2pt]")
                for highlight in work.highlights:
                    lines.append(r"\item " + escape_latex(highlight))
                lines.append(r"\end{itemize}")

    if resume.education:
        lines.append(r"\section*{Education}")
        for education in resume.education:
            title = " ".join(
                filter(None, [education.studyType, education.area, education.institution])
            )
            dates = _date_range(education.startDate, education.endDate)
            if title:
                lines.append(
                    r"\textbf{" + escape_latex(title) + "}"
                    + (r" \hfill " + dates if dates else "")
                    + r"\par"
                )

    if resume.skills:
        lines.append(r"\section*{Skills}")
        for group in resume.skills:
            label = f"{group.name}: " if group.name else ""
            lines.append(
                r"\textbf{" + escape_latex(label) + "}"
                + escape_latex(", ".join(group.keywords))
                + r"\par"
            )

    if resume.projects:
        lines.append(r"\section*{Projects}")
        for project in resume.projects:
            if project.name:
                lines.append(r"\textbf{" + escape_latex(project.name) + r"}\par")
            if project.description:
                lines.append(escape_latex(project.description))
            if project.highlights:
                lines.append(r"\begin{itemize}[leftmargin=1.2em,itemsep=2pt,topsep=2pt]")
                for highlight in project.highlights:
                    lines.append(r"\item " + escape_latex(highlight))
                lines.append(r"\end{itemize}")

    if resume.certifications:
        lines.append(r"\section*{Certifications}")
        lines.append(r"\begin{itemize}[leftmargin=1.2em,itemsep=2pt,topsep=2pt]")
        for certification in resume.certifications:
            if certification.name:
                lines.append(r"\item " + escape_latex(certification.name))
        lines.append(r"\end{itemize}")

    if resume.languages:
        lines.append(r"\section*{Languages}")
        for language in resume.languages:
            label = " ".join(filter(None, [language.language, language.fluency]))
            if label:
                lines.append(escape_latex(label) + r"\par")

    if resume.awards:
        lines.append(r"\section*{Awards}")
        for award in resume.awards:
            title = " ".join(filter(None, [award.title, award.awarder, award.date]))
            if title:
                lines.append(r"\textbf{" + escape_latex(title) + r"}\par")
            if award.summary:
                lines.append(escape_latex(award.summary))

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


__all__ = ["escape_latex", "render_resume_tex"]
