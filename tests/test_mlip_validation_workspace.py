import json
from pathlib import Path

import pytest

from fiir_crystal.io import read_jsonl, write_jsonl
from scripts.normalize_offline_validation_results import main as normalize_main
from scripts.run_local_mlip_validation import main as mlip_plan_main


def _candidate(candidate_id: str, formula: str = "BaTiO3") -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {
            "mode": "csp",
            "formula": formula,
            "spacegroup": None,
            "generation": {"source_checkpoint": "ckpt", "temperature": "1.0", "top_k": "40", "K": "40"},
        },
    }


def test_local_mlip_validation_dry_run_writes_plan_without_running(tmp_path) -> None:
    candidate_index = tmp_path / "audit_candidates.jsonl"
    write_jsonl(candidate_index, [_candidate("c1"), _candidate("c2")])
    output_dir = tmp_path / "mlip_plan"

    result = mlip_plan_main(
        [
            "--candidate-index",
            str(candidate_index),
            "--output-dir",
            str(output_dir),
            "--validator",
            "mace_mpa_0",
            "--validator",
            "chgnet_0_3_0",
            "--limit",
            "1",
        ]
    )

    summary = result["summary"]
    assert summary["run_mlip"] is False
    assert summary["runs_mlip"] is False
    assert summary["candidate_count"] == 1
    assert summary["planned_task_count"] == 2
    assert summary["validators"] == ["mace_mpa_0", "chgnet_0_3_0"]
    assert (output_dir / "mlip_validation_plan.json").exists()
    plan = json.loads((output_dir / "mlip_validation_plan.json").read_text(encoding="utf-8"))
    assert all(task["status"] == "planned_not_executed" for task in plan["tasks"])
    assert "normalize_offline_validation_results.py" in plan["normalization_command"]


def test_local_mlip_validation_run_flag_is_guarded(tmp_path) -> None:
    candidate_index = tmp_path / "audit_candidates.jsonl"
    write_jsonl(candidate_index, [_candidate("c1")])

    with pytest.raises(SystemExit, match="intentionally not implemented"):
        mlip_plan_main(
            [
                "--candidate-index",
                str(candidate_index),
                "--output-dir",
                str(tmp_path / "mlip_plan"),
                "--run-mlip",
            ]
        )


def test_fake_mlip_validation_example_normalizes(tmp_path) -> None:
    result = normalize_main(
        [
            "--input",
            "examples/mlip_validation/BaTiO3_fake_mlip_validation.jsonl",
            "--output-jsonl",
            str(tmp_path / "normalized" / "validation_results.jsonl"),
            "--output-summary",
            str(tmp_path / "normalized" / "normalization_summary.json"),
            "--report",
            str(tmp_path / "normalized" / "report.md"),
        ]
    )

    rows = read_jsonl(result["files"]["normalized_validation_results"])
    assert len(rows) == 2
    assert rows[0]["validator"] == "mace_mpa_0"
    assert result["summary"]["failed_or_incomplete_count"] == 1
    assert result["summary"]["f3_available_candidate_count"] == 1


def test_mlip_workspace_docs_keep_core_boundary_explicit() -> None:
    text = Path("docs/setup/mlip_validation_workspace.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    for required in [
        "does not run MACE",
        "no DFT execution",
        "no checkpoint or dataset downloads",
        "scripts/run_local_mlip_validation.py",
        "scripts/normalize_offline_validation_results.py",
        "F3 remains unavailable or unknown",
    ]:
        assert required in text
    assert "Optional MLIP Validation Workspace" in readme
    assert "does not install or run MACE" in readme
