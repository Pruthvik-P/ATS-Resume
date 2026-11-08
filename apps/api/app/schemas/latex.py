from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LatexIssueCode = Literal[
    "shell_escape",
    "write18",
    "absolute_input",
    "path_traversal",
    "openout",
    "immediate_write",
    "direct_lua",
    "minted",
    "fontawesome",
    "icon_font",
    "tabular_layout",
    "multi_column",
    "graphics_text",
    "missing_glyphtounicode",
    "missing_fontenc",
    "letter_spacing",
    "unknown_macro",
    "extra_blank_lines",
]


class LatexIssue(BaseModel):
    code: LatexIssueCode
    severity: Literal["info", "warning", "error"]
    message: str
    line: int | None = None
    evidence: str | None = None
    auto_fix: str | None = None
    security_relevant: bool = False


class LatexReport(BaseModel):
    main_file: str = "resume.tex"
    document_class: str | None = None
    packages: list[str] = Field(default_factory=list)
    macros: dict[str, int] = Field(default_factory=dict)
    issues: list[LatexIssue] = Field(default_factory=list)
    uses_shell_escape: bool = False
    is_hostile: bool = False
    ats_risk_score: float = Field(default=100.0, ge=0.0, le=100.0)
    suggested_preamble: list[str] = Field(default_factory=list)


class LatexParseResult(BaseModel):
    text: str
    report: LatexReport
