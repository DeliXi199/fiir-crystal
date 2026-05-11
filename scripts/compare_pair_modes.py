"""CLI for comparing lightweight FIIR pair construction modes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.comparison import compare_pair_modes
from fiir_crystal.validation import read_validation_results_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare FIIR pair construction modes.")
    parser.add_argument("--config", default="configs/mock_fiir_loop.yaml")
    parser.add_argument("--input", dest="input_path", default="examples/mock_candidates.jsonl")
    parser.add_argument("--output-dir", default="outputs/pair_mode_comparison")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["axis_aligned", "weighted_sum", "random_negative", "binary_success_failure"],
        choices=["axis_aligned", "weighted_sum", "random_negative", "binary_success_failure"],
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation", help="Optional offline validation results JSONL.")
    parser.add_argument("--quiet", action="store_true", help="Only print the output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _require_file(args.config, "config")
    _require_file(args.input_path, "input")
    validation_results = None
    if args.validation:
        _require_file(args.validation, "validation")
        validation_results = read_validation_results_jsonl(args.validation)
    result = compare_pair_modes(
        args.config,
        modes=args.modes,
        output_dir=args.output_dir,
        input_path=args.input_path,
        top_k=args.top_k,
        seed=args.seed,
        validation_results=validation_results,
    )
    if args.quiet:
        print(result["output_dir"])
        return
    summary = result["summary"]
    print("Pair mode comparison complete")
    print(f"  output_dir: {summary['output_dir']}")
    print(f"  modes: {', '.join(row['mode'] for row in summary['modes'])}")
    for row in summary["modes"]:
        print(
            f"  {row['mode']}: pairs={row['pair_count']}, "
            f"top_k_valid={row['top_k_valid_rate']}, "
            f"valid_pair_ratio={row['valid_pair_ratio']}"
        )


def _require_file(path: str, label: str) -> None:
    if not Path(path).exists():
        raise SystemExit(f"{label} file does not exist: {path}")


if __name__ == "__main__":
    main()
