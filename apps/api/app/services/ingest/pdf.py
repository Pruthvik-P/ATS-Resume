from __future__ import annotations

import io
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.errors import UnsupportedFormatError
from app.schemas.common import ParseIssue

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
_GARBAGE_RE = re.compile(r"[\ufffd\u0000-\u0008\u000b\u000c\u000e-\u001f]")
_SPACED_LETTERS_RE = re.compile(r"\b(?:[A-Za-z]\s){4,}[A-Za-z]\b")
_PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")
_COMPARE_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.]{2,}")


@dataclass
class PdfExtraction:
    text: str
    page_count: int = 0
    extractor: str = "unknown"
    extractors: dict[str, str] = field(default_factory=dict)
    agreement: float = 1.0
    disagreements: list[str] = field(default_factory=list)
    layout: dict[str, object] = field(default_factory=dict)
    blocks: list[dict[str, object]] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)


# Backwards-compatible name used by older imports.
TextExtraction = PdfExtraction


def _clean(text: str) -> tuple[str, list[ParseIssue]]:
    issues: list[ParseIssue] = []
    ligature_hits = sum(text.count(char) for char in _LIGATURES)
    if ligature_hits:
        issues.append(
            ParseIssue(
                code="ligature_glyphs",
                severity="warning",
                message=(
                    f"{ligature_hits} ligature glyph(s) detected (ﬁ/ﬂ/ffi). "
                    "Some ATS parsers extract these as broken words."
                ),
                auto_fixable=True,
            )
        )
        for ligature, replacement in _LIGATURES.items():
            text = text.replace(ligature, replacement)
    garbage = _GARBAGE_RE.findall(text)
    if garbage:
        issues.append(
            ParseIssue(
                code="garbage_characters",
                severity="error",
                message=f"{len(garbage)} unreadable control/replacement character(s) in extracted text.",
            )
        )
        text = _GARBAGE_RE.sub(" ", text)
    private_use = _PRIVATE_USE_RE.findall(text)
    if private_use:
        issues.append(
            ParseIssue(
                code="private_use_glyphs",
                severity="warning",
                message=(
                    f"{len(private_use)} private-use glyph(s) found. These usually come from "
                    "icon fonts and extract as missing characters."
                ),
                auto_fixable=True,
            )
        )
    spaced = _SPACED_LETTERS_RE.findall(text)
    if spaced:
        issues.append(
            ParseIssue(
                code="spaced_letters",
                severity="warning",
                message="Letter-spaced text detected; ATS keyword matching will fail on it.",
            )
        )
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), issues


def _extract_pypdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - depends on file
            raise UnsupportedFormatError(
                "The PDF is password protected and cannot be read."
            ) from exc
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages), len(reader.pages)


def _extract_pymupdf(
    data: bytes,
) -> tuple[str, int, list[dict[str, object]], list[ParseIssue], int]:
    """Run PyMuPDF without letting an optional-extractor failure break parsing."""

    try:
        return _extract_pymupdf_raw(data)
    except Exception as exc:  # pragma: no cover - depends on the PDF/library
        return (
            "",
            0,
            [],
            [
                ParseIssue(
                    code="pymupdf_failed",
                    severity="info",
                    message=(
                        "PyMuPDF could not read this PDF; the pypdf result was used "
                        f"({type(exc).__name__})."
                    ),
                )
            ],
            0,
        )


