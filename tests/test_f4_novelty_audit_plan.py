from pathlib import Path

import pytest

from fiir_crystal.io import read_json, read_jsonl, write_json, write_jsonl
from scripts.check_f4_novelty_audit_ready import main as check_ready_main
from scripts.plan_f4_novelty_audit import main as plan_f4_main


def _candidate(
    candidate_id: str,
    formula: str = "BaTiO3",
    *,
    f1_label: str = "pass",
    f2_label: str = "pass",
    dpo_eligible: bool = True,
    ranking_score: float = 1.0,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {"mode": "csp", "formula": formula, "spacegroup": None},
        "dpo_eligible": dpo_eligible,
        "f1_label": f1_label,
        "f2_label": f2_label,
        "ranking_score": ranking_score,
        "fiir_score": 1.0 - ranking_score,
        "raw_sequence_fields": {"A": "[56, 22, 8, 8, 8]", "L": "[4, 4, 4, 90, 90, 90]"},
        "species": ["Ba", "Ti", "O"],
        "frac_coords": [[0.0, 0.0, 0.0]],
        "lattice_matrix": [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]],
    }


def test_plan_f4_novelty_audit_filters_and_shards_tasks(tmp_path: Path) -> None:
    candidate_index = tmp_path / "candidate_index.jsonl"
    output_dir = tmp_path / "f4_plan"
    write_jsonl(
        candidate_index,
        [
            _candidate("c1", ranking_score=0.2),
            _candidate("c2", ranking_score=0.9),
            _candidate("bad_f1", f1_label="fail"),
            _candidate("bad_f2", f2_label="fail"),
            _candidate("not_dpo", dpo_eligible=False),
        ],
    )

    result = plan_f4_main(
        [
            "--candidate-index",
            str(candidate_index),
            "--output-dir",
            str(output_dir),
            "--shard-count",
            "2",
            "--sort",
            "ranking",
            "--require-dpo-eligible",
            "--require-f1-pass",
            "--require-f2-pass",
        ]
    )

    summary = result["summary"]
    assert summary["workflow"] == "f4_novelty_audit_plan"
    assert summary["runs_structure_matcher"] is False
    assert summary["candidate_input_count"] == 5
    assert summary["selected_task_count"] == 2
    assert summary["skipped_reason_counts"] == {
        "f1_not_pass": 1,
        "f2_not_pass": 1,
        "not_dpo_eligible": 1,
    }
    assert summary["shard_count"] == 2

    tasks = read_jsonl(output_dir / "f4_audit_tasks.jsonl")
    assert [row["candidate_id"] for row in tasks] == ["c2", "c1"]
    assert {row["schema_version"] for row in tasks} == {"f4-audit-task-v1"}
    assert tasks[0]["reference_pool_manifest"] == str(output_dir / "reference_pool_manifest.json")
    assert tasks[0]["candidate_snapshot"]["raw_sequence_fields"]["A"] == "[56, 22, 8, 8, 8]"
    assert tasks[0]["candidate_snapshot"]["species"] == ["Ba", "Ti", "O"]
    assert tasks[0]["candidate_snapshot"]["lattice_matrix"][0] == [4.0, 0.0, 0.0]
    assert len(read_jsonl(output_dir / "shards" / "f4_audit_tasks_shard_0000.jsonl")) == 1
    assert len(read_jsonl(output_dir / "shards" / "f4_audit_tasks_shard_0001.jsonl")) == 1
    manifest = read_json(output_dir / "reference_pool_manifest.example.json")
    assert manifest["example_manifest"] is True


def test_plan_f4_novelty_audit_rejects_duplicate_candidate_ids(tmp_path: Path) -> None:
    candidate_index = tmp_path / "candidate_index.jsonl"
    write_jsonl(candidate_index, [_candidate("c1"), _candidate("c1")])

    with pytest.raises(SystemExit, match="duplicate candidate_id"):
        plan_f4_main(
            [
                "--candidate-index",
                str(candidate_index),
                "--output-dir",
                str(tmp_path / "f4_plan"),
            ]
        )


def test_check_f4_novelty_audit_ready_requires_real_manifest(tmp_path: Path) -> None:
    candidate_index = tmp_path / "candidate_index.jsonl"
    output_dir = tmp_path / "f4_plan"
    write_jsonl(candidate_index, [_candidate("c1"), _candidate("c2")])
    plan_f4_main(
        [
            "--candidate-index",
            str(candidate_index),
            "--output-dir",
            str(output_dir),
            "--shard-count",
            "2",
        ]
    )

    not_ready = check_ready_main(["--plan-json", str(output_dir / "f4_audit_plan.json")])
    assert not_ready["ready"] is False
    assert not_ready["reference_pool"]["issues"] == [
        f"missing_reference_manifest:{output_dir / 'reference_pool_manifest.json'}"
    ]

    reference_file = output_dir / "references" / "materials_project_snapshot.structures.jsonl"
    write_jsonl(reference_file, [{"reference_id": "mp-1", "formula": "BaTiO3"}])
    real_manifest = output_dir / "reference_pool_manifest.json"
    write_json(
        real_manifest,
        {
            "schema_version": "f4-reference-pool-manifest-v1",
            "reference_pool_id": "reference_pool_v1",
            "example_manifest": False,
            "created_time_utc": "2026-05-13T00:00:00+00:00",
            "total_reference_count": 1,
            "reference_sources": [
                {
                    "name": "materials_project_snapshot",
                    "path": str(reference_file),
                    "format": "structure_jsonl",
                    "reference_count": 1,
                    "sha256": None,
                }
            ],
        },
    )

    ready = check_ready_main(
        [
            "--plan-json",
            str(output_dir / "f4_audit_plan.json"),
            "--reference-manifest",
            str(real_manifest),
            "--output-json",
            str(output_dir / "readiness_summary.json"),
        ]
    )
    assert ready["ready"] is True
    assert ready["tasks"]["row_count"] == 2
    assert ready["shards"]["row_count"] == 2
    assert ready["reference_pool"]["total_reference_count"] == 1
    assert (output_dir / "readiness_summary.json").exists()


def test_f4_reference_pool_workspace_docs_keep_core_boundary_explicit() -> None:
    text = Path("docs/setup/f4_reference_pool_workspace.md").read_text(encoding="utf-8")
    assert "does not run StructureMatcher" in text
    assert "reference_pool_manifest.example.json" in text
    assert "scripts/plan_f4_novelty_audit.py" in text
    assert "scripts/check_f4_novelty_audit_ready.py" in text
    assert "scripts/import_f4_novelty_audit.py" in text
