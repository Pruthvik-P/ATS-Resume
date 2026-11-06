from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import UnsupportedFormatError
from app.schemas.common import ParseIssue, SourceFormat
from app.schemas.latex import LatexReport
from app.schemas.resume import ResumeDocument
from app.services.ingest.docx import extract_docx
from app.services.ingest.latex import analyse_latex, latex_to_text
from app.services.ingest.pdf import extract_pdf
from app.services.ingest.structurer import structure_resume

EXTENSION_FORMATS: dict[str, SourceFormat] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".tex": "tex",
    ".zip": "zip",
    ".txt": "txt",
}

MAGIC_FORMATS: tuple[tuple[bytes, SourceFormat], ...] = (
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "docx"),
)

MAX_ZIP_ENTRY_BYTES = 2 * 1024 * 1024


@dataclass
class IngestResult:
    document: ResumeDocument
    raw_text: str


def detect_format(filename: str, content_type: str | None, data: bytes) -> SourceFormat:
    suffix = Path(filename).suffix.lower()
    if suffix in EXTENSION_FORMATS:
        return EXTENSION_FORMATS[suffix]
    for magic, source_format in MAGIC_FORMATS:
        if data.startswith(magic):
            return source_format
    if content_type:
        lowered = content_type.lower()
        if "pdf" in lowered:
            return "pdf"
        if "word" in lowered or "officedocument" in lowered:
            return "docx"
        if "latex" in lowered or "x-tex" in lowered:
            return "tex"
        if "text/plain" in lowered:
            return "txt"
    raise UnsupportedFormatError(
        "Unsupported file type. Upload a PDF, DOCX, .tex, or a .zip containing .tex files."
    )


def _decode_tex(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _ingest_zip(data: bytes) -> tuple[str, str, LatexReport, list[ParseIssue]]:
    issues: list[ParseIssue] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormatError("The uploaded zip file is corrupted.") from exc

    tex_entries: list[zipfile.ZipInfo] = []
    total = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in Path(name).parts:
            raise UnsupportedFormatError("The zip contains an unsafe file path.")
        if not name.lower().endswith((".tex", ".sty", ".cls")):
            continue
        total += info.file_size
        if info.file_size > MAX_ZIP_ENTRY_BYTES or total > MAX_ZIP_ENTRY_BYTES:
            raise UnsupportedFormatError("The zip contains LaTeX files that are too large.")
        if name.lower().endswith(".tex"):
            tex_entries.append(info)

    if not tex_entries:
        raise UnsupportedFormatError("The zip does not contain any .tex files.")

    decoded: list[tuple[str, str]] = [
        (entry.filename, _decode_tex(archive.read(entry))) for entry in tex_entries
    ]
    main_name, main_source = next(
        ((name, source) for name, source in decoded if "\\documentclass" in source),
        decoded[0],
    )
    if len(decoded) > 1:
        issues.append(
            ParseIssue(
                code="zip_includes_not_resolved",
                severity="info",
                message=(
                    f"{len(decoded)} .tex files found; analysing '{Path(main_name).name}'. "
                    "\\input/\\include resolution arrives with the sandboxed compiler."
                ),
            )
        )
    report = analyse_latex(main_source, filename=Path(main_name).name)
    return latex_to_text(main_source), main_source, report, issues


def ingest_bytes(filename: str, content_type: str | None, data: bytes) -> IngestResult:
    source_format = detect_format(filename, content_type, data)
    issues: list[ParseIssue] = []
    latex_report: LatexReport | None = None
    tex_source: str | None = None

    if source_format == "pdf":
        extraction = extract_pdf(data)
        raw_text = extraction.text
        issues.extend(extraction.issues)
    elif source_format == "docx":
        extraction = extract_docx(data)
        raw_text = extraction.text
        issues.extend(extraction.issues)
    elif source_format in {"tex", "zip"}:
        if source_format == "zip":
            raw_text, tex_source, latex_report, zip_issues = _ingest_zip(data)
            issues.extend(zip_issues)
        else:
            tex_source = _decode_tex(data)
            latex_report = analyse_latex(tex_source, filename=Path(filename).name)
            raw_text = latex_to_text(tex_source)
        if latex_report.is_hostile:
            hostile = [
                issue.message
                for issue in latex_report.issues
                if issue.security_relevant and issue.severity == "error"
            ]
            from app.core.errors import HostileLatexError

            raise HostileLatexError(hostile)
        for latex_issue in latex_report.issues:
            issues.append(
                ParseIssue(
                    code=latex_issue.code,
                    severity=latex_issue.severity,
                    message=latex_issue.message,
                    source_ref=None,
                    auto_fixable=bool(latex_issue.auto_fix),
                )
            )
    else:
        raw_text = _decode_tex(data)
        if not raw_text.strip():
            issues.append(
                ParseIssue(
                    code="empty_document",
                    severity="error",
                    message="The uploaded text file is empty.",
                )
            )

    resume, source_map, struct_issues, structuring = structure_resume(raw_text)
    issues.extend(struct_issues)

    document = ResumeDocument(
        format=source_format,
        canonical=resume,
        source_map=source_map,
        issues=issues,
        raw_text=raw_text if len(raw_text) <= 40_000 else raw_text[:40_000],
        structuring=structuring,
    )
    return IngestResult(document=document, raw_text=raw_text)


def excerpt(text: str, limit: int = 400) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "…"