def _extract_pymupdf_raw(
    data: bytes,
) -> tuple[str, int, list[dict[str, object]], list[ParseIssue], int]:
    issues: list[ParseIssue] = []
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except Exception:
        try:
            import fitz  # type: ignore[import-not-found]
        except Exception:
            return "", 0, [], issues, 0

    blocks: list[dict[str, object]] = []
    table_count = 0
    page_count = 0
    pages: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as document:
        page_count = document.page_count
        for page_index, page in enumerate(document):
            pages.append(page.get_text("text"))
            page_width = float(page.rect.width) or 1.0
            page_height = float(page.rect.height) or 1.0
            page_blocks: list[dict[str, object]] = []
            try:
                raw_blocks = page.get_text("dict").get("blocks", [])
            except Exception:  # pragma: no cover - malformed PDF
                raw_blocks = []
            for block in raw_blocks:
                if block.get("type") != 0:
                    continue
                text = " ".join(
                    "".join(span.get("text", "") for span in line.get("spans", []))
                    for line in block.get("lines", [])
                ).strip()
                if not text:
                    continue
                bbox = [float(value) for value in block.get("bbox", [0, 0, 0, 0])]
                page_blocks.append(
                    {
                        "page": page_index + 1,
                        "bbox": bbox,
                        "text": text,
                        "width": bbox[2] - bbox[0],
                        "height": bbox[3] - bbox[1],
                    }
                )
            blocks.extend(page_blocks)
            issues.extend(
                _layout_issues(
                    page=page_index + 1,
                    page_width=page_width,
                    page_height=page_height,
                    blocks=page_blocks,
                )
            )
            try:
                tables = page.find_tables()
                table_count += len(getattr(tables, "tables", []))
            except Exception:  # pragma: no cover - older PyMuPDF
                pass

    if table_count:
        issues.append(
            ParseIssue(
                code="pdf_tables",
                severity="warning",
                message=(
                    f"{table_count} table(s) detected in the compiled PDF. Tables are a "
                    "common source of flattened reading order."
                ),
            )
        )
    return "\n\n".join(pages), page_count, blocks, issues, table_count


def _layout_issues(
    *,
    page: int,
    page_width: float,
    page_height: float,
    blocks: list[dict[str, object]],
) -> list[ParseIssue]:
    issues: list[ParseIssue] = []
    if not blocks:
        return issues
    mid = page_width / 2
    left = [
        block
        for block in blocks
        if float(block["bbox"][2]) <= mid * 1.05  # type: ignore[index]
        and float(block["width"]) > page_width * 0.15  # type: ignore[arg-type]
    ]
    right = [
        block
        for block in blocks
        if float(block["bbox"][0]) >= mid * 0.95  # type: ignore[index]
        and float(block["width"]) > page_width * 0.15  # type: ignore[arg-type]
    ]
    if left and right:
        for left_block in left:
            left_top = float(left_block["bbox"][1])  # type: ignore[index]
            left_bottom = float(left_block["bbox"][3])  # type: ignore[index]
            for right_block in right:
                right_top = float(right_block["bbox"][1])  # type: ignore[index]
                right_bottom = float(right_block["bbox"][3])  # type: ignore[index]
                if min(left_bottom, right_bottom) - max(left_top, right_top) > 8:
                    issues.append(
                        ParseIssue(
                            code="pdf_multi_column",
                            severity="warning",
                            message=(
                                f"Page {page} has side-by-side text blocks. Multi-column "
                                "layouts often extract out of reading order."
                            ),
                        )
                    )
                    return issues
    sidebar = [
        block
        for block in blocks
        if float(block["width"]) < page_width * 0.34  # type: ignore[arg-type]
        and float(block["height"]) > page_height * 0.4  # type: ignore[arg-type]
    ]
    if sidebar:
        issues.append(
            ParseIssue(
                code="pdf_sidebar_layout",
                severity="warning",
                message=(
                    f"Page {page} has a tall narrow block that looks like a sidebar. "
                    "Verify contact details and section order in the extracted text."
                ),
            )
        )
    return issues


