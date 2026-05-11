"""JSONL serialization for `CrystalStructureRecord`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from fiir_crystal.structures.records import CrystalStructureRecord


def read_jsonl(path: str | Path) -> list[CrystalStructureRecord]:
    """Read normalized structure records from JSONL."""

    records: list[CrystalStructureRecord] = []
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"{source}:{line_no}: JSONL row must be an object")
            records.append(CrystalStructureRecord.from_dict(data))
    return records


def write_jsonl(path: str | Path, records: Iterable[CrystalStructureRecord]) -> None:
    """Write normalized structure records to JSONL."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
