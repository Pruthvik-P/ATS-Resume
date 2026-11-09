from __future__ import annotations

import importlib.util
import io
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.core.config import settings
from app.schemas.jobs import OptimiseOptions
from app.schemas.resume import Resume, ResumeDocument
from app.services import optimiser
from app.services.ingest.docx import extract_docx
from app.services.ingest.latex import apply_preamble_fixes, latex_to_text
from app.services.ingest.pdf import _layout_issues, compare_extractor_texts, extract_pdf
from app.services.ingest.pipeline import ingest_bytes
from app.services.jd_analyser import analyse_jd
from app.services.latex import compiler
from app.services.latex.compiler import CompileResult, compile_project, compile_source
from app.services.latex.project import load_tex_project, resolve_project_source
from app.services.latex.render import escape_latex, render_resume_tex
from app.services.scoring.engine import build_score_report
from tests.conftest import SAMPLE_JD, SAMPLE_TEX


def _zip(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _tar(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _load_worker():
    path = Path(__file__).resolve().parents[3] / "services" / "latex_worker" / "worker.py"
    spec = importlib.util.spec_from_file_location("ats_latex_worker", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_tar(data: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            if member.isfile():
                extracted = archive.extractfile(member)
                if extracted is not None:
                    files[member.name] = extracted.read()
    return files


def _docker_worker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", "ats-latex-worker:latest"],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _document() -> ResumeDocument:
    return ingest_bytes("jane.tex", None, SAMPLE_TEX.encode("utf-8")).document


# ---------------------------------------------------------------------------
# Zip / \input resolution
# ---------------------------------------------------------------------------


def test_zip_project_resolves_input_and_include():
    main = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\input{sections/head}\n"
        "\\include{experience}\n"
        "\\end{document}\n"
    )
    data = _zip(
        {
            "resume/main.tex": main,
            "resume/sections/head.tex": "Jane Doe\njane@example.com\n",
            "resume/experience.tex": "\\section{Experience}\nAcme Corp\n",
        }
    )

    project = load_tex_project("resume.zip", data)
    assert project is not None
    assert project.main_file == "resume/main.tex"

    source, issues = resolve_project_source(project)
    assert "Jane Doe" in source
    assert "Acme Corp" in source
    assert not [issue for issue in issues if issue.code in {"missing_include", "unresolved_input"}]


def test_zip_project_skips_traversal_and_unsupported_entries():
    data = _zip(
        {
            "main.tex": "\\documentclass{article}\\begin{document}x\\end{document}",
            "../escape.tex": "\\section{Evil}",
            "/absolute.tex": "\\section{Evil}",
            "tool.exe": b"MZ",
        }
    )
    project = load_tex_project("resume.zip", data)
    assert project is not None
    assert "main.tex" in project.files
    assert "../escape.tex" not in project.files
    assert "/absolute.tex" not in project.files
    assert "tool.exe" not in project.files


def test_zip_without_tex_is_rejected():
    data = _zip({"notes.txt": "hello"})
    with pytest.raises(ValueError):
        load_tex_project("resume.zip", data)


def test_corrupt_zip_is_rejected_not_treated_as_text():
    with pytest.raises(ValueError):
        load_tex_project("resume.zip", b"this is not a zip archive")


def test_pipeline_ingests_zip_with_resolved_source():
    data = _zip(
        {
            "main.tex": (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\input{body}\n\\end{document}\n"
            ),
            "body.tex": (
                "Jane Doe\\\njane.doe@example.com\\\n"
                "\\section{Experience}\n"
                "\\resumeSubheading{Senior Engineer}{Acme Corp}{Jan 2021}{Present}\n"
                "\\resumeItem{Built FastAPI services handling 2M requests per day.}\n"
            ),
        }
    )
    result = ingest_bytes("resume.zip", "application/zip", data)
    assert result.document.format == "zip"
    assert "Acme Corp" in result.raw_text
    fidelity = result.document.parse_fidelity
    assert fidelity["source"] == "latex"
    assert fidelity["main_file"] == "main.tex"
    assert fidelity["project_files"] == 2
    assert fidelity["compile_status"] == "disabled"


# ---------------------------------------------------------------------------
# Preamble fixes and canonical renderer
# ---------------------------------------------------------------------------


def test_preamble_fixes_are_applied_once():
    source = "\\documentclass{article}\n\\begin{document}Hi\\end{document}\n"
    result = apply_preamble_fixes(source)
    assert "\\usepackage[T1]{fontenc}" in result.source
    assert "\\input{glyphtounicode}" in result.source
    assert "\\pdfgentounicode=1" in result.source
    assert result.applied

    again = apply_preamble_fixes(result.source)
    assert again.applied == []


def test_preamble_fixes_skip_xelatex_fontspec():
    source = (
        "\\documentclass{article}\n"
        "\\usepackage{fontspec}\n"
        "\\begin{document}x\\end{document}\n"
    )
    result = apply_preamble_fixes(source)
    assert result.applied == []
    assert "glyphtounicode" not in result.source


def test_renderer_escapes_latex_and_stays_single_column():
    resume = Resume.model_validate(
        {
            "basics": {
                "name": "Jane & Co.",
                "email": "jane@example.com",
                "url": "https://example.com/jane_doe",
                "summary": "50% faster APIs with C# and C++.",
            },
            "work": [
                {
                    "name": "Acme_Inc",
                    "position": "R&D Engineer",
                    "startDate": "2021",
                    "endDate": "2023",
                    "highlights": ["Cut cost by 50% & improved #1 latency."],
                }
            ],
            "skills": [{"name": "Languages", "keywords": ["C++", "C#", "A_B"]}],
            "languages": [{"language": "English", "fluency": "Native"}],
            "awards": [{"title": "Best Engineer", "awarder": "Acme", "date": "2022"}],
        }
    )
    document = ResumeDocument(format="tex", canonical=resume)
    tex = render_resume_tex(document)

    assert "Jane \\& Co." in tex
    assert "R\\&D Engineer" in tex
    assert "Acme\\_Inc" in tex
    assert "50\\%" in tex
    assert "C\\#" in tex
    assert "\\input{glyphtounicode}" in tex
    assert "\\pdfgentounicode=1" in tex
    assert "English Native" in tex
    assert "Best Engineer" in tex
    assert "\\begin{tabular}" not in tex
    assert "\\begin{multicols}" not in tex
    assert escape_latex("{x}") == r"\{x\}"


# ---------------------------------------------------------------------------
# PDF extraction / layout comparison
# ---------------------------------------------------------------------------


def test_extractor_agreement_detects_disagreement():
    agreement, disagreements = compare_extractor_texts(
        {
            "pypdf": "python fastapi postgres kubernetes",
            "pymupdf": "python fastapi postgres kubernetes",
        }
    )
    assert agreement == 1.0
    assert disagreements == []

    agreement, disagreements = compare_extractor_texts(
        {
            "pypdf": "python fastapi postgres kubernetes",
            "pymupdf": "python java oracle weblogic mainframe",
        }
    )
    assert agreement < 0.5
    assert disagreements


def test_layout_detection_flags_side_by_side_blocks():
    blocks = [
        {"page": 1, "bbox": [40, 100, 280, 700], "width": 240, "height": 600, "text": "left"},
        {"page": 1, "bbox": [320, 100, 560, 700], "width": 240, "height": 600, "text": "right"},
    ]
    issues = _layout_issues(page=1, page_width=600, page_height=800, blocks=blocks)
    assert any(issue.code == "pdf_multi_column" for issue in issues)


def test_pdf_without_text_layer_is_reported():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)

    extraction = extract_pdf(buffer.getvalue())
    assert extraction.page_count == 1
    assert any(issue.code == "pdf_no_text_layer" for issue in extraction.issues)
    assert extraction.extractors.get("pypdf") == ""


# ---------------------------------------------------------------------------
# DOCX fidelity
# ---------------------------------------------------------------------------


def test_docx_tables_are_extracted_in_order():
    import docx

    document = docx.Document()
    document.add_paragraph("Jane Doe")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Python"
    table.cell(0, 1).text = "AWS"
    table.cell(1, 0).text = "Docker"
    table.cell(1, 1).text = "Kubernetes"
    buffer = io.BytesIO()
    document.save(buffer)

    extraction = extract_docx(buffer.getvalue())
    assert "Jane Doe" in extraction.text
    assert "Python | AWS" in extraction.text
    assert "Docker | Kubernetes" in extraction.text
    assert any(issue.code == "docx_tables" for issue in extraction.issues)


# ---------------------------------------------------------------------------
# Compile engine selection / rollback
# ---------------------------------------------------------------------------


def test_compile_disabled_returns_disabled(monkeypatch):
    monkeypatch.setattr(settings, "latex_compile_enabled", False)
    result = compile_source("\\documentclass{article}\\begin{document}x\\end{document}")
    assert result.status == "disabled"


def test_compile_rejects_hostile_source(monkeypatch):
    monkeypatch.setattr(settings, "latex_compile_enabled", True)
    result = compile_source(
        "\\documentclass{article}\\begin{document}\\write18{rm -rf /}\\end{document}"
    )
    assert result.status == "rejected"
    assert result.issues


def test_compile_unavailable_without_worker_or_engine(monkeypatch):
    monkeypatch.setattr(settings, "latex_compile_enabled", True)
    monkeypatch.setattr(settings, "latex_worker_url", None)
    monkeypatch.setattr(settings, "latex_compile_engine", "auto")
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(compiler.shutil, "which", lambda name: None)

    result = compile_source("\\documentclass{article}\\begin{document}x\\end{document}")
    assert result.status == "unavailable"


def test_compiler_project_archive_roundtrip():
    project = load_tex_project(
        "resume.tex",
        b"\\documentclass{article}\\begin{document}Hi\\end{document}",
    )
    assert project is not None
    archive = compiler._tar_project(project)
    extracted = compiler._safe_extract(archive)
    assert b"documentclass" in extracted["resume.tex"]


def test_compiler_reads_pdf_and_log_from_worker_archive():
    output = compiler._tar_to_bytes(
        {"main.pdf": b"%PDF-1.4 fake", "main.log": b"compiled cleanly"}
    )
    result = compiler._result_from_archive(data=output, engine="worker", elapsed_ms=12)
    assert result.status == "compiled"
    assert result.pdf == b"%PDF-1.4 fake"
    assert "compiled cleanly" in result.log

    missing = compiler._result_from_archive(
        data=compiler._tar_to_bytes({"main.log": b"! Undefined control sequence"}),
        engine="worker",
        elapsed_ms=13,
    )
    assert missing.status == "failed"
    assert "Undefined control sequence" in missing.reason


def test_docker_infrastructure_error_maps_to_unavailable(monkeypatch):
    project = load_tex_project(
        "resume.tex",
        b"\\documentclass{article}\\begin{document}Hi\\end{document}",
    )
    assert project is not None

    class Completed:
        returncode = 125
        stdout = b""
        stderr = b"Cannot connect to the Docker daemon at unix:///var/run/docker.sock"

    monkeypatch.setattr(compiler.subprocess, "run", lambda *args, **kwargs: Completed())
    result = compiler._compile_docker(project)
    assert result.status == "unavailable"
    assert "Docker worker unavailable" in result.reason


def test_http_worker_status_mapping(monkeypatch):
    import httpx

    project = load_tex_project(
        "resume.tex",
        b"\\documentclass{article}\\begin{document}Hi\\end{document}",
    )
    assert project is not None

    class FakeResponse:
        def __init__(self, status_code: int, log: bytes) -> None:
            self.status_code = status_code
            self.content = compiler._tar_to_bytes({"main.log": log})
            self.text = ""

    class FakeClient:
        status_code = 503
        log = b"No LaTeX engine installed"

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse(self.status_code, self.log)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(settings, "latex_worker_url", "http://worker.invalid")

    result = compiler._compile_http(project)
    assert result.status == "unavailable"
    assert "No LaTeX engine" in result.reason

    FakeClient.status_code = 504
    FakeClient.log = b"timed out"
    result = compiler._compile_http(project)
    assert result.status == "timeout"
    assert "timed out" in result.reason


def test_worker_rejects_hostile_archive_and_reports_missing_engine(monkeypatch):
    worker = _load_worker()

    hostile = worker.compile_archive(
        _tar({"resume.tex": b"\\write18{echo bad}"}), "resume.tex"
    )
    assert int(hostile[0]) == 422
    assert b"Rejected" in _read_tar(hostile[1])["main.log"]

    monkeypatch.setattr(worker, "_engine", lambda: None)
    clean = worker.compile_archive(
        _tar(
            {
                "resume.tex": (
                    b"\\documentclass{article}\\begin{document}Hi\\end{document}"
                )
            }
        ),
        "resume.tex",
    )
    assert int(clean[0]) == 503
    assert b"No LaTeX engine" in _read_tar(clean[1])["main.log"]


def test_worker_rejects_path_traversal_entries():
    worker = _load_worker()
    archive = _tar(
        {
            "resume.tex": b"\\documentclass{article}",
            "../escape.tex": b"\\section{Evil}",
        }
    )
    files = worker._extract_project(archive)
    assert "resume.tex" in files
    assert "../escape.tex" not in files
    assert "escape.tex" not in files


def test_compile_guard_blocks_failed_compile(monkeypatch):
    document = _document()
    monkeypatch.setattr(optimiser.settings, "latex_compile_enabled", True)
    monkeypatch.setattr(
        optimiser,
        "compile_source",
        lambda *args, **kwargs: CompileResult(status="failed", reason="boom"),
    )
    ok, reason = optimiser._compile_guard(document)
    assert ok is False
    assert reason == "boom"


def test_compile_guard_allows_unavailable_worker(monkeypatch):
    document = _document()
    monkeypatch.setattr(optimiser.settings, "latex_compile_enabled", True)
    monkeypatch.setattr(
        optimiser,
        "compile_source",
        lambda *args, **kwargs: CompileResult(status="unavailable"),
    )
    ok, reason = optimiser._compile_guard(document)
    assert ok is True
    assert reason is None


async def test_optimiser_rolls_back_iteration_on_compile_failure(monkeypatch):
    document = _document()
    analysis, _ = analyse_jd(SAMPLE_JD, title="Senior Backend Engineer")
    baseline = build_score_report(
        resume_id="resume-1",
        jd_id="jd-1",
        document=document,
        analysis=analysis,
    )
    monkeypatch.setattr(optimiser.settings, "latex_compile_enabled", True)
    monkeypatch.setattr(
        optimiser,
        "compile_source",
        lambda *args, **kwargs: CompileResult(status="failed", reason="missing package"),
    )

    result = await optimiser.run_optimisation(
        job_id="job-1",
        document=document,
        analysis=analysis,
        baseline=baseline,
        facts=[],
        options=OptimiseOptions(max_iterations=1, max_changes=10),
    )

    assert result.stopped_reason == "failed"
    assert result.proposals == []
    assert any("rolled back" in note for note in result.notes)


# ---------------------------------------------------------------------------
# Static parse-fidelity metadata
# ---------------------------------------------------------------------------


def test_tex_ingestion_records_parse_metadata():
    document = _document()
    assert document.parse_fidelity["source"] == "latex"
    assert document.parse_fidelity["compile_status"] == "disabled"
    assert "main_file" in document.parse_fidelity


@pytest.mark.skipif(
    not _docker_worker_ready(),
    reason="ats-latex-worker:latest is not built on this host",
)
def test_real_docker_worker_compiles_and_extracts(monkeypatch):
    monkeypatch.setattr(settings, "latex_compile_enabled", True)
    monkeypatch.setattr(settings, "latex_worker_url", None)
    monkeypatch.setattr(settings, "latex_compile_engine", "docker")
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "latex_compile_timeout_seconds", 120.0)

    tex = render_resume_tex(_document())
    project = load_tex_project("resume.tex", tex.encode("utf-8"))
    assert project is not None
    result = compile_project(project)

    assert result.compiled, f"{result.reason}\n{result.log[-2000:]}"
    assert result.engine == "docker"
    assert result.pdf and result.pdf.startswith(b"%PDF")

    extraction = extract_pdf(result.pdf)
    assert extraction.page_count >= 1
    assert "Jane Doe" in extraction.text
    assert "FastAPI" in extraction.text


@pytest.mark.skipif(
    not _docker_worker_ready(),
    reason="ats-latex-worker:latest is not built on this host",
)
def test_pipeline_uses_compiled_pdf_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "latex_compile_enabled", True)
    monkeypatch.setattr(settings, "latex_worker_url", None)
    monkeypatch.setattr(settings, "latex_compile_engine", "docker")
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "latex_compile_timeout_seconds", 120.0)

    tex = render_resume_tex(_document())
    result = ingest_bytes("resume.tex", "application/x-tex", tex.encode("utf-8"))

    fidelity = result.document.parse_fidelity
    assert fidelity["compile_status"] == "compiled"
    assert fidelity["compile_engine"] == "docker"
    assert fidelity.get("extractor") == "pypdf"
    assert fidelity.get("agreement") == 1.0
    assert "Jane Doe" in result.raw_text
    assert "FastAPI" in result.raw_text


def test_latex_macro_registry_covers_template_macros():
    source = (
        "\\begin{document}\n"
        "\\cvsection{Experience}\n"
        "\\cventry{2021}{Senior Engineer}{Acme}{}{}{Built APIs.}\n"
        "\\cvitem{Skills}{Python, AWS}\n"
        "\\resumeSubHeadingListStart\n"
        "\\resumeItem{Led a team.}\n"
        "\\resumeSubHeadingListEnd\n"
        "\\end{document}\n"
    )
    text = latex_to_text(source)
    assert "Experience" in text
    assert "Senior Engineer" in text
    assert "Skills" in text
    assert "Led a team." in text
