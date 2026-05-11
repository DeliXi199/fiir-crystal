"""CLI for the mock FIIR active discovery loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.feedback import run_mock_active_loop
from fiir_crystal.validation import read_validation_results_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a mock FIIR active loop without external services.")
    parser.add_argument("--config", default="configs/mock_fiir_loop.yaml")
    parser.add_argument("--input", dest="input_path", default="examples/mock_candidates.jsonl")
    parser.add_argument("--validation", help="Optional offline validation results JSONL.")
    parser.add_argument("--output-dir", default="outputs/mock_active_loop")
    parser.add_argument("--rounds", type=int, default=3)
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
    result = run_mock_active_loop(
        args.config,
        validation_results=validation_results,
        output_dir=args.output_dir,
        input_path=args.input_path,
        rounds=args.rounds,
    )
    summary = result["summary"]
    if args.quiet:
        print(summary["output_dir"])
        return
    print("Mock active loop complete")
    print(f"  output_dir: {summary['output_dir']}")
    print(f"  rounds: {summary['round_count']}")
    print(f"  feedback_events: {summary['feedback_event_count']}")
    print(f"  positive_evidence: {summary['positive_evidence_count']}")
    print(f"  negative_evidence: {summary['negative_evidence_count']}")


def _require_file(path: str, label: str) -> None:
    if not Path(path).exists():
        raise SystemExit(f"{label} file does not exist: {path}")


if __name__ == "__main__":
    main()
