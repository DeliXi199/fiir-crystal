"""Small standard-library JSON and JSONL utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from fiir_crystal.failure import StructureLike


class JsonlFormatError(ValueError):
    """Raised when a JSONL file contains an invalid line."""


def _to_jsonable(item: Any) -> Any:
    if hasattr(item, "to_dict"):
        return _to_jsonable(item.to_dict())
    if isinstance(item, dict):
        return {key: _to_jsonable(value) for key, value in item.items()}
    if isinstance(item, (list, tuple)):
        return [_to_jsonable(value) for value in item]
    return item


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL file as a list of dictionaries."""

    rows: list[dict[str, Any]] = []
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise JsonlFormatError(f"{source}:{line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(item, dict):
                raise JsonlFormatError(f"{source}:{line_no}: JSONL row must be an object")
            rows.append(item)
    return rows


def write_jsonl(path: str | Path, items: Iterable[Any]) -> None:
    """Write JSONL rows."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(_to_jsonable(item), sort_keys=True) + "\n")


def read_json(path: str | Path) -> Any:
    """Read a JSON file."""

    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, item: Any) -> None:
    """Write a JSON file."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(_to_jsonable(item), handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_mock_candidates_jsonl(path: str | Path) -> list[StructureLike]:
    """Read mock or normalized structure candidates into `StructureLike` records."""

    structures: list[StructureLike] = []
    for row in read_jsonl(path):
        if _looks_like_structure_record(row):
            from fiir_crystal.structures import CrystalStructureRecord

            structures.append(CrystalStructureRecord.from_dict(row).to_structure_like())
        else:
            structures.append(StructureLike.from_dict(row))
    return structures


def _looks_like_structure_record(row: dict[str, Any]) -> bool:
    return "species" in row and "lattice_matrix" in row and "source" in row
