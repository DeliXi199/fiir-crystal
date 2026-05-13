from pathlib import Path

import pytest

from fiir_crystal.io import read_json, write_jsonl
from scripts.build_f4_reference_pool_manifest import main as build_manifest_main
from scripts.check_f4_novelty_audit_ready import main as check_ready_main
from scripts.plan_f4_novelty_audit import main as plan_f4_main


def _candidate(candidate_id: str, formula: str = "BaTiO3") -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {"mode": "csp", "formula": formula, "spacegroup": None},
        "dpo_eligible": True,
        "f1_label": "pass",
        "f2_label": "pass",
    }


def _reference(reference_id: str, formula: str = "BaTiO3") -> dict:
    return {
        "reference_id": reference_id,
        "formula": formula,
        "source_database": "materials_project_snapshot",
        "structure": {"lattice": None, "species": []},
    }


def test_build_f4_reference_pool_manifest_enables_readiness(tmp_path: Path) -> None:
    candidate_index = tmp_path / "candidate_index.jsonl"
    output_dir = tmp_path / "f4"
    references_dir = output_dir / "references"
    mp_refs = references_dir / "materials_project_snapshot.structures.jsonl"
    train_refs = references_dir / "training_set_snapshot.structures.jsonl"
    write_jsonl(candidate_index, [_candidate("c1"), _candidate("c2")])
    write_jsonl(mp_refs, [_reference("mp-1"), _reference("mp-2", "SrTiO3")])
    write_jsonl(train_refs, [_reference("train-1")])
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

    result = build_manifest_main(
        [
            "--reference-source",
            f"materials_project_snapshot={mp_refs}",
            "--reference-source",
            f"training_set_snapshot={train_refs}",
            "--reference-pool-id",
            "reference_pool_v1",
            "--output-json",
            str(output_dir / "reference_pool_manifest.json"),
        ]
    )

    summary = result["summary"]
    assert summary["schema_version"] == "f4-reference-pool-manifest-v1"
    assert summary["example_manifest"] is False
    assert summary["total_reference_count"] == 3
    assert summary["reference_source_count"] == 2
    assert summary["duplicate_reference_id_count"] == 0
    assert len(summary["reference_sources"][0]["sha256"]) == 64
    manifest = read_json(output_dir / "reference_pool_manifest.json")
    assert manifest["reference_sources"][0]["reference_count"] == 2

    readiness = check_ready_main(["--plan-json", str(output_dir / "f4_audit_plan.json")])
    assert readiness["ready"] is True
    assert readiness["reference_pool"]["total_reference_count"] == 3


def test_build_f4_reference_pool_manifest_rejects_duplicate_reference_ids(tmp_path: Path) -> None:
    refs = tmp_path / "refs.jsonl"
    write_jsonl(refs, [_reference("mp-1"), _reference("mp-1")])

    with pytest.raises(SystemExit, match="duplicate reference_id"):
        build_manifest_main(
            [
                "--reference-source",
                f"materials_project_snapshot={refs}",
                "--output-json",
                str(tmp_path / "reference_pool_manifest.json"),
            ]
        )


def test_build_f4_reference_pool_manifest_rejects_missing_reference_ids(tmp_path: Path) -> None:
    refs = tmp_path / "refs.jsonl"
    write_jsonl(refs, [{"formula": "BaTiO3"}])

    with pytest.raises(SystemExit, match="rows without reference_id"):
        build_manifest_main(
            [
                "--reference-source",
                f"materials_project_snapshot={refs}",
                "--output-json",
                str(tmp_path / "reference_pool_manifest.json"),
            ]
        )


def test_build_f4_reference_pool_manifest_help_is_documented() -> None:
    text = Path("docs/setup/f4_reference_pool_workspace.md").read_text(encoding="utf-8")
    assert "scripts/build_f4_reference_pool_manifest.py" in text
    assert "reference_pool_manifest.json" in text
