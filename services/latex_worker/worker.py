#!/usr/bin/env python3
"""Standalone LaTeX compile worker.

The worker has no third-party dependencies so the image stays small and the
compile surface stays auditable. It runs in two modes:

* ``serve`` (default): a stdlib HTTP server exposing ``GET /health`` and
  ``POST /compile?main=<file>``. The request body is a gzip-compressed tar of the
  LaTeX project; the response is a gzip-compressed tar of ``main.pdf``,
  ``main.log`` and, when produced, ``main.synctex.gz``.
* ``compile - <main>``: one-shot stdin/stdout mode used by the API's Docker
  fallback (``docker run -i ... compile - resume.tex``).

The container is expected to run read-only with a tmpfs ``/tmp``, no network,
dropped capabilities, and CPU/memory/PID limits. This process additionally:

* rejects absolute paths, ``..`` traversal, oversized archives, and too many
  files before touching disk;
* refuses obvious shell-escape / file-write constructs even though the API
  performs the same static check;
* runs TeX with ``shell_escape=f`` and ``openin_any=p`` / ``openout_any=p``;
* enforces a wall-clock timeout and output-size cap.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("WORKER_PORT", "8099"))
TIMEOUT_SECONDS = float(os.environ.get("WORKER_TIMEOUT_SECONDS", "45"))
MAX_INPUT_BYTES = int(os.environ.get("WORKER_MAX_INPUT_BYTES", str(25 * 1024 * 1024)))
MAX_FILE_BYTES = int(os.environ.get("WORKER_MAX_FILE_BYTES", str(8 * 1024 * 1024)))
MAX_FILES = int(os.environ.get("WORKER_MAX_FILES", "300"))
MAX_OUTPUT_BYTES = int(os.environ.get("WORKER_MAX_OUTPUT_BYTES", str(20 * 1024 * 1024)))
MAX_LOG_CHARS = 20_000

_ALLOWED_SUFFIXES = {
    ".tex",
    ".sty",
    ".cls",
    ".bib",
    ".bst",
    ".cfg",
    ".def",
    ".clo",
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".eps",
    ".svg",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".txt",
    ".csv",
    ".dat",
}

_FORBIDDEN = (
    ("write18", re.compile(r"\\write18")),
    ("shell_escape", re.compile(r"\\usepackage(?:\[[^\]]*\])?\{shellesc\}")),
    ("immediate_write", re.compile(r"\\immediate\s*\\write")),
    ("openout", re.compile(r"\\openout")),
    ("direct_lua", re.compile(r"\\directlua")),
    ("pipe_input", re.compile(r"\\input\s*\|")),
    ("path_traversal", re.compile(r"\\(?:input|include|openin)\s*\{[^}]*\.\.[^}]*\}")),
)


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _safe_name(name: str) -> str | None:
    normalised = name.replace("\\", "/").strip()
    if not normalised or normalised.startswith("/"):
        return None
    parts = normalised.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    if Path(normalised).suffix.lower() not in _ALLOWED_SUFFIXES:
        return None
    return normalised


def _extract_project(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("The uploaded LaTeX project is too large.")
    files: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                name = _safe_name(member.name)
                if name is None:
                    continue
                if member.size > MAX_FILE_BYTES:
                    continue
                total += member.size
                if total > MAX_INPUT_BYTES or len(files) >= MAX_FILES:
                    raise ValueError("The uploaded LaTeX project has too many files.")
                extracted = archive.extractfile(member)
                if extracted is not None:
                    files[name] = extracted.read(MAX_FILE_BYTES)
    except tarfile.TarError as exc:
        raise ValueError("The LaTeX project archive is corrupt.") from exc
    if not files:
        raise ValueError("The LaTeX project archive is empty.")
    return files


def _hostile(name: str, data: bytes) -> str | None:
    if not name.lower().endswith((".tex", ".sty", ".cls", ".def", ".cfg", ".clo")):
        return None
    text = data.decode("utf-8", errors="replace")
    for label, pattern in _FORBIDDEN:
        if pattern.search(text):
            return label
    return None


def _tar_outputs(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _engine() -> str | None:
    for name in ("latexmk", "tectonic", "pdflatex"):
        if shutil.which(name):
            return name
    return None


def _command(engine: str, main_file: str, out_name: str) -> list[str]:
    if engine == "latexmk":
        return [
            engine,
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-synctex=1",
            f"-outdir={out_name}",
            main_file,
        ]
    if engine == "tectonic":
        return [
            engine,
            "-X",
            "compile",
            main_file,
            "--outdir",
            out_name,
            "--keep-logs",
            "--synctex",
        ]
    return [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        "-synctex=1",
        f"-output-directory={out_name}",
        main_file,
    ]


def compile_archive(data: bytes, main_file: str) -> tuple[int, bytes]:
    """Compile a tar archive and return ``(http_status, output_tar_gz)``."""

    try:
        files = _extract_project(data)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, _tar_outputs({"main.log": str(exc).encode()})

    for name, content in files.items():
        label = _hostile(name, content)
        if label:
            message = f"Rejected LaTeX project: blocked construct '{label}' in '{name}'."
            _log(message)
            return HTTPStatus.UNPROCESSABLE_ENTITY, _tar_outputs(
                {"main.log": message.encode()}
            )

    if main_file not in files or not main_file.lower().endswith(".tex"):
        message = f"Unknown main file '{main_file}'."
        return HTTPStatus.BAD_REQUEST, _tar_outputs({"main.log": message.encode()})

    engine = _engine()
    if engine is None:
        message = "No LaTeX engine is installed in the worker image."
        return HTTPStatus.SERVICE_UNAVAILABLE, _tar_outputs(
            {"main.log": message.encode()}
        )

    with tempfile.TemporaryDirectory(prefix="latex-worker-") as raw_dir:
        work = Path(raw_dir)
        out = work / "out"
        out.mkdir()
        for name, content in files.items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        main = work / main_file
        if not main.is_file():  # pragma: no cover - guarded above
            return HTTPStatus.BAD_REQUEST, _tar_outputs(
                {"main.log": f"Main file '{main_file}' was not extracted.".encode()}
            )
        env = {
            **os.environ,
            "HOME": str(work),
            "TEXMFVAR": os.environ.get("TEXMFVAR", "/tmp/texmf-var"),
            "openin_any": "p",
            "openout_any": "p",
            "shell_escape": "f",
            "SOURCE_DATE_EPOCH": "0",
        }
        log = ""
        try:
            completed = subprocess.run(
                _command(engine, main_file, out.name),
                cwd=work,
                env=env,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
            log += completed.stdout.decode("utf-8", errors="replace")
            log += completed.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return HTTPStatus.GATEWAY_TIMEOUT, _tar_outputs(
                {
                    "main.log": (
                        f"Compilation exceeded the {TIMEOUT_SECONDS:.0f}s worker limit."
                        + log[-MAX_LOG_CHARS:]
                    ).encode()
                }
            )
        except OSError as exc:
            return HTTPStatus.SERVICE_UNAVAILABLE, _tar_outputs(
                {"main.log": f"Could not run {engine}: {exc}".encode()}
            )

        outputs: dict[str, bytes] = {}
        stem = Path(main_file).stem
        for suffix in (".pdf", ".log", ".synctex.gz"):
            candidate = out / f"{stem}{suffix}"
            if candidate.is_file() and candidate.stat().st_size <= MAX_OUTPUT_BYTES:
                outputs[f"main{suffix}"] = candidate.read_bytes()
        if "main.log" not in outputs:
            outputs["main.log"] = log[-MAX_LOG_CHARS:].encode("utf-8", errors="replace")
        status = (
            HTTPStatus.OK
            if "main.pdf" in outputs
            else HTTPStatus.UNPROCESSABLE_ENTITY
        )
        return status, _tar_outputs(outputs)


class Handler(BaseHTTPRequestHandler):
    server_version = "ats-latex-worker/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        _log(f"{self.address_string()} - {format % args}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if urlparse(self.path).path != "/health":
            self._send(HTTPStatus.NOT_FOUND, b'{"error":"not_found"}', "application/json")
            return
        body = json.dumps(
            {"status": "ok", "engine": _engine(), "timeout_seconds": TIMEOUT_SECONDS}
        ).encode()
        self._send(HTTPStatus.OK, body, "application/json")

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        if parsed.path != "/compile":
            self._send(HTTPStatus.NOT_FOUND, b'{"error":"not_found"}', "application/json")
            return
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_INPUT_BYTES:
            self._send(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                b'{"error":"invalid_size"}',
                "application/json",
            )
            return
        data = self.rfile.read(length)
        main_file = parse_qs(parsed.query).get("main", ["resume.tex"])[0]
        try:
            status, output = compile_archive(data, main_file)
        except Exception as exc:  # pragma: no cover - defensive
            _log(f"unhandled compile error: {exc}")
            status, output = HTTPStatus.INTERNAL_SERVER_ERROR, _tar_outputs(
                {"main.log": f"Internal worker error: {exc}".encode()}
            )
        self._send(status, output, "application/gzip")


def serve() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    _log(f"latex worker listening on :{PORT} (engine={_engine()})")
    server.serve_forever()


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "serve"
    if mode == "serve":
        serve()
        return 0
    if mode == "compile":
        if len(argv) < 3:
            _log("usage: worker.py compile - <main.tex>")
            return 2
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        main_file = argv[3] if len(argv) > 3 else "resume.tex"
        status, output = compile_archive(data, main_file)
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return 0 if status == HTTPStatus.OK else 1
    _log(f"unknown mode '{mode}'")
    return 2


if __name__ == "__main__":
    # ThreadingHTTPServer is fine for the one-request-at-a-time compose setup.
    threading.current_thread().name = "latex-worker"
    raise SystemExit(main(sys.argv))
