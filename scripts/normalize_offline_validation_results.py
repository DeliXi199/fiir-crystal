"""CLI for normalizing existing local MLIP/DFT validation result files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.validation_normalization import (
    ValidationNormalizationConfig,
    normalize_offline_validation_results,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize already-existing local MLIP/DFT validation results without running validators."
    )
    parser.add_argument("--input", dest="inputs", action="append", required=True)
    parser.add_argument("--input-format", choices=["auto", "csv", "json", "jsonl"], default="auto")
    parser.add_argument(
        "--output-jsonl",
        default="outputs/offline_validation_normalized/validation_results.jsonl",
    )
    parser.add_argument(
        "--output-summary",
        default="outputs/offline_validation_normalized/normalization_summary.json",
    )
    parser.add_argument("--report", default="outputs/offline_validation_normalized/report.md")
    parser.add_argument("--candidate-index")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    config = ValidationNormalizationConfig(
        inputs=tuple(Path(path) for path in args.inputs),
        input_format=args.input_format,
        output_jsonl=Path(args.output_jsonl),
        output_summary=Path(args.output_summary),
        report=Path(args.report),
        candidate_index=None if args.candidate_index is None else Path(args.candidate_index),
        strict=args.strict,
    )
    try:
        result = normalize_offline_validation_results(config)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    summary = result["summary"]
    print("Offline validation normalization complete")
    print(f"  normalized_row_count: {summary['normalized_row_count']}")
    print(f"  issue_count: {summary['issue_count']}")
    print(f"  unmatched_candidate_id_count: {summary['unmatched_candidate_id_count']}")
    print(f"  formula_mismatch_count: {summary['formula_mismatch_count']}")
    print(f"  failed_or_incomplete_count: {summary['failed_or_incomplete_count']}")
    print(f"  f3_available_candidate_count: {summary['f3_available_candidate_count']}")
    print(f"  output_jsonl: {result['files']['normalized_validation_results']}")
    print(f"  summary: {result['files']['normalization_summary']}")
    print(f"  report: {result['files']['report']}")

    if args.strict and (
        summary["missing_required_field_count"]
        or summary["unmatched_candidate_id_count"]
        or summary["formula_mismatch_count"]
    ):
        raise SystemExit("strict normalization found blocking issues")
    return result


if __name__ == "__main__":
    main()
