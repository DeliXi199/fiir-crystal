import json

import pytest

from fiir_crystal.dpo import (
    CrystalFormerDpoSmokeRunConfig,
    prepare_crystalformer_dpo_smoke_run,
)
from fiir_crystal.io import write_jsonl
from scripts.prepare_crystalformer_dpo_smoke_run import main


def _sequence(g: int = 221) -> dict:
    return {
        "g": str(g),
        "L": json.dumps([4.0, 4.0, 4.0, 90.0, 90.0, 90.0]),
        "X": json.dumps([[0.0, 0.0, 0.0]] * 21),
        "A": json.dumps([8] + [0] * 20),
        "W": json.dumps([1] + [0] * 20),
    }


def _pair(pair_id: str = "BaTiO3:good>bad") -> dict:
    return {
        "pair_id": pair_id,
        "condition": {"mode": "csp", "formula": "BaTiO3", "spacegroup": None, "generation": {}},
        "chosen_candidate_id": "good",
        "rejected_candidate_id": "bad",
        "chosen_sequence": _sequence(221),
        "rejected_sequence": _sequence(62),
        "chosen_score": 0.0,
        "rejected_score": 0.4,
        "preference_margin": 0.4,
        "preference_type": "stability_aware_offline_validation",
        "preference_reason": ["lower_fiir_score"],
        "chosen_failure_vector": {"f1_geometry": 0.0, "f2_chemistry": 0.0, "f3_stability": 0.0},
        "rejected_failure_vector": {"f1_geometry": 0.0, "f2_chemistry": 0.0, "f3_stability": 1.0},
        "metadata": {},
    }


def test_prepare_dpo_smoke_run_writes_safe_artifacts(tmp_path) -> None:
    pairs = tmp_path / "preference_pairs.jsonl"
    checkpoint = tmp_path / "base_checkpoint"
    crystalformer = tmp_path / "CrystalFormer"
    output_dir = tmp_path / "smoke"
    checkpoint.mkdir()
    crystalformer.mkdir()
    write_jsonl(pairs, [_pair()])

    result = prepare_crystalformer_dpo_smoke_run(
        CrystalFormerDpoSmokeRunConfig(
            preference_pairs_jsonl=pairs,
            output_dir=output_dir,
            base_checkpoint_dir=checkpoint,
            crystalformer_work_dir=crystalformer,
        )
    )

    manifest = result["manifest"]
    assert manifest["runs_training"] is False
    assert manifest["non_overwrite"] is True
    assert manifest["prepared_pair_count"] == 1
    assert manifest["base_checkpoint_dir"] != manifest["training_output_root"]
    assert "--restore_path" in manifest["recommended_training_command"]
    assert "--folder" in manifest["recommended_training_command"]
    chosen = json.loads((output_dir / "chosen_sequences.jsonl").read_text(encoding="utf-8").splitlines()[0])
    rejected = json.loads((output_dir / "rejected_sequences.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert chosen["g"] == 221
    assert rejected["g"] == 62
    assert len(chosen["A"]) == 21
    assert len(chosen["X"]) == 21
    assert (output_dir / "run_training.sh").exists()
    assert (output_dir / "report.md").exists()


def test_prepare_dpo_smoke_run_blocks_output_inside_checkpoint(tmp_path) -> None:
    pairs = tmp_path / "preference_pairs.jsonl"
    checkpoint = tmp_path / "base_checkpoint"
    crystalformer = tmp_path / "CrystalFormer"
    checkpoint.mkdir()
    crystalformer.mkdir()
    write_jsonl(pairs, [_pair()])

    with pytest.raises(ValueError, match="inside the base checkpoint"):
        prepare_crystalformer_dpo_smoke_run(
            CrystalFormerDpoSmokeRunConfig(
                preference_pairs_jsonl=pairs,
                output_dir=checkpoint,
                base_checkpoint_dir=checkpoint,
                crystalformer_work_dir=crystalformer,
            )
        )


def test_prepare_dpo_smoke_run_cli(tmp_path) -> None:
    pairs = tmp_path / "preference_pairs.jsonl"
    checkpoint = tmp_path / "base_checkpoint"
    crystalformer = tmp_path / "CrystalFormer"
    output_dir = tmp_path / "smoke"
    checkpoint.mkdir()
    crystalformer.mkdir()
    write_jsonl(pairs, [_pair(), _pair("BaTiO3:good2>bad2")])

    result = main(
        [
            "--preference-pairs-jsonl",
            str(pairs),
            "--output-dir",
            str(output_dir),
            "--base-checkpoint-dir",
            str(checkpoint),
            "--crystalformer-work-dir",
            str(crystalformer),
            "--max-pairs",
            "1",
        ]
    )

    assert result["manifest"]["input_pair_count"] == 2
    assert result["manifest"]["prepared_pair_count"] == 1
    assert (output_dir / "dpo_smoke_manifest.json").exists()