def _extract_pdftotext(data: bytes) -> str:
    binary = shutil.which("pdftotext")
    if not binary:
        return ""
    try:
        completed = subprocess.run(
            [binary, "-layout", "-", "-"],
            input=data,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.decode("utf-8", errors="replace")


def _normalise_for_compare(text: str) -> str:
    lowered = text.lower().replace("ﬁ", "fi").replace("ﬂ", "fl")
    return " ".join(_COMPARE_TOKEN_RE.findall(lowered))


def compare_extractor_texts(extractions: dict[str, str]) -> tuple[float, list[str]]:
    """Measure token agreement between independent PDF extractors."""

    usable = {
        name: set(_normalise_for_compare(text).split())
        for name, text in extractions.items()
        if text.strip()
    }
    if len(usable) < 2:
        return 1.0, []
    names = sorted(usable)
    scores: list[float] = []
    disagreements: list[str] = []
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            a, b = usable[left], usable[right]
            union = a | b
            if not union:
                continue
            scores.append(len(a & b) / len(union))
            missing_left = sorted(b - a)[:4]
            missing_right = sorted(a - b)[:4]
            if missing_left:
                disagreements.append(f"{left} lacks: {', '.join(missing_left)}")
            if missing_right:
                disagreements.append(f"{right} lacks: {', '.join(missing_right)}")
    agreement = sum(scores) / len(scores) if scores else 1.0
    return round(agreement, 3), disagreements[:8]


def _try_ocr(data: bytes) -> str:
    if not settings.ocr_enabled:
        return ""
    try:
        try:
            import pymupdf as fitz  # type: ignore[import-not-found]
        except Exception:
            import fitz  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except Exception:
        return ""
    if not shutil.which("tesseract"):
        return ""
    pages: list[str] = []
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            for page in document:
                pixmap = page.get_pixmap(dpi=200)
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                pages.append(pytesseract.image_to_string(image))
    except Exception:  # pragma: no cover - OCR environment
        return ""
    return "\n\n".join(pages)


def extract_pdf(data: bytes) -> PdfExtraction:
    issues: list[ParseIssue] = []
    text = ""
    page_count = 0
    extractor = "pypdf"
    extractors: dict[str, str] = {}

    try:
        text, page_count = _extract_pypdf(data)
        extractors["pypdf"] = text
    except UnsupportedFormatError:
        raise
    except Exception as exc:
        raise UnsupportedFormatError(f"Could not read the PDF: {exc}") from exc

    pymupdf_text, pymupdf_pages, blocks, layout_issues, _tables = _extract_pymupdf(data)
    if pymupdf_text.strip():
        extractors["pymupdf"] = pymupdf_text
        if len(pymupdf_text.strip()) > len(text.strip()):
            text = pymupdf_text
            extractor = "pymupdf"
        page_count = max(page_count, pymupdf_pages)
        issues.extend(layout_issues)

    pdftotext = _extract_pdftotext(data)
    if pdftotext.strip():
        extractors["pdftotext"] = pdftotext
        if len(pdftotext.strip()) > len(text.strip()):
            text = pdftotext
            extractor = "pdftotext"

    agreement, disagreements = compare_extractor_texts(extractors)
    if len(extractors) >= 2 and agreement < 0.85:
        issues.append(
            ParseIssue(
                code="parser_disagreement",
                severity="warning",
                message=(
                    f"Independent PDF extractors agree on only {agreement:.0%} of tokens. "
                    "Different ATS vendors may see a different document."
                ),
            )
        )

    text, clean_issues = _clean(text)
    issues.extend(clean_issues)

    letters = sum(char.isalpha() for char in text)
    if letters < 120:
        ocr_text = _try_ocr(data)
        if ocr_text.strip():
            text, ocr_issues = _clean(ocr_text)
            issues.extend(ocr_issues)
            issues.append(
                ParseIssue(
                    code="pdf_ocr_used",
                    severity="info",
                    message=(
                        "This PDF had little extractable text, so OCR was used. "
                        "Some ATS vendors do not OCR, so keep a text layer in the source."
                    ),
                )
            )
            extractor = "tesseract"
        else:
            issues.append(
                ParseIssue(
                    code="pdf_no_text_layer",
                    severity="error",
                    message=(
                        "This PDF has almost no extractable text. It is either a scanned image "
                        "or uses outlined/vector text. Enable ATS_OCR_ENABLED and install "
                        "Tesseract for fallback OCR."
                    ),
                )
            )

    layout = {
        "multi_column": any(issue.code == "pdf_multi_column" for issue in issues),
        "sidebar": any(issue.code == "pdf_sidebar_layout" for issue in issues),
        "tables": any(issue.code == "pdf_tables" for issue in issues),
        "blocks": len(blocks),
    }
    return PdfExtraction(
        text=text,
        page_count=page_count,
        extractor=extractor,
        extractors={
            name: value[:200_000] for name, value in extractors.items()
        },
        agreement=agreement,
        disagreements=disagreements,
        layout=layout,
        blocks=blocks[:500],
        issues=issues,
    )


__all__ = [
    "PdfExtraction",
    "TextExtraction",
    "compare_extractor_texts",
    "extract_pdf",
]
