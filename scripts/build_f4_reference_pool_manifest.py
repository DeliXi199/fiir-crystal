#!/usr/bin/env python
"""Build a local F4 reference pool manifest from structure JSONL files."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import JsonlFormatError, write_json


MANIFEST_SCHEMA_VERSION = "f4-reference-pool-manifest-v1"
DEFAULT_OUTPUT_JSON = Path("outputs/f4_novelty_audit/reference_pool_v1/reference_pool_manifest.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local F4 reference pool manifest from existing JSONL files. "
            "This does not download data, query databases, or run structure matching."
        )
    )
    parser.add_argument("--reference-source", action="append", required=True, help="Input as NAME=path/to/refs.jsonl")
    parser.add_argument("--reference-pool-id", default="reference_pool_v1")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--report")
    parser.add_argument("--reference-id-field", default="reference_id")
    parser.add_argument("--format", default="structure_jsonl")
    parser.add_argument("--allow-duplicate-reference-ids", action="store_true")
    parser.add_argument("--allow-missing-reference-ids", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    sources = [_parse_reference_source(item) for item in args.reference_source]
    names = [name for name, _ in sources]
    if len(set(names)) != len(names):
        raise SystemExit("reference source names must be unique")

    source_rows = []
    all_reference_ids: list[str] = []
    missing_reference_id_count = 0
    for name, path in sources:
        if not path.exists():
            raise SystemExit(f"reference source does not exist: {path}")
        try:
            stats = _reference_file_stats(path, args.reference_id_field)
        except JsonlFormatError as exc:
            raise SystemExit(str(exc)) from exc
        source_ids = stats["reference_ids"]
        missing_ids = stats["missing_reference_id_count"]
        if missing_ids and not args.allow_missing_reference_ids:
            raise SystemExit(f"reference source has rows without {args.reference_id_field}: {name}")
        all_reference_ids.extend(source_ids)
        missing_reference_id_count += missing_ids
        source_rows.append(
            {
                "name": name,
                "path": str(path),
                "format": args.format,
                "reference_count": stats["reference_count"],
                "sha256": _sha256(path),
                "reference_id_field": args.reference_id_field,
                "missing_reference_id_count": missing_ids,
                "duplicate_reference_id_count": len(stats["duplicate_reference_ids"]),
                "duplicate_reference_ids": stats["duplicate_reference_ids"][:50],
            }
        )

    total_reference_count = sum(row["reference_count"] for row in source_rows)
    if total_reference_count < 1 and not args.allow_empty:
        raise SystemExit("reference pool is empty")

    duplicate_reference_ids = sorted(_duplicates(all_reference_ids))
    if duplicate_reference_ids and not args.allow_duplicate_reference_ids:
        preview = ",".join(duplicate_reference_ids[:10])
        raise SystemExit(f"duplicate reference_id values found: {preview}")

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "reference_pool_id": args.reference_pool_id,
        "example_manifest": False,
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "total_reference_count": total_reference_count,
        "reference_source_count": len(source_rows),
        "reference_id_field": args.reference_id_field,
        "duplicate_reference_id_count": len(duplicate_reference_ids),
        "duplicate_reference_ids": duplicate_reference_ids[:100],
        "missing_reference_id_count": missing_reference_id_count,
        "reference_sources": source_rows,
        "local_only": True,
        "runs_structure_matcher": False,
        "runs_pymatgen": False,
        "runs_database_query": False,
        "calls_external_apis": False,
        "downloads": False,
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
    }

    output_json = Path(args.output_json)
    report_path = Path(args.report) if args.report else output_json.with_name("reference_pool_manifest_report.md")
    write_json(output_json, manifest)
    report_path.write_text(_render_report(manifest), encoding="utf-8")

    print("F4 reference pool manifest build complete")
    print(f"  reference_pool_id: {manifest['reference_pool_id']}")
    print(f"  reference_source_count: {manifest['reference_source_count']}")
    print(f"  total_reference_count: {manifest['total_reference_count']}")
    print(f"  duplicate_reference_id_count: {manifest['duplicate_reference_id_count']}")
    print(f"  missing_reference_id_count: {manifest['missing_reference_id_count']}")
    print(f"  manifest: {output_json}")
    print(f"  report: {report_path}")
    return {"summary": manifest, "files": {"manifest": str(output_json), "report": str(report_path)}}


def _parse_reference_source(item: str) -> tuple[str, Path]:
    if "=" not in item:
        raise SystemExit(f"--reference-source must be NAME=PATH, got: {item}")
    name, raw_path = item.split("=", 1)
    name = name.strip()
    if not name:
        raise SystemExit(f"empty reference source name in --reference-source: {item}")
    return name, Path(raw_path)


def _reference_file_stats(path: Path, field_name: str) -> dict[str, Any]:
    ids: list[str] = []
    missing_count = 0
    reference_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise JsonlFormatError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise JsonlFormatError(f"{path}:{line_no}: JSONL row must be an object")
            reference_count += 1
            value = row.get(field_name)
            if value in (None, ""):
                missing_count += 1
                continue
            ids.append(str(value))
    duplicate_reference_ids = sorted(_duplicates(ids))
    return {
        "reference_count": reference_count,
        "reference_ids": ids,
        "missing_reference_id_count": missing_count,
        "duplicate_reference_ids": duplicate_reference_ids,
    }


def _render_report(manifest: dict[str, Any]) -> str:
    lines = [
        "# F4 Reference Pool Manifest",
        "",
        "## Boundary",
        "- Reads local reference JSONL files only.",
        "- Does not run StructureMatcher, pymatgen, database queries, downloads, or external APIs.",
        "",
        "## Summary",
        f"- reference_pool_id: {manifest['reference_pool_id']}",
        f"- reference_source_count: {manifest['reference_source_count']}",
        f"- total_reference_count: {manifest['total_reference_count']}",
        f"- duplicate_reference_id_count: {manifest['duplicate_reference_id_count']}",
        f"- missing_reference_id_count: {manifest['missing_reference_id_count']}",
        "",
        "## Sources",
    ]
    for source in manifest["reference_sources"]:
        lines.append(
            "- "
            f"{source['name']}: "
            f"reference_count={source['reference_count']}, "
            f"sha256={source['sha256']}, "
            f"path=`{source['path']}`"
        )
    lines.append("")
    return "\n".join(lines)


def _duplicates(values: list[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
