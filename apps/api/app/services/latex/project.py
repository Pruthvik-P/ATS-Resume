"""LaTeX project loading, include resolution, and source utilities."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.schemas.common import ParseIssue
from app.services.ingest.latex import strip_comments

MAX_PROJECT_BYTES = 20 * 1024 * 1024
MAX_PROJECT_FILES = 200
MAX_PROJECT_FILE_BYTES = 8 * 1024 * 1024
MAX_RESOLVED_CHARS = 2_000_000
MAX_INCLUDE_DEPTH = 24

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

# TeX Live ships these; a missing local file is not a user error.
_SYSTEM_INPUTS = {
    "glyphtounicode",
    "glyphtounicode.tex",
    "pdftex.def",
    "lmodern.sty",
    "fontenc.sty",
    "inputenc.sty",
    "hyperref.sty",
}

_INPUT_RE = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}")


@dataclass
class TexProject:
    main_file: str
    files: dict[str, bytes]
    issues: list[ParseIssue] = field(default_factory=list)

    @property
    def main_bytes(self) -> bytes:
        return self.files[self.main_file]

    def read_text(self, name: str) -> str:
        return decode_tex(self.files[name])


def decode_tex(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _safe_zip_name(name: str) -> str | None:
    normalised = name.replace("\\", "/").strip()
    if not normalised or normalised.startswith("/"):
        return None
    path = PurePosixPath(normalised)
    if path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        return None
    if path.parts and path.parts[0] == "__MACOSX":
        return None
    if path.suffix.lower() not in _ALLOWED_SUFFIXES:
        return None
    return path.as_posix()


def _pick_main(names: list[str], sources: dict[str, str]) -> str | None:
    candidates = [name for name in names if "\\documentclass" in sources[name]]
    if not candidates:
        candidates = [name for name in names if name.lower().endswith(".tex")]
    if not candidates:
        return None

    def rank(name: str) -> tuple[int, int, str]:
        basename = PurePosixPath(name).name.lower()
        preferred = 0 if basename in {"main.tex", "resume.tex", "cv.tex"} else 1
        return preferred, len(PurePosixPath(name).parts), name

    return sorted(candidates, key=rank)[0]


def load_tex_project(filename: str, data: bytes) -> TexProject | None:
    """Load a single ``.tex`` file or a zip of LaTeX sources.

    Returns ``None`` when the upload is not LaTeX. Zip entries are validated
    before reading so absolute paths, traversal, and oversized archives never
    reach the compiler.
    """

    suffix = Path(filename).suffix.lower()
    if suffix not in {".tex", ".zip"} and not data.startswith(b"PK\x03\x04"):
        return None

    is_zip = zipfile.is_zipfile(io.BytesIO(data))
    if suffix == ".tex" and not is_zip:
        if len(data) > MAX_PROJECT_BYTES:
            raise ValueError("LaTeX source is too large.")
        name = PurePosixPath(filename.replace("\\", "/")).name or "resume.tex"
        return TexProject(main_file=name, files={name: data})
    if not is_zip:
        raise ValueError("The uploaded zip file is corrupted.")

    issues: list[ParseIssue] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded zip file is corrupted.") from exc

    files: dict[str, bytes] = {}
    total = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        safe = _safe_zip_name(info.filename)
        if safe is None:
            continue
        if info.file_size > MAX_PROJECT_FILE_BYTES:
            issues.append(
                ParseIssue(
                    code="zip_asset_too_large",
                    severity="warning",
                    message=f"Ignored oversized zip entry '{Path(safe).name}'.",
                )
            )
            continue
        total += info.file_size
        if total > MAX_PROJECT_BYTES or len(files) >= MAX_PROJECT_FILES:
            raise ValueError("The zip contains too much LaTeX content.")
        try:
            files[safe] = archive.read(info)
        except (RuntimeError, zipfile.BadZipFile) as exc:
            raise ValueError("The zip contains an encrypted or corrupt entry.") from exc

    tex_names = [name for name in files if name.lower().endswith(".tex")]
    if not tex_names:
        raise ValueError("The zip does not contain any .tex files.")

    sources = {
        name: decode_tex(files[name]) for name in tex_names
    }
    main_file = _pick_main(tex_names, sources)
    if main_file is None:
        raise ValueError("No main .tex file was found in the zip.")

    if len(tex_names) > 1:
        issues.append(
            ParseIssue(
                code="zip_multi_file",
                severity="info",
                message=(
                    f"{len(tex_names)} .tex files found; using '{main_file}' as the main "
                    "document and resolving \\input/\\include references."
                ),
            )
        )
    return TexProject(main_file=main_file, files=files, issues=issues)


def _resolve_path(current_file: str, target: str) -> str | None:
    raw = target.strip().strip('"').replace("\\", "/")
    if not raw or raw.startswith("/") or ":" in raw:
        return None
    path = PurePosixPath(raw)
    if ".." in path.parts:
        return None
    parent = PurePosixPath(current_file).parent
    candidate = (parent / path).as_posix()
    if candidate.startswith("./"):
        candidate = candidate[2:]
    return candidate


def resolve_project_source(project: TexProject) -> tuple[str, list[ParseIssue]]:
    """Expand ``\\input``/``\\include`` recursively for static analysis.

    The returned source is a flattened view used by the heuristic structurer and
    static guardrails. The original project files are kept intact for the
    sandboxed compiler.
    """

    issues: list[ParseIssue] = []
    seen_issues: set[str] = set()

    def issue(code: str, message: str) -> None:
        key = f"{code}:{message}"
        if key in seen_issues:
            return
        seen_issues.add(key)
        issues.append(
            ParseIssue(code=code, severity="info", message=message)
        )

    def expand(name: str, stack: tuple[str, ...], depth: int) -> str:
        if depth > MAX_INCLUDE_DEPTH:
            issue("input_too_deep", "LaTeX include nesting is too deep; stopped expanding.")
            return ""
        if name in stack:
            issue("input_cycle", f"Circular LaTeX include detected for '{name}'.")
            return ""
        if name not in project.files:
            issue("missing_include", f"Referenced LaTeX file '{name}' is not in the upload.")
            return ""
        source = strip_comments(project.read_text(name))
        if len(source) > MAX_RESOLVED_CHARS:
            issue("include_too_large", f"LaTeX file '{name}' is too large to expand.")
            return source[:MAX_RESOLVED_CHARS]

        def replace(match: re.Match[str]) -> str:
            target = match.group(1)
            resolved = _resolve_path(name, target)
            if resolved is None:
                issue(
                    "unsafe_input",
                    f"Refused unsafe LaTeX include path '{target}'.",
                )
                return match.group(0)
            candidates = [resolved]
            if not resolved.lower().endswith(".tex"):
                candidates.append(resolved + ".tex")
            for candidate in candidates:
                if candidate in project.files:
                    return expand(candidate, stack + (name,), depth + 1)
            if target.strip().lower() in _SYSTEM_INPUTS:
                return match.group(0)
            issue(
                "unresolved_input",
                f"LaTeX input '{target}' could not be resolved from the upload.",
            )
            return match.group(0)

        return _INPUT_RE.sub(replace, source)

    source = expand(project.main_file, (), 0)
    return source, issues


__all__ = [
    "MAX_PROJECT_BYTES",
    "TexProject",
    "decode_tex",
    "load_tex_project",
    "resolve_project_source",
]
