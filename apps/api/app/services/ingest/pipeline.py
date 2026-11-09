from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import UnsupportedFormatError
from app.schemas.common import ParseIssue, SourceFormat
from app.schemas.latex import LatexReport
from app.schemas.resume import ResumeDocument
from app.services.ingest.docx import extract_docx
from app.services.ingest.latex import analyse_latex, latex_to_text
from app.services.ingest.pdf import extract_pdf
from app.services.ingest.structurer import structure_resume
from app.services.latex.compiler import CompileResult, compile_project
from app.services.latex.project import (
    TexProject,
    decode_tex,
    load_tex_project,
    resolve_project_source,
)

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


@dataclass
class IngestResult:
    document: ResumeDocument
    raw_text: str
    project: TexProject | None = None
    latex_report: LatexReport | None = None
    compile_result: CompileResult | None = None


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


def _extraction_meta(
    *,
    source: str,
    extractor: str | None = None,
    extractors: list[str] | None = None,
    agreement: float | None = None,
    disagreements: list[str] | None = None,
    layout: dict[str, object] | None = None,
    page_count: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"source": source}
    if extractor:
        meta["extractor"] = extractor
    if extractors:
        meta["extractors"] = extractors
    if agreement is not None:
        meta["agreement"] = agreement
    if disagreements:
        meta["disagreements"] = disagreements
    if layout:
        meta["layout"] = layout
    if page_count is not None:
        meta["page_count"] = page_count
    meta.update(extra)
    return meta


def _ingest_latex(
    *,
    filename: str,
    data: bytes,
    issues: list[ParseIssue],
) -> tuple[str, TexProject, LatexReport, dict[str, Any], CompileResult | None]:
    try:
        project = load_tex_project(filename, data)
    except ValueError as exc:
        raise UnsupportedFormatError(str(exc)) from exc
    if project is None:
        raise UnsupportedFormatError("No LaTeX project was found in the upload.")

    issues.extend(project.issues)
    resolved_source, resolution_issues = resolve_project_source(project)
    issues.extend(resolution_issues)

    report = analyse_latex(resolved_source, filename=project.main_file)
    if report.is_hostile:
        from app.core.errors import HostileLatexError

        hostile = [
            issue.message
            for issue in report.issues
            if issue.security_relevant and issue.severity == "error"
        ]
        raise HostileLatexError(hostile)

    for latex_issue in report.issues:
        issues.append(
            ParseIssue(
                code=latex_issue.code,
                severity=latex_issue.severity,
                message=latex_issue.message,
                source_ref=None,
                auto_fixable=bool(latex_issue.auto_fix),
            )
        )

    raw_text = latex_to_text(resolved_source)
    fidelity = _extraction_meta(
        source="latex",
        main_file=project.main_file,
        project_files=len(project.files),
        compile_status="disabled",
    )

    compile_result: CompileResult | None = None
    if settings.latex_compile_enabled:
        compile_result = compile_project(project)
        fidelity["compile_status"] = compile_result.status
        fidelity["compile_engine"] = compile_result.engine
        fidelity["compile_ms"] = compile_result.duration_ms
        if compile_result.compiled and compile_result.pdf:
            pdf_extraction = extract_pdf(compile_result.pdf)
            issues.extend(pdf_extraction.issues)
            if pdf_extraction.text.strip():
                # The compiled PDF is the authoritative ATS view.
                raw_text = pdf_extraction.text
            fidelity.update(
                {
                    "extractor": pdf_extraction.extractor,
                    "extractors": sorted(pdf_extraction.extractors),
                    "agreement": pdf_extraction.agreement,
                    "disagreements": pdf_extraction.disagreements,
                    "layout": pdf_extraction.layout,
                    "page_count": pdf_extraction.page_count,
                }
            )
        elif compile_result.status in {"failed", "timeout"}:
            issues.append(
                ParseIssue(
                    code="latex_compile_failed",
                    severity="warning",
                    message=(
                        "The sandboxed LaTeX compiler could not build this document. "
                        "Static analysis was used instead. Check the compile log in the job metadata."
                    ),
                )
            )
        elif compile_result.status == "rejected":
            issues.append(
                ParseIssue(
                    code="latex_compile_rejected",
                    severity="error",
                    message="The LaTeX compiler refused this document for security reasons.",
                )
            )
        elif compile_result.status == "unavailable":
            issues.append(
                ParseIssue(
                    code="latex_compile_unavailable",
                    severity="info",
                    message=(
                        "LaTeX compilation is enabled but no sandboxed worker is available. "
                        "Static analysis was used instead."
                    ),
                )
            )

    return raw_text, project, report, fidelity, compile_result


def ingest_bytes(filename: str, content_type: str | None, data: bytes) -> IngestResult:
    source_format = detect_format(filename, content_type, data)
    issues: list[ParseIssue] = []
    latex_report: LatexReport | None = None
    project: TexProject | None = None
    compile_result: CompileResult | None = None
    parse_fidelity: dict[str, Any] = {"source": source_format}

    if source_format == "pdf":
        extraction = extract_pdf(data)
        raw_text = extraction.text
        issues.extend(extraction.issues)
        parse_fidelity = _extraction_meta(
            source="pdf",
            extractor=extraction.extractor,
            extractors=sorted(extraction.extractors),
            agreement=extraction.agreement,
            disagreements=extraction.disagreements,
            layout=extraction.layout,
            page_count=extraction.page_count,
        )
    elif source_format == "docx":
        extraction = extract_docx(data)
        raw_text = extraction.text
        issues.extend(extraction.issues)
        parse_fidelity = _extraction_meta(
            source="docx",
            tables=extraction.table_count,
            paragraphs=extraction.paragraph_count,
            text_boxes=extraction.text_box_count,
        )
    elif source_format in {"tex", "zip"}:
        (
            raw_text,
            project,
            latex_report,
            parse_fidelity,
            compile_result,
        ) = _ingest_latex(filename=filename, data=data, issues=issues)
    else:
        raw_text = decode_tex(data)
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
        parse_fidelity=parse_fidelity,
    )
    return IngestResult(
        document=document,
        raw_text=raw_text,
        project=project,
        latex_report=latex_report,
        compile_result=compile_result,
    )


def excerpt(text: str, limit: int = 400) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "…"
