"""CLI for preparing the external CrystalFormer DPO training boundary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.dpo.evidence import DpoEvidenceContext
from fiir_crystal.dpo import (
    TrainingBoundaryConfig,
    prepare_crystalformer_dpo_training_boundary,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a DPO preference artifact and write an external CrystalFormer trainer manifest."
    )
    parser.add_argument("--preference-pairs-jsonl", required=True)
    parser.add_argument("--output-dir", default="outputs/crystalformer_dpo_training_boundary")
    parser.add_argument("--crystalformer-work-dir", default="external/CrystalFormer")
    parser.add_argument("--checkpoint-dir", default="external/checkpoints")
    parser.add_argument("--allow-missing-workspace", action="store_true")
    parser.add_argument("--require-submodule-for-training", action="store_true")
    parser.add_argument("--training-command")
    parser.add_argument("--run-training", action="store_true")
    parser.add_argument("--preference-artifact-label")
    parser.add_argument("--source-validation-jsonl")
    parser.add_argument("--input-candidate-count", type=int)
    parser.add_argument("--f3-available-candidate-count", type=int)
    parser.add_argument("--disagreement-candidate-count", type=int)
    parser.add_argument("--evidence-caveat")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    config = TrainingBoundaryConfig(
        preference_pairs_jsonl=Path(args.preference_pairs_jsonl),
        output_dir=Path(args.output_dir),
        crystalformer_work_dir=Path(args.crystalformer_work_dir),
        checkpoint_dir=Path(args.checkpoint_dir),
        require_workspace=not args.allow_missing_workspace,
        require_submodule_for_training=args.require_submodule_for_training,
        training_command=args.training_command,
        run_training=args.run_training,
        evidence_context=DpoEvidenceContext(
            preference_artifact_label=args.preference_artifact_label,
            source_validation_jsonl=Path(args.source_validation_jsonl) if args.source_validation_jsonl else None,
            input_candidate_count=args.input_candidate_count,
            f3_available_candidate_count=args.f3_available_candidate_count,
            disagreement_candidate_count=args.disagreement_candidate_count,
            caveat=args.evidence_caveat or DpoEvidenceContext().caveat,
        ),
    )
    try:
        result = prepare_crystalformer_dpo_training_boundary(config)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    summary = result["summary"]
    pair = summary["pair_validation"]
    workspace = summary["workspace"]["crystalformer"]
    print("CrystalFormer DPO training boundary prepared")
    print(f"  ready_for_external_training: {summary['ready_for_external_training']}")
    print(f"  blocking_reasons: {summary['blocking_reasons']}")
    print(f"  warnings: {summary['warnings']}")
    print(f"  input_pairs: {pair['input_pair_count']}")
    print(f"  valid_pairs: {pair['valid_pair_count']}")
    print(f"  invalid_pairs: {pair['invalid_pair_count']}")
    print(f"  preference_type_breakdown: {pair['preference_type_breakdown']}")
    print(f"  crystalformer_state: {workspace['clone_state']}")
    print(f"  manifest: {result['files']['manifest']}")
    print(f"  report: {result['files']['report']}")
    print(f"  provenance: {result['files']['provenance']}")
    return result


if __name__ == "__main__":
    main()
