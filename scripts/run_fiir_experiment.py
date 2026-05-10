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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a lightweight FIIR mock experiment.")
    parser.add_argument("--config", default="configs/mock_fiir_loop.yaml")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output-dir")
    parser.add_argument("--pair-mode", choices=["axis_aligned", "weighted_sum", "random_negative", "binary_success_failure"])
    parser.add_argument("--top-k", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
    result = run_fiir_experiment(config)
    summary = result["summary"]
    print("FIIR experiment complete")
    print(f"  output_dir: {summary['output_dir']}")
    print(f"  candidates: {summary['candidate_count']}")
    print(f"  pairs: {summary['pair_count']} ({summary['pair_mode']})")
    print(f"  ranked: {summary['ranked_count']} ({summary['ranking_mode']})")
    print(f"  feedback: {summary['feedback_count']}")


if __name__ == "__main__":
    main()
