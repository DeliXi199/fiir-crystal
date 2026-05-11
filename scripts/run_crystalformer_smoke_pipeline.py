"""CLI for the CrystalFormer real-smoke integration pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.evaluation.error_audit import F3_UNAVAILABLE_MODE
from fiir_crystal.generation.crystalformer_smoke_pipeline import (
    CrystalFormerSmokePipelineConfig,
    run_crystalformer_smoke_pipeline,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local CrystalFormer output -> audit -> DPO preference smoke pipeline."
    )
    parser.add_argument("--input-dir", required=True, help="Existing CrystalFormer raw output directory or file.")
    parser.add_argument("--formula", required=True)
    parser.add_argument("--spacegroup", type=int)
    parser.add_argument("--output-root", default="outputs")
    parser.add_argument("--parser-backend", choices=["auto", "none", "pymatgen"], default="auto")
    parser.add_argument("--stability-mode", choices=[F3_UNAVAILABLE_MODE], default=F3_UNAVAILABLE_MODE)
    parser.add_argument("--source-format", default="auto")
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--min-preference-margin", type=float, default=1e-6)
    parser.add_argument("--max-pairs", type=int)
    parser.add_argument("--crystalformer-command")
    parser.add_argument("--crystalformer-work-dir")
    parser.add_argument("--run-generation", action="store_true")
    parser.add_argument("--offline-validation-jsonl")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    config = CrystalFormerSmokePipelineConfig(
        input_dir=Path(args.input_dir),
        formula=args.formula,
        output_root=Path(args.output_root),
        parser_backend=args.parser_backend,
        stability_mode=args.stability_mode,
        spacegroup=args.spacegroup,
        source_format=args.source_format,
        max_candidates=args.max_candidates,
        min_preference_margin=args.min_preference_margin,
        max_pairs=args.max_pairs,
        crystalformer_command=args.crystalformer_command,
        crystalformer_work_dir=(
            Path(args.crystalformer_work_dir) if args.crystalformer_work_dir else None
        ),
        run_generation=args.run_generation,
        offline_validation_jsonl=(
            Path(args.offline_validation_jsonl) if args.offline_validation_jsonl else None
        ),
    )
    try:
        result = run_crystalformer_smoke_pipeline(config)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    summary = result["summary"]
    print("CrystalFormer smoke pipeline complete")
    print(f"  candidates: {summary['candidate_count']}")
    print(f"  parse_status_counts: {summary['parse_status_counts']}")
    print(f"  f1_status_counts: {summary['f1_status_counts']}")
    print(f"  f2_status_counts: {summary['f2_status_counts']}")
    print(f"  f3_status_counts: {summary['f3_status_counts']}")
    print(f"  f3_validation: {summary['f3_validation']}")
    print(f"  offline_validation_imported: {summary['offline_validation_imported']}")
    if summary["validation_import_summary"] is not None:
        validation = summary["validation_import_summary"]
        print(f"  validation_matched: {validation['matched_count']}")
        print(f"  validation_f3_available: {validation['f3_available_count']}")
    print(f"  dpo_eligible: {summary['dpo_eligible_count']}")
    print(f"  preference_pairs: {summary['preference_pair_count']}")
    print(f"  preference_skip_reasons: {summary['preference_skip_reasons']}")
    print(f"  audit_dir: {summary['output_dirs']['audit']}")
    print(f"  dpo_preferences_dir: {summary['output_dirs']['preferences']}")
    print(f"  report: {result['files']['pipeline_report']}")
    return result


if __name__ == "__main__":
    main()
