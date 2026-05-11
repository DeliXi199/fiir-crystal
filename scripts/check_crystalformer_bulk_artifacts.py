"""CLI for local-only QA of CrystalFormer bulk/audit/DPO artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.artifact_qa import ArtifactQAConfig, check_crystalformer_bulk_artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run read-only QA checks over existing CrystalFormer bulk, audit, and DPO artifacts."
    )
    parser.add_argument("--input-roots", nargs="+", default=[])
    parser.add_argument("--glob", dest="glob_patterns", action="append", default=[])
    parser.add_argument("--collection-summary")
    parser.add_argument("--output-dir", default="outputs/crystalformer_bulk_qa")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--fail-on-critical", action="store_true")
    parser.add_argument("--max-examples", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if not args.input_roots and not args.glob_patterns:
        raise SystemExit("provide --input-roots and/or --glob")
    if args.max_examples < 0:
        raise SystemExit("--max-examples must be non-negative")

    result = check_crystalformer_bulk_artifacts(
        ArtifactQAConfig(
            input_roots=tuple(Path(path) for path in args.input_roots),
            glob_patterns=tuple(args.glob_patterns),
            collection_summary=None if args.collection_summary is None else Path(args.collection_summary),
            output_dir=Path(args.output_dir),
            strict=args.strict,
            fail_on_critical=args.fail_on_critical,
            max_examples=args.max_examples,
        )
    )
    summary = result["summary"]
    print("CrystalFormer bulk artifact QA complete")
    print(f"  ready: {summary['ready']}")
    print(f"  scanned_root_count: {summary['scanned_root_count']}")
    print(f"  critical_count: {summary['critical_count']}")
    print(f"  warning_count: {summary['warning_count']}")
    print(f"  info_count: {summary['info_count']}")
    print(f"  check_counts: {summary['check_counts']}")
    print(f"  summary: {result['files']['summary']}")
    print(f"  report: {result['files']['report']}")

    if args.fail_on_critical and summary["critical_count"]:
        raise SystemExit("QA found critical failures")
    return result


if __name__ == "__main__":
    main()
