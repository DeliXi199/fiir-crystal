"""CLI for preparing a non-overwriting CrystalFormer DPO smoke run."""

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
    CrystalFormerDpoSmokeRunConfig,
    prepare_crystalformer_dpo_smoke_run,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare chosen/rejected raw-sequence JSONL files and a safe CrystalFormer DPO smoke command."
    )
    parser.add_argument("--preference-pairs-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-checkpoint-dir", required=True)
    parser.add_argument("--crystalformer-work-dir", default="external/CrystalFormer")
    parser.add_argument("--run-name", default="fiir_dpo_smoke")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batchsize", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--beta", type=float, default=0.1)
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument("--gamma", type=float, default=0.0)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--optimizer", default="adam", choices=["adam", "adamw"])
    parser.add_argument("--num-io-process", type=int, default=1)
    parser.add_argument("--max-pairs", type=int)
    parser.add_argument("--preference-artifact-label")
    parser.add_argument("--source-validation-jsonl")
    parser.add_argument("--input-candidate-count", type=int)
    parser.add_argument("--f3-available-candidate-count", type=int)
    parser.add_argument("--disagreement-candidate-count", type=int)
    parser.add_argument("--evidence-caveat")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    config = CrystalFormerDpoSmokeRunConfig(
        preference_pairs_jsonl=Path(args.preference_pairs_jsonl),
        output_dir=Path(args.output_dir),
        base_checkpoint_dir=Path(args.base_checkpoint_dir),
        crystalformer_work_dir=Path(args.crystalformer_work_dir),
        run_name=args.run_name,
        epochs=args.epochs,
        batchsize=args.batchsize,
        lr=args.lr,
        beta=args.beta,
        label_smoothing=args.label_smoothing,
        gamma=args.gamma,
        val_ratio=args.val_ratio,
        optimizer=args.optimizer,
        num_io_process=args.num_io_process,
        max_pairs=args.max_pairs,
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
        result = prepare_crystalformer_dpo_smoke_run(config)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    manifest = result["manifest"]
    print("CrystalFormer DPO smoke run prepared")
    print(f"  prepared_pairs: {manifest['prepared_pair_count']}")
    print(f"  base_checkpoint_dir: {manifest['base_checkpoint_dir']}")
    print(f"  training_output_root: {manifest['training_output_root']}")
    print(f"  chosen_sequences: {result['files']['chosen_sequences']}")
    print(f"  rejected_sequences: {result['files']['rejected_sequences']}")
    print(f"  manifest: {result['files']['manifest']}")
    print(f"  report: {result['files']['report']}")
    print("  command:")
    print(f"    {manifest['recommended_training_command']}")
    return result


if __name__ == "__main__":
    main()
