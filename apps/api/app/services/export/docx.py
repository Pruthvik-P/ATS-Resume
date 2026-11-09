"""Render a canonical resume to a clean single-column DOCX."""

from __future__ import annotations

from io import BytesIO

from app.schemas.resume import Resume, ResumeDocument


def _add_heading(document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(text.upper())
    run.bold = True
    run.font.size = None


def _add_line(document, text: str, *, bold: bool = False, italic: bool = False) -> None:
    if not text.strip():
        return
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    paragraph.paragraph_format.space_after = None


def _add_bullet(document, text: str) -> None:
    if not text.strip():
        return
    paragraph = document.add_paragraph(text, style="List Bullet")
    paragraph.paragraph_format.space_after = None


def _contact_line(resume: Resume) -> str:
    basics = resume.basics
    parts = [basics.email, basics.phone, basics.url]
    parts.extend(profile.url for profile in basics.profiles if profile.url)
    return " | ".join(part for part in parts if part)


def render_resume_docx(document: ResumeDocument) -> bytes:
    from docx import Document
    from docx.shared import Inches

    resume = document.canonical
    output = Document()
    section = output.sections[0]
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)

    normal = output.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = None

    basics = resume.basics
    if basics.name:
        paragraph = output.add_paragraph()
        paragraph.alignment = 1
        run = paragraph.add_run(basics.name)
        run.bold = True
        run.font.size = None
    if basics.label:
        paragraph = output.add_paragraph()
        paragraph.alignment = 1
        paragraph.add_run(basics.label)
    contact = _contact_line(resume)
    if contact:
        paragraph = output.add_paragraph()
        paragraph.alignment = 1
        paragraph.add_run(contact)

    if basics.summary:
        _add_heading(output, "Summary")
        _add_line(output, basics.summary)

    if resume.work:
        _add_heading(output, "Experience")
        for work in resume.work:
            title = " | ".join(filter(None, [work.position, work.name]))
            dates = " | ".join(filter(None, [work.startDate, work.endDate]))
            _add_line(output, title, bold=True)
            if dates:
                _add_line(output, dates)
            if work.summary:
                _add_line(output, work.summary)
            for highlight in work.highlights:
                _add_bullet(output, highlight)

    if resume.education:
        _add_heading(output, "Education")
        for education in resume.education:
            title = " | ".join(
                filter(None, [education.studyType, education.area, education.institution])
            )
            _add_line(output, title, bold=True)
            if education.score:
                _add_line(output, education.score)

    if resume.skills:
        _add_heading(output, "Skills")
        for group in resume.skills:
            label = f"{group.name}: " if group.name else ""
            _add_line(output, label + ", ".join(group.keywords))

    if resume.projects:
        _add_heading(output, "Projects")
        for project in resume.projects:
            _add_line(output, project.name or "", bold=True)
            if project.description:
                _add_line(output, project.description)
            for highlight in project.highlights:
                _add_bullet(output, highlight)

    if resume.certifications:
        _add_heading(output, "Certifications")
        for certification in resume.certifications:
            _add_line(output, certification.name or "")

    if resume.languages:
        _add_heading(output, "Languages")
        for language in resume.languages:
            _add_line(
                output,
                " ".join(filter(None, [language.language, language.fluency])),
            )

    if resume.awards:
        _add_heading(output, "Awards")
        for award in resume.awards:
            _add_line(
                output,
                " | ".join(filter(None, [award.title, award.awarder, award.date])),
                bold=True,
            )
            if award.summary:
                _add_line(output, award.summary)

    buffer = BytesIO()
    output.save(buffer)
    return buffer.getvalue()


__all__ = ["render_resume_docx"]
