#!/usr/bin/env python
"""Prepare local CSV/CIF rows as an F4 reference source JSONL.

This script only reshapes existing local files into the manifest-friendly
`structure_jsonl` format. It does not parse structures, run StructureMatcher,
download datasets, query databases, or call external APIs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import write_json, write_jsonl


DEFAULT_ID_FIELDS = ("reference_id", "material_id", "mat_id", "id", "candidate_id")
DEFAULT_FORMULA_FIELDS = ("formula", "pretty_formula", "composition", "target_formula")
DEFAULT_CIF_FIELDS = ("cif", "cif_string", "structure_cif")
DEFAULT_CIF_PATH_FIELDS = ("cif_path", "cif_file", "cif_filename", "structure_path", "path")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert an existing local CSV with CIF text/path columns into an F4 "
            "reference structure JSONL. This is a data-shaping helper only."
        )
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report")
    parser.add_argument("--source-name", default="local_csv_reference")
    parser.add_argument("--reference-id-field")
    parser.add_argument("--formula-field")
    parser.add_argument("--cif-field")
    parser.add_argument("--cif-path-field")
    parser.add_argument("--id-prefix")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-missing-structure", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")

    input_csv = Path(args.input_csv)
    if not input_csv.exists():
        raise SystemExit(f"input CSV does not exist: {input_csv}")

    csv_rows = _read_csv(input_csv)
    rows = csv_rows[: args.limit] if args.limit is not None else csv_rows
    converted: list[dict[str, Any]] = []
    skipped_missing_structure = 0
    for index, row in enumerate(rows, start=1):
        item = _convert_row(
            row,
            row_index=index,
            input_csv=input_csv,
            source_name=args.source_name,
            reference_id_field=args.reference_id_field,
            formula_field=args.formula_field,
            cif_field=args.cif_field,
            cif_path_field=args.cif_path_field,
            id_prefix=args.id_prefix,
        )
        if not item["structure_ref"]:
            skipped_missing_structure += 1
            if not args.allow_missing_structure:
                raise SystemExit(f"row {index} has no CIF text/path structure field")
        converted.append(item)

    output_jsonl = Path(args.output_jsonl)
    write_jsonl(output_jsonl, converted)
    summary = {
        "workflow": "prepare_f4_reference_source",
        "source_name": args.source_name,
        "input_csv": str(input_csv),
        "output_jsonl": str(output_jsonl),
        "input_row_count": len(csv_rows),
        "converted_row_count": len(converted),
        "skipped_missing_structure": skipped_missing_structure,
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": _sha256(input_csv),
        "output_sha256": _sha256(output_jsonl),
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
    report_path = Path(args.report) if args.report else output_jsonl.with_suffix(".report.md")
    write_json(report_path.with_suffix(".json"), summary)
    report_path.write_text(_render_report(summary), encoding="utf-8")

    print("F4 reference source preparation complete")
    print(f"  source_name: {summary['source_name']}")
    print(f"  input_rows: {summary['input_row_count']}")
    print(f"  converted_rows: {summary['converted_row_count']}")
    print(f"  skipped_missing_structure: {summary['skipped_missing_structure']}")
    print(f"  output_jsonl: {output_jsonl}")
    print(f"  report: {report_path}")
    return {"summary": summary, "files": {"references": str(output_jsonl), "report": str(report_path)}}


def _convert_row(
    row: dict[str, str],
    *,
    row_index: int,
    input_csv: Path,
    source_name: str,
    reference_id_field: str | None,
    formula_field: str | None,
    cif_field: str | None,
    cif_path_field: str | None,
    id_prefix: str | None,
) -> dict[str, Any]:
    reference_id = _first_value(row, *((reference_id_field,) if reference_id_field else DEFAULT_ID_FIELDS))
    if reference_id is None:
        prefix = id_prefix or source_name
        reference_id = f"{prefix}_{row_index:06d}"
    formula = _first_value(row, *((formula_field,) if formula_field else DEFAULT_FORMULA_FIELDS))
    cif_text = _first_value(row, *((cif_field,) if cif_field else DEFAULT_CIF_FIELDS))
    cif_path_value = _first_value(row, *((cif_path_field,) if cif_path_field else DEFAULT_CIF_PATH_FIELDS))
    structure_ref = None
    structure_format = None
    if cif_text:
        structure_ref = cif_text
        structure_format = "cif_inline"
    elif cif_path_value:
        structure_ref = str(_resolve(input_csv.parent, cif_path_value))
        structure_format = "cif_path"

    metadata = {
        "source_csv": str(input_csv),
        "source_row_index": row_index,
        "source_name": source_name,
        "raw_row": dict(row),
    }
    return {
        "reference_id": str(reference_id),
        "formula": None if formula in (None, "") else str(formula),
        "source_database": source_name,
        "structure_ref": structure_ref,
        "structure_format": structure_format,
        "metadata": metadata,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _first_value(row: dict[str, str], *keys: str | None) -> str | None:
    for key in keys:
        if not key:
            continue
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _render_report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# F4 Reference Source Preparation",
            "",
            "## Boundary",
            "- Reads an existing local CSV only.",
            "- Does not run StructureMatcher, pymatgen, database queries, downloads, or external APIs.",
            "",
            "## Summary",
            f"- source_name: {summary['source_name']}",
            f"- input_csv: `{summary['input_csv']}`",
            f"- output_jsonl: `{summary['output_jsonl']}`",
            f"- input_row_count: {summary['input_row_count']}",
            f"- converted_row_count: {summary['converted_row_count']}",
            f"- skipped_missing_structure: {summary['skipped_missing_structure']}",
            "",
        ]
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
