"""Conservative source patching for literal LaTeX resume templates.

This is not an AST. It applies accepted before/after text edits only when the
exact original string occurs in the uploaded source. That is enough for common
literal templates such as Jake's Resume, where bullets are macro arguments.
Unmatched edits are reported instead of guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PatchResult:
    source: str
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.skipped


def patch_source(source: str, edits: list[tuple[str, str]]) -> PatchResult:
    patched = source
    applied: list[str] = []
    skipped: list[str] = []
    for before, after in edits:
        if not before.strip():
            continue
        if before in patched:
            patched = patched.replace(before, after, 1)
            applied.append(before)
        else:
            skipped.append(before)
    return PatchResult(source=patched, applied=applied, skipped=skipped)


__all__ = ["PatchResult", "patch_source"]
