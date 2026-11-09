"""Compile LaTeX in a sandboxed worker with optional local fallbacks.

The production path is an out-of-process worker (HTTP or a one-shot Docker
container) with no network, a read-only root filesystem, dropped capabilities,
and CPU/memory/PID limits. Local TeX binaries are only used in development and
tests, because they are not a security boundary.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import ParseIssue
from app.services.ingest.latex import analyse_latex
from app.services.latex.project import TexProject, resolve_project_source

logger = get_logger(__name__)

CompileStatus = Literal[
    "compiled",
    "disabled",
    "unavailable",
    "failed",
    "timeout",
    "rejected",
]

MAX_LOG_CHARS = 20_000

_DOCKER_UNAVAILABLE_MARKERS = (
    "cannot connect to the docker daemon",
    "error during connect",
    "is the docker daemon running",
    "unable to find image",
    "pull access denied",
    "no such image",
    "permission denied while trying to connect",
)


@dataclass
class CompileResult:
    status: CompileStatus
    engine: str = "none"
    pdf: bytes | None = None
    log: str = ""
    reason: str | None = None
    duration_ms: int = 0
    synctex: bytes | None = None
    issues: list[ParseIssue] = field(default_factory=list)

    @property
    def compiled(self) -> bool:
        return self.status == "compiled" and bool(self.pdf)


def _tar_project(project: TexProject) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in project.files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _safe_extract(data: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if not data:
        return files
    limit = settings.latex_max_output_bytes
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or member.size > limit:
                    continue
                name = member.name.replace("\\", "/")
                if name.startswith("/") or ".." in PurePosixPath(name).parts:
                    continue
                extracted = archive.extractfile(member)
                if extracted is not None:
                    files[name] = extracted.read(limit)
    except (tarfile.TarError, OSError):
        return {}
    return files


def _normalise_output(files: dict[str, bytes]) -> tuple[bytes | None, str, bytes | None]:
    pdf = next(
        (data for name, data in files.items() if name.lower().endswith(".pdf")),
        None,
    )
    log = next(
        (
            data.decode("utf-8", errors="replace")
            for name, data in files.items()
            if name.lower().endswith(".log")
        ),
        "",
    )
    synctex = next(
        (
            data
            for name, data in files.items()
            if name.lower().endswith((".synctex.gz", ".synctex"))
        ),
        None,
    )
    return pdf, log[:MAX_LOG_CHARS], synctex


def _result_from_archive(
    *, data: bytes, engine: str, elapsed_ms: int, stderr: str = ""
) -> CompileResult:
    files = _safe_extract(data)
    pdf, log, synctex = _normalise_output(files)
    if pdf:
        return CompileResult(
            status="compiled",
            engine=engine,
            pdf=pdf,
            log=log,
            duration_ms=elapsed_ms,
            synctex=synctex,
        )
    combined = (log + "\n" + stderr.strip()).strip()
    reason = "The LaTeX worker did not produce a PDF."
    if combined:
        reason = f"{reason} {combined[:600]}"
    return CompileResult(
        status="failed",
        engine=engine,
        log=combined[:MAX_LOG_CHARS],
        reason=reason,
        duration_ms=elapsed_ms,
    )


def _archive_reason(data: bytes, fallback: str) -> str:
    files = _safe_extract(data)
    log = next(
        (
            value.decode("utf-8", errors="replace")
            for name, value in files.items()
            if name.lower().endswith(".log")
        ),
        "",
    )
    return (log.strip() or fallback)[:MAX_LOG_CHARS]


def _compile_http(project: TexProject) -> CompileResult:
    import httpx

    started = time.monotonic()
    archive = _tar_project(project)
    url = f"{settings.latex_worker_url.rstrip('/')}/compile"
    try:
        with httpx.Client(timeout=settings.latex_compile_timeout_seconds + 10) as client:
            response = client.post(
                url,
                params={"main": project.main_file},
                content=archive,
                headers={"content-type": "application/gzip"},
            )
    except Exception as exc:  # pragma: no cover - network/environment
        logger.warning("LaTeX worker request failed", exc_info=exc)
        return CompileResult(
            status="unavailable",
            engine="worker",
            reason=f"LaTeX worker is unreachable: {exc}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    elapsed = int((time.monotonic() - started) * 1000)
    if response.status_code == 503:
        return CompileResult(
            status="unavailable",
            engine="worker",
            reason=_archive_reason(
                response.content, "The LaTeX worker has no TeX engine installed."
            ),
            duration_ms=elapsed,
        )
    if response.status_code == 504:
        return CompileResult(
            status="timeout",
            engine="worker",
            reason=_archive_reason(
                response.content, "LaTeX compilation exceeded the worker limit."
            ),
            duration_ms=elapsed,
        )
    if response.status_code not in {200, 400, 422, 500}:
        return CompileResult(
            status="failed",
            engine="worker",
            reason=f"LaTeX worker returned HTTP {response.status_code}.",
            log=response.text[:MAX_LOG_CHARS],
            duration_ms=elapsed,
        )
    return _result_from_archive(
        data=response.content,
        engine="worker",
        elapsed_ms=elapsed,
        stderr=response.text if not response.content else "",
    )


def _compile_docker(project: TexProject) -> CompileResult:
    started = time.monotonic()
    archive = _tar_project(project)
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--pids-limit",
        "128",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        settings.latex_worker_image,
        "compile",
        "-",
        project.main_file,
    ]
    try:
        completed = subprocess.run(
            command,
            input=archive,
            capture_output=True,
            timeout=settings.latex_compile_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(
            status="timeout",
            engine="docker",
            reason="LaTeX compilation exceeded the time limit.",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except OSError as exc:
        return CompileResult(
            status="unavailable",
            engine="docker",
            reason=f"Docker is not available: {exc}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    elapsed = int((time.monotonic() - started) * 1000)
    stderr_text = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0 and not completed.stdout:
        lowered = stderr_text.lower()
        if any(marker in lowered for marker in _DOCKER_UNAVAILABLE_MARKERS):
            return CompileResult(
                status="unavailable",
                engine="docker",
                reason=f"Docker worker unavailable: {stderr_text.strip()[:600]}",
                log=stderr_text[:MAX_LOG_CHARS],
                duration_ms=elapsed,
            )
    return _result_from_archive(
        data=completed.stdout,
        engine="docker",
        elapsed_ms=elapsed,
        stderr=stderr_text,
    )


def _find_local_engine() -> str | None:
    for name in ("tectonic", "latexmk", "pdflatex"):
        if shutil.which(name):
            return name
    return None


def _compile_local(project: TexProject) -> CompileResult:
    engine = _find_local_engine()
    if engine is None:
        return CompileResult(
            status="unavailable",
            engine="local",
            reason="No local LaTeX engine found (tectonic, latexmk, or pdflatex).",
        )

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ats-latex-") as raw_dir:
        work = Path(raw_dir)
        out = work / "out"
        out.mkdir()
        for name, data in project.files.items():
            target = work / Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        main = work / Path(project.main_file)
        env = {
            **os.environ,
            "HOME": str(work),
            "TEXMFOUTPUT": str(out),
            "openin_any": "p",
            "openout_any": "p",
            "shell_escape": "f",
        }
        if engine == "tectonic":
            command = [
                engine,
                "-X",
                "compile",
                str(main),
                "--outdir",
                str(out),
                "--keep-logs",
                "--synctex",
            ]
        elif engine == "latexmk":
            command = [
                engine,
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-synctex=1",
                f"-outdir={out}",
                str(main),
            ]
        else:
            command = [
                engine,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                "-synctex=1",
                f"-output-directory={out}",
                str(main),
            ]

        runs = 1 if engine in {"tectonic", "latexmk"} else 2
        log = ""
        try:
            for _ in range(runs):
                completed = subprocess.run(
                    command,
                    cwd=work,
                    env=env,
                    capture_output=True,
                    timeout=settings.latex_compile_timeout_seconds,
                    check=False,
                )
                log += completed.stdout.decode("utf-8", errors="replace")
                log += completed.stderr.decode("utf-8", errors="replace")
                if completed.returncode != 0:
                    break
        except subprocess.TimeoutExpired:
            return CompileResult(
                status="timeout",
                engine=engine,
                reason="Local LaTeX compilation exceeded the time limit.",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except OSError as exc:
            return CompileResult(
                status="unavailable",
                engine=engine,
                reason=f"Could not run {engine}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        stem = Path(project.main_file).stem
        files: dict[str, bytes] = {}
        for suffix in (".pdf", ".log", ".synctex.gz"):
            candidate = out / f"{stem}{suffix}"
            if candidate.is_file():
                files[f"main{suffix}"] = candidate.read_bytes()
        if not files:
            workload = out if out.exists() else work
            for candidate in workload.glob("*"):
                if candidate.is_file() and candidate.suffix in {".pdf", ".log", ".synctex", ".gz"}:
                    files[f"main{candidate.suffix}"] = candidate.read_bytes()
        return _result_from_archive(
            data=_tar_to_bytes(files),
            engine=engine,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            stderr=log,
        )


def _tar_to_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def compile_project(project: TexProject) -> CompileResult:
    """Compile a project using the configured sandboxed engine."""

    if not settings.latex_compile_enabled:
        return CompileResult(status="disabled", reason="LaTeX compilation is disabled.")

    resolved, _ = resolve_project_source(project)
    report = analyse_latex(resolved, filename=project.main_file)
    if report.is_hostile:
        return CompileResult(
            status="rejected",
            reason="The LaTeX source contains a blocked security construct.",
            issues=report.issues,
        )

    if settings.latex_worker_url:
        result = _compile_http(project)
        if result.status != "unavailable":
            return result
        logger.warning("LaTeX worker unavailable; trying the next engine")

    mode = settings.latex_compile_engine
    if mode in {"auto", "docker"} and shutil.which("docker"):
        result = _compile_docker(project)
        if result.status != "unavailable":
            return result
        logger.warning("Docker LaTeX worker unavailable; trying the next engine")

    if mode in {"auto", "local"} and settings.environment in {"local", "test"}:
        return _compile_local(project)

    return CompileResult(
        status="unavailable",
        engine="none",
        reason="No LaTeX worker is configured. Set ATS_LATEX_WORKER_URL or build the worker image.",
    )


def compile_source(source: str, filename: str = "resume.tex") -> CompileResult:
    return compile_project(
        TexProject(
            main_file=filename,
            files={filename: source.encode("utf-8")},
        )
    )


__all__ = [
    "CompileResult",
    "CompileStatus",
    "compile_project",
    "compile_source",
]
