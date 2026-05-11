"""CLI for local-only collection of CrystalFormer bulk output artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.collection import CollectionConfig, collect_crystalformer_bulk_results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect existing CrystalFormer bulk, audit, and DPO artifacts without modifying scanned roots."
    )
    parser.add_argument("--output-roots", nargs="+", default=[])
    parser.add_argument("--glob", dest="glob_patterns", action="append", default=[])
    parser.add_argument("--output-dir", default="outputs/crystalformer_bulk_collection")
    parser.add_argument("--include-in-progress", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--max-error-examples", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if not args.output_roots and not args.glob_patterns:
        raise SystemExit("provide --output-roots and/or --glob")
    if args.max_error_examples < 0:
        raise SystemExit("--max-error-examples must be non-negative")

    result = collect_crystalformer_bulk_results(
        CollectionConfig(
            output_roots=tuple(Path(path) for path in args.output_roots),
            glob_patterns=tuple(args.glob_patterns),
            output_dir=Path(args.output_dir),
            include_in_progress=args.include_in_progress,
            strict=args.strict,
            max_error_examples=args.max_error_examples,
        )
    )
    summary = result["summary"]

    print("CrystalFormer bulk collection complete")
    print(f"  scanned_root_count: {summary['scanned_root_count']}")
    print(f"  formula_count: {summary['formula_count']}")
    print(f"  completed_formula_count: {summary['completed_formula_count']}")
    print(f"  failed_formula_count: {summary['failed_formula_count']}")
    print(f"  in_progress_formula_count: {summary['in_progress_formula_count']}")
    print(f"  missing_artifact_count: {summary['missing_artifact_count']}")
    print(f"  corrupt_artifact_count: {summary['corrupt_artifact_count']}")
    print(f"  total_candidates: {summary['total_candidates']}")
    print(f"  total_audit_candidates: {summary['total_audit_candidates']}")
    print(f"  total_dpo_eligible: {summary['total_dpo_eligible']}")
    print(f"  total_preference_pairs: {summary['total_preference_pairs']}")
    print(f"  summary: {result['files']['summary']}")
    print(f"  report: {result['files']['report']}")

    if args.strict and (summary["missing_artifact_count"] or summary["corrupt_artifact_count"]):
        raise SystemExit("collector strict mode found missing or corrupt artifacts")
    return result


if __name__ == "__main__":
    main()
