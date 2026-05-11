"""CLI for bulk CrystalFormer generation plus FIIR smoke orchestration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.generation import (
    load_bulk_config,
    run_crystalformer_bulk_generation,
    validate_bulk_generation_config,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan and optionally run bulk CrystalFormer generation followed by FIIR smoke audits."
    )
    parser.add_argument("--config", default="configs/crystalformer_bulk_generation.json")
    parser.add_argument("--output-root")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--run-generation", action="store_true")
    parser.add_argument("--only-formula")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--max-concurrent-generations", type=int)
    parser.add_argument("--generation-cpu-threads", type=int)
    parser.add_argument("--total-cpu-cores", type=int)
    parser.add_argument("--total-gpus", type=int)
    parser.add_argument(
        "--gpu-devices",
        help="Comma-separated CUDA_VISIBLE_DEVICES tokens to assign one per concurrent generation worker.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    try:
        config = load_bulk_config(args.config)
        skip_existing = None
        if args.skip_existing and args.no_skip_existing:
            raise ValueError("choose only one of --skip-existing or --no-skip-existing")
        if args.skip_existing:
            skip_existing = True
        if args.no_skip_existing:
            skip_existing = False
        if args.validate_only:
            if args.run_generation:
                raise ValueError("--validate-only cannot be combined with --run-generation")
            result = validate_bulk_generation_config(
                config,
                only_formula=args.only_formula,
                skip_existing=skip_existing,
                output_root=Path(args.output_root) if args.output_root else None,
            )
        else:
            result = run_crystalformer_bulk_generation(
                config,
                run_generation=args.run_generation,
                only_formula=args.only_formula,
                continue_on_error=args.continue_on_error,
                skip_existing=skip_existing,
                output_root=Path(args.output_root) if args.output_root else None,
                max_concurrent_generations=args.max_concurrent_generations,
                generation_cpu_threads=args.generation_cpu_threads,
                total_cpu_cores=args.total_cpu_cores,
                total_gpus=args.total_gpus,
                gpu_devices=args.gpu_devices,
            )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    summary = result["summary"]
    if args.validate_only:
        print("CrystalFormer bulk generation validation complete")
        print(f"  ready_for_generation: {summary['ready_for_generation']}")
        print(f"  formula_count: {summary['formula_count']}")
        print(f"  total_num_samples: {summary['total_num_samples']}")
        print(f"  blocking_reasons: {summary['blocking_reasons']}")
        print(f"  warnings: {summary['warnings']}")
        print(f"  plan: {result['files']['plan']}")
        print(f"  summary: {result['files']['summary']}")
        print(f"  report: {result['files']['report']}")
        return result

    print("CrystalFormer bulk generation orchestration complete")
    print(f"  run_generation: {summary['run_generation']}")
    print(f"  parallelism: {summary['parallelism']}")
    print(f"  timing: {summary['timing']}")
    print(f"  formula_count: {summary['formula_count']}")
    print(f"  completed_formula_count: {summary['completed_formula_count']}")
    print(f"  status_counts: {summary['status_counts']}")
    print(f"  total_candidates: {summary['total_candidates']}")
    print(f"  total_dpo_eligible: {summary['total_dpo_eligible']}")
    print(f"  total_preference_pairs: {summary['total_preference_pairs']}")
    print(f"  plan: {result['files']['plan']}")
    print(f"  summary: {result['files']['summary']}")
    print(f"  report: {result['files']['report']}")
    return result


if __name__ == "__main__":
    main()
