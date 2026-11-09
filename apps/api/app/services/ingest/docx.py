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
    nested_table_count: int = 0
    text_box_count: int = 0
    issues: list[ParseIssue] = field(default_factory=list)


def _iter_block_items(document: Any):
    """Yield paragraphs and tables in document order."""

    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _cell_text(cell: Any) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for paragraph in cell.paragraphs:
        text = paragraph.text.strip()
        if text and text not in seen:
            seen.add(text)
            values.append(text)
    for table in cell.tables:
        for row in table.rows:
            row_values = [value.strip() for value in row.cells if value.text.strip()]
            if row_values:
                joined = " | ".join(row_values)
                if joined not in seen:
                    seen.add(joined)
                    values.append(joined)
    return " ".join(values)


def _extract_text_boxes(document: Any) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for element in document.element.iter():
        if not element.tag.endswith("}txbxContent"):
            continue
        parts = [
            node.text.strip()
            for node in element.iter()
            if node.tag.endswith("}t") and node.text and node.text.strip()
        ]
        text = " ".join(parts)
        if text and text not in seen:
            seen.add(text)
            values.append(text)
    return values


def _extract_header_footer_lines(document: Any) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for section in document.sections:
        containers = [
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ]
        for container in containers:
            for paragraph in container.paragraphs:
                text = paragraph.text.strip()
                if text and text not in seen:
                    seen.add(text)
                    lines.append(text)
    return lines


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
    nested_tables = 0

    header_footer = _extract_header_footer_lines(document)
    if header_footer:
        lines.extend(header_footer)

    for block in _iter_block_items(document):
        if hasattr(block, "rows"):
            tables += 1
            nested_tables += sum(len(cell.tables) for row in block.rows for cell in row.cells)
            row_lines: list[str] = []
            for row in block.rows:
                cells: list[str] = []
                for cell in row.cells:
                    text = _cell_text(cell).strip()
                    if text and (not cells or cells[-1] != text):
                        cells.append(text)
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

    text_boxes = _extract_text_boxes(document)
    if text_boxes:
        lines.extend(text_boxes)

    if text_boxes:
        issues.append(
            ParseIssue(
                code="docx_text_boxes",
                severity="warning",
                message=(
                    f"{len(text_boxes)} text box(es) were detected. Many ATS parsers skip "
                    "text inside text boxes, so verify contact details are not placed there."
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
    if nested_tables:
        issues.append(
            ParseIssue(
                code="docx_nested_tables",
                severity="warning",
                message=(
                    f"{nested_tables} nested table(s) detected. Nested tables are especially "
                    "likely to extract in the wrong order."
                ),
            )
        )
    if header_footer:
        issues.append(
            ParseIssue(
                code="docx_headers_footers",
                severity="warning",
                message=(
                    "Header/footer text was found. Some ATS vendors ignore headers and footers, "
                    "so keep the name and contact details in the body."
                ),
            )
        )

    return DocxExtraction(
        text="\n".join(lines).strip(),
        paragraph_count=paragraphs,
        table_count=tables,
        nested_table_count=nested_tables,
        text_box_count=len(text_boxes),
        issues=issues,
    )
