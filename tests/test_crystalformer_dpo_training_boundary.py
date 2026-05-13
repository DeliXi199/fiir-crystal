import json
import sys
from pathlib import Path

import pytest

from fiir_crystal.io import write_jsonl
from scripts.prepare_crystalformer_dpo_training_boundary import main


def _valid_pair(pair_id: str = "pair_001") -> dict:
    sequence = {"g": "221", "W": "a,b,c,c,c", "A": "Ba Ti O O O", "X": "coords", "L": "lattice"}
    return {
        "pair_id": pair_id,
        "condition": {
            "mode": "csp",
            "formula": "BaTiO3",
            "spacegroup": None,
            "generation": {
                "source_checkpoint": "fake-local-checkpoint",
                "temperature": "1.0",
                "top_k": "40",
            },
        },
        "chosen_candidate_id": "good",
        "rejected_candidate_id": "bad",
        "chosen_sequence": sequence,
        "rejected_sequence": sequence,
        "chosen_score": 0.01,
        "rejected_score": 0.42,
        "preference_margin": 0.41,
        "preference_type": "stability_aware_offline_validation",
        "preference_reason": ["lower_fiir_score", "offline_validation_stability_signal"],
        "chosen_failure_vector": {"f1_geometry": 0.0, "f2_chemistry": 0.0, "f3_stability": 0.0},
        "rejected_failure_vector": {"f1_geometry": 0.2, "f2_chemistry": 0.0, "f3_stability": 0.42},
        "metadata": {"dpo_training": False, "stability_preference": True},
    }


def _workspace(path: Path) -> Path:
    work_dir = path / "CrystalFormer"
    (work_dir / ".git").mkdir(parents=True)
    return work_dir


def test_training_boundary_writes_manifest_and_report(tmp_path) -> None:
    preference_path = tmp_path / "preference_pairs.jsonl"
    write_jsonl(preference_path, [_valid_pair()])
    work_dir = _workspace(tmp_path)
    output_dir = tmp_path / "boundary"

    result = main(
        [
            "--preference-pairs-jsonl",
            str(preference_path),
            "--output-dir",
            str(output_dir),
            "--crystalformer-work-dir",
            str(work_dir),
            "--preference-artifact-label",
            "strict_three_mlip_fixture",
            "--input-candidate-count",
            "2",
            "--f3-available-candidate-count",
            "1",
            "--disagreement-candidate-count",
            "1",
            "--evidence-caveat",
            "fixture labels are proxy evidence",
        ]
    )

    summary = result["summary"]
    assert summary["ready_for_external_training"] is True
    assert summary["train_dpo_in_fiir"] is False
    assert summary["pair_validation"]["valid_pair_count"] == 1
    assert summary["pair_validation"]["stability_aware_pair_count"] == 1
    assert (output_dir / "trainer_manifest.json").exists()
    assert (output_dir / "report.md").exists()
    manifest = json.loads((output_dir / "trainer_manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_training_only"] is True
    assert "torch" in manifest["not_core_dependencies"]
    assert "MatGL" in manifest["not_core_dependencies"]
    assert manifest["evidence_context"]["preference_artifact_label"] == "strict_three_mlip_fixture"
    assert manifest["evidence_context"]["input_candidate_count"] == 2
    assert manifest["evidence_context"]["f3_available_candidate_count"] == 1
    assert manifest["evidence_context"]["disagreement_candidate_count"] == 1
    assert manifest["evidence_context"]["caveat"] == "fixture labels are proxy evidence"


def test_training_boundary_does_not_execute_command_without_run_training(tmp_path) -> None:
    preference_path = tmp_path / "preference_pairs.jsonl"
    write_jsonl(preference_path, [_valid_pair()])
    work_dir = _workspace(tmp_path)
    marker = tmp_path / "ran.txt"
    fake_script = tmp_path / "fake_train.py"
    fake_script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = main(
        [
            "--preference-pairs-jsonl",
            str(preference_path),
            "--output-dir",
            str(tmp_path / "boundary"),
            "--crystalformer-work-dir",
            str(work_dir),
            "--training-command",
            f"{sys.executable} {fake_script}",
        ]
    )

    assert not marker.exists()
    provenance = json.loads(Path(result["files"]["provenance"]).read_text(encoding="utf-8"))
    assert provenance["executed"] is False
    assert provenance["reason"] == "run_training_not_requested"


def test_training_boundary_run_training_requires_command(tmp_path) -> None:
    preference_path = tmp_path / "preference_pairs.jsonl"
    write_jsonl(preference_path, [_valid_pair()])
    work_dir = _workspace(tmp_path)

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--preference-pairs-jsonl",
                str(preference_path),
                "--output-dir",
                str(tmp_path / "boundary"),
                "--crystalformer-work-dir",
                str(work_dir),
                "--run-training",
            ]
        )

    assert "--run-training requires --training-command" in str(exc.value)


def test_training_boundary_records_fake_command_provenance(tmp_path) -> None:
    preference_path = tmp_path / "preference_pairs.jsonl"
    write_jsonl(preference_path, [_valid_pair()])
    work_dir = _workspace(tmp_path)
    marker = tmp_path / "ran.txt"
    fake_script = tmp_path / "fake_train.py"
    fake_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')",
                "print('fake trainer boundary command')",
            ]
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "--preference-pairs-jsonl",
            str(preference_path),
            "--output-dir",
            str(tmp_path / "boundary"),
            "--crystalformer-work-dir",
            str(work_dir),
            "--training-command",
            f"{sys.executable} {fake_script}",
            "--run-training",
        ]
    )

    assert marker.read_text(encoding="utf-8") == "ran"
    provenance = json.loads(Path(result["files"]["provenance"]).read_text(encoding="utf-8"))
    assert provenance["executed"] is True
    assert provenance["returncode"] == 0
    assert "fake trainer boundary command" in provenance["stdout"]


def test_training_boundary_blocks_invalid_pairs(tmp_path) -> None:
    bad_pair = _valid_pair()
    bad_pair["chosen_sequence"] = {"g": "221"}
    bad_pair["preference_margin"] = 0.0
    preference_path = tmp_path / "preference_pairs.jsonl"
    write_jsonl(preference_path, [bad_pair])
    work_dir = _workspace(tmp_path)

    result = main(
        [
            "--preference-pairs-jsonl",
            str(preference_path),
            "--output-dir",
            str(tmp_path / "boundary"),
            "--crystalformer-work-dir",
            str(work_dir),
        ]
    )

    summary = result["summary"]
    assert summary["ready_for_external_training"] is False
    assert "invalid_preference_pairs" in summary["blocking_reasons"]
    assert summary["pair_validation"]["invalid_reasons"]["chosen_missing_sequence_fields"] == 1
    assert summary["pair_validation"]["invalid_reasons"]["non_positive_preference_margin"] == 1
