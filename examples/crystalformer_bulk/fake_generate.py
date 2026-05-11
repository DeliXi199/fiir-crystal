"""Tiny fake CrystalFormer generator for bulk orchestration tests.

This script writes fake raw CSV files only. It is not CrystalFormer and does
not generate real structures.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write fake CrystalFormer raw CSV output.")
    parser.add_argument("--formula", required=True)
    parser.add_argument("--num-samples", type=int, required=True)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fail-formula")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.fail_formula and args.fail_formula == args.formula:
        raise SystemExit(f"requested fake failure for {args.formula}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "samples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "candidate_id",
                "g",
                "W",
                "A",
                "X",
                "L",
                "formula",
                "spacegroup",
                "source_checkpoint",
                "temperature",
                "top_k",
            ],
        )
        writer.writeheader()
        for index in range(max(1, args.num_samples)):
            overlap = index == max(1, args.num_samples) - 1
            coords = (
                "0 0 0;0.01 0.01 0.01;0.5 0.5 0;0.5 0 0.5;0 0.5 0.5"
                if overlap
                else "0 0 0;0.5 0.5 0.5;0.5 0.5 0;0.5 0 0.5;0 0.5 0.5"
            )
            writer.writerow(
                {
                    "candidate_id": f"{args.formula}_fake_{index + 1:03d}",
                    "g": "221",
                    "W": "a,b,c,c,c",
                    "A": "Ba Ti O O O",
                    "X": coords,
                    "L": "4 4 4",
                    "formula": args.formula,
                    "spacegroup": "221",
                    "source_checkpoint": "fake-bulk-checkpoint",
                    "temperature": "1.0",
                    "top_k": str(args.top_k),
                }
            )
    print(f"wrote fake CrystalFormer raw output: {csv_path}")


if __name__ == "__main__":
    main()
