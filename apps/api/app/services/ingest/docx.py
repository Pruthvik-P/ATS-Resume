from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import UnsupportedFormatError
from app.schemas.common import ParseIssue

_HEADING_STYLES = {"title", "heading 1", "heading 2", "heading 3", "subtitle"}


@dataclass
class DocxExtraction:
    text: str
    paragraph_count: int = 0
    table_count: int = 0
    issues: list[ParseIssue] = field(default_factory=list)


def _iter_block_items(document: Any):
    """Yield paragraphs and tables in document order."""

    from docx.document import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)
    if not isinstance(document, DocxDocument):  # pragma: no cover - defensive
        return


def extract_docx(data: bytes) -> DocxExtraction:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise UnsupportedFormatError("DOCX support is not installed.") from exc

    issues: list[ParseIssue] = []
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedFormatError(f"Could not read the DOCX file: {exc}") from exc

    lines: list[str] = []
    paragraphs = 0
    tables = 0
    textbox_text = 0

    for block in _iter_block_items(document):
        if hasattr(block, "rows"):
            tables += 1
            row_lines: list[str] = []
            for row in block.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    row_lines.append(" | ".join(cells))
            if row_lines:
                lines.extend(row_lines)
            continue

        paragraphs += 1
        text = block.text.strip()
        if not text:
            continue
        style_name = (block.style.name if block.style else "") or ""
        lowered = style_name.lower()
        if lowered in _HEADING_STYLES or "heading" in lowered:
            level = 2 if "1" not in lowered else 1
            lines.append(f"{'#' * level} {text}")
        else:
            lines.append(text)

    # Text boxes are not exposed by python-docx's paragraph API.
    try:
        xml = document.element.xml
        textbox_text = xml.count("txbxContent")
    except Exception:  # pragma: no cover - defensive
        pass
    if textbox_text:
        issues.append(
            ParseIssue(
                code="docx_text_boxes",
                severity="warning",
                message=(
                    "Text boxes were detected. Many ATS parsers skip text inside text boxes, "
                    "so verify contact details are not placed there."
                ),
                auto_fixable=True,
            )
        )
    if tables:
        issues.append(
            ParseIssue(
                code="docx_tables",
                severity="warning",
                message=(
                    f"{tables} table(s) detected. Tables often break ATS reading order; "
                    "prefer plain stacked paragraphs."
                ),
            )
        )

    return DocxExtraction(
        text="\n".join(lines).strip(),
        paragraph_count=paragraphs,
        table_count=tables,
        issues=issues,
    )
