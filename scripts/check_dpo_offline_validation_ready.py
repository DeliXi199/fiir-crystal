#!/usr/bin/env python
"""Check whether matched DPO offline validation outputs are ready to import."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT in sys.path:
    sys.path.remove(PROJECT_ROOT_TEXT)
sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.io import JsonlFormatError, read_jsonl, write_json


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only readiness check for normalized before/after MLIP validation JSONL files."
        )
    )
    parser.add_argument(
        "--validation",
        action="append",
        required=True,
        help="Input as LABEL=path/to/normalized/validation_results.jsonl. Repeat for each expected file.",
    )
    parser.add_argument("--expected-rows", type=int, required=True)
    parser.add_argument("--output-json", help="Optional path for the readiness summary JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    validations = [_parse_validation_arg(item) for item in args.validation]
    labels = [label for label, _ in validations]
    if len(set(labels)) != len(labels):
        raise SystemExit("validation labels must be unique")
    rows = [_check_file(label, path, args.expected_rows) for label, path in validations]
    ready = all(row["ready"] for row in rows)
    summary = {
        "workflow": "dpo_offline_validation_readiness_check",
        "ready": ready,
        "expected_rows": args.expected_rows,
        "validation_count": len(rows),
        "validations": rows,
        "local_only": True,
        "runs_dft": False,
        "runs_generation": False,
        "runs_mlip": False,
        "runs_training": False,
        "downloads": False,
        "calls_external_apis": False,
        "caveat": "Readiness only. Downstream labels are MLIP relaxation proxy evidence, not DFT or hull-confirmed stability.",
    }
    if args.output_json:
        write_json(args.output_json, summary)
    print(f"offline validation ready: {ready}")
    for row in rows:
        print(
            f"  {row['label']}: exists={row['exists']} row_count={row['row_count']} "
            f"ready={row['ready']} issue={row['issue']}"
        )
    return summary


def _parse_validation_arg(item: str) -> tuple[str, Path]:
    if "=" not in item:
        raise SystemExit(f"--validation must be LABEL=PATH, got: {item}")
    label, path = item.split("=", 1)
    label = label.strip()
    if not label:
        raise SystemExit(f"empty validation label in --validation: {item}")
    return label, Path(path)


def _check_file(label: str, path: Path, expected_rows: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "label": label,
            "path": str(path),
            "exists": False,
            "row_count": 0,
            "ready": False,
            "issue": "missing",
        }
    try:
        rows = read_jsonl(path)
    except JsonlFormatError as exc:
        return {
            "label": label,
            "path": str(path),
            "exists": True,
            "row_count": None,
            "ready": False,
            "issue": f"invalid_jsonl: {exc}",
        }
    row_count = len(rows)
    issue = None if row_count == expected_rows else "row_count_mismatch"
    return {
        "label": label,
        "path": str(path),
        "exists": True,
        "row_count": row_count,
        "ready": issue is None,
        "issue": issue,
    }


if __name__ == "__main__":
    main()
