from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.errors import AppError

_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class Storage(Protocol):
    async def save(self, key: str, data: bytes) -> str: ...
    async def read(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


def _validate_key(key: str) -> Path:
    if not _SAFE_KEY_RE.match(key) or ".." in Path(key).parts:
        raise AppError("invalid_storage_key", "Invalid storage key.", status_code=400)
    return Path(key)


class LocalStorage:
    """Filesystem storage for local dev. S3/MinIO implements the same protocol."""

    name = "local"

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (base_dir or settings.storage_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        relative = _validate_key(key)
        target = (self.base_dir / relative).resolve()
        if self.base_dir not in target.parents and target != self.base_dir:
            raise AppError("invalid_storage_key", "Storage key escapes the base directory.")
        return target

    async def save(self, key: str, data: bytes) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return key

    async def read(self, key: str) -> bytes:
        target = self._path(key)
        if not target.exists():
            raise AppError("storage_missing", "Stored file was not found.", status_code=404)
        return target.read_bytes()

    async def delete(self, key: str) -> None:
        target = self._path(key)
        if target.exists():
            target.unlink()


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage
