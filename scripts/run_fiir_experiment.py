"""CLI for configurable lightweight FIIR experiments."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.config import load_experiment_config
from fiir_crystal.experiment import run_fiir_experiment
from fiir_crystal.validation import read_validation_results_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a lightweight FIIR mock experiment.")
    parser.add_argument("--config", default="configs/mock_fiir_loop.yaml")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output-dir")
    parser.add_argument("--pair-mode", choices=["axis_aligned", "weighted_sum", "random_negative", "binary_success_failure"])
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--validation", help="Optional offline validation results JSONL.")
    parser.add_argument("--quiet", action="store_true", help="Only print the output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.config and not Path(args.config).exists():
        raise SystemExit(f"config file does not exist: {args.config}")
    overrides = {}
    if args.input_path:
        overrides["input_path"] = args.input_path
    if args.output_dir:
        overrides["output_dir"] = args.output_dir
    if args.pair_mode:
        overrides["pair_mode"] = args.pair_mode
    if args.top_k is not None:
        overrides["top_k"] = args.top_k

    config = load_experiment_config(args.config, overrides=overrides)
    if not Path(config.input_path).exists():
        raise SystemExit(f"input file does not exist: {config.input_path}")
    validation_results = None
    if args.validation:
        if not Path(args.validation).exists():
            raise SystemExit(f"validation file does not exist: {args.validation}")
        validation_results = read_validation_results_jsonl(args.validation)
    result = run_fiir_experiment(config, validation_results=validation_results)
    summary = result["summary"]
    if args.quiet:
        print(summary["output_dir"])
        return
    print("FIIR experiment complete")
    print(f"  output_dir: {summary['output_dir']}")
    print(f"  candidates: {summary['candidate_count']}")
    print(f"  pairs: {summary['pair_count']} ({summary['pair_mode']})")
    print(f"  ranked: {summary['ranked_count']} ({summary['ranking_mode']})")
    print(f"  feedback: {summary['feedback_count']}")
    if validation_results is not None:
        print(f"  validation_results: {summary['validation_count']}")


if __name__ == "__main__":
    main()
