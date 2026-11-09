"""Load external skills taxonomy files.

Supports JSON and CSV exports shaped like ESCO, O*NET, Lightcast, or a simple
curated list. The loader normalises common column names and returns plain
records; `app.taxonomy.skills` turns them into `Skill` entries.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

_CANONICAL_KEYS = ("canonical", "name", "preferredLabel", "preferred_label", "skill", "title")
_ALIAS_KEYS = (
    "aliases",
    "altLabels",
    "alt_labels",
    "alternative_labels",
    "keywords",
)
_CATEGORY_KEYS = ("category", "skillType", "skill_type", "type", "group")
_AMBIGUOUS_KEYS = ("ambiguous", "is_ambiguous")


def _first(mapping: dict[str, Any], keys: tuple[str, ...], default: Any = "") -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    for separator in ("|", ";", "||"):
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    return [part.strip() for part in text.split(",") if part.strip()]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _normalise(record: dict[str, Any]) -> dict[str, Any] | None:
    canonical = str(_first(record, _CANONICAL_KEYS)).strip()
    if not canonical:
        return None
    aliases = [
        alias
        for alias in _as_list(_first(record, _ALIAS_KEYS))
        if alias.lower() != canonical.lower()
    ]
    return {
        "canonical": canonical,
        "aliases": aliases,
        "category": str(_first(record, _CATEGORY_KEYS, "general")).strip() or "general",
        "ambiguous": _as_bool(_first(record, _AMBIGUOUS_KEYS, False)),
    }


def load_taxonomy_records(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON/CSV taxonomy file into normalised records."""

    file_path = Path(path)
    suffix = file_path.suffix.lower()
    records: list[dict[str, Any]] = []
    if suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            raw_records = [
                json.loads(line)
                for line in file_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                raw_records = payload.get("skills") or payload.get("records") or []
            else:
                raw_records = payload
        records = [item for item in raw_records if isinstance(item, dict)]
    elif suffix == ".csv":
        with file_path.open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
    else:
        raise ValueError(f"Unsupported taxonomy format: {file_path.suffix or 'none'}")

    normalised: list[dict[str, Any]] = []
    for record in records:
        entry = _normalise(record)
        if entry is not None:
            normalised.append(entry)
    return normalised


__all__ = ["load_taxonomy_records"]
