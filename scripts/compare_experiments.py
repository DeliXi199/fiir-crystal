"""CLI for aggregating existing FIIR experiment outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.comparison import write_aggregate_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate FIIR experiment output directories.")
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--output-dir", default="outputs/aggregate_report")
    parser.add_argument("--quiet", action="store_true", help="Only print the output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for run in args.runs:
        if not Path(run).exists():
            raise SystemExit(f"run directory does not exist: {run}")
    summary = write_aggregate_outputs(args.runs, args.output_dir)
    if args.quiet:
        print(summary["output_dir"])
        return
    print("Experiment aggregation complete")
    print(f"  output_dir: {summary['output_dir']}")
    print(f"  runs: {summary['run_count']}")
    for row in summary["runs"]:
        print(
            f"  {row['run_name']}: mode={row['pair_mode']}, pairs={row['pair_count']}, "
            f"top_k_valid={row['top_k_valid_rate']}"
        )


if __name__ == "__main__":
    main()
