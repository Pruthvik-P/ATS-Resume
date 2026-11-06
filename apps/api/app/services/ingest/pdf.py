from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from app.core.errors import UnsupportedFormatError
from app.schemas.common import ParseIssue

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
_GARBAGE_RE = re.compile(r"[\ufffd\u0000-\u0008\u000b\u000c\u000e-\u001f]")
_SPACED_LETTERS_RE = re.compile(r"\b(?:[A-Za-z]\s){4,}[A-Za-z]\b")
_PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")


@dataclass
class TextExtraction:
    text: str
    page_count: int = 0
    extractor: str = "unknown"
    issues: list[ParseIssue] = field(default_factory=list)


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


def extract_pdf(data: bytes) -> TextExtraction:
    issues: list[ParseIssue] = []
    text = ""
    page_count = 0
    extractor = "pypdf"

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # pragma: no cover - depends on file
                raise UnsupportedFormatError(
                    "The PDF is password protected and cannot be read."
                ) from exc
        page_count = len(reader.pages)
        pages: list[str] = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n\n".join(pages)
    except UnsupportedFormatError:
        raise
    except Exception as exc:
        raise UnsupportedFormatError(f"Could not read the PDF: {exc}") from exc

    # PyMuPDF is an optional second extractor with better layout handling.
    try:
        import fitz  # type: ignore[import-not-found]

        with fitz.open(stream=data, filetype="pdf") as document:
            alt = "\n\n".join(page.get_text("text") for page in document)
        if len(alt.strip()) > len(text.strip()):
            text = alt
            extractor = "pymupdf"
    except Exception:
        pass

    text, clean_issues = _clean(text)
    issues.extend(clean_issues)

    letters = sum(char.isalpha() for char in text)
    if letters < 120:
        issues.append(
            ParseIssue(
                code="pdf_no_text_layer",
                severity="error",
                message=(
                    "This PDF has almost no extractable text. It is either a scanned image "
                    "or uses outlined/vector text. OCR is not enabled in this build."
                ),
            )
        )
    return TextExtraction(text=text, page_count=page_count, extractor=extractor, issues=issues)
