import json
from pathlib import Path

import pytest

from fiir_crystal.io import write_json, write_jsonl
from scripts.collect_crystalformer_bulk_results import main


def _candidate(candidate_id: str, formula: str = "BaTiO3", *, dpo_eligible: bool = True) -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {"mode": "csp", "formula": formula, "spacegroup": None, "generation": {"top_k": "40"}},
        "dpo_eligible": dpo_eligible,
        "dpo_ineligible_reasons": [] if dpo_eligible else ["missing_raw_sequence"],
    }


def _pair(chosen: str, rejected: str, formula: str = "BaTiO3") -> dict:
    return {
        "pair_id": f"{formula}:{chosen}>{rejected}",
        "condition": {"mode": "csp", "formula": formula, "spacegroup": None, "generation": {"top_k": "40"}},
        "chosen_candidate_id": chosen,
        "rejected_candidate_id": rejected,
        "preference_type": "geometry_chemistry_only",
    }


def test_collect_crystalformer_bulk_results_summarizes_fake_completed_root(tmp_path) -> None:
    root = tmp_path / "bulk"
    audit_dir = root / "smoke" / "crystalformer_audit" / "BaTiO3"
    pref_dir = root / "smoke" / "dpo_preferences" / "BaTiO3"
    audit_dir.mkdir(parents=True)
    pref_dir.mkdir(parents=True)
    write_json(
        root / "bulk_plan.json",
        {"items": [{"formula": "BaTiO3"}, {"formula": "SrTiO3"}], "run_generation": True},
    )
    write_json(
        root / "bulk_summary.json",
        {
            "items": [
                {
                    "formula": "BaTiO3",
                    "status": "succeeded",
                    "smoke_summary": {
                        "candidate_count": 2,
                        "dpo_eligible_count": 2,
                        "preference_pair_count": 1,
                    },
                    "total_duration_seconds": 3.5,
                },
                {"formula": "SrTiO3", "status": "failed", "error": "generation_failed_returncode_1"},
            ],
            "timing": {"total_wall_seconds": 4.0},
        },
    )
    (root / "report.md").write_text("# report\n", encoding="utf-8")
    write_jsonl(audit_dir / "candidates.jsonl", [_candidate("c1"), _candidate("c2")])
    write_jsonl(audit_dir / "audit_candidates.jsonl", [_candidate("c1"), _candidate("c2")])
    write_json(audit_dir / "audit_summary.json", {"total_candidates": 2, "dpo_eligible_count": 2})
    write_jsonl(audit_dir / "failure_vectors.jsonl", [{"candidate_id": "c1"}, {"candidate_id": "c2"}])
    (audit_dir / "report.md").write_text("# audit\n", encoding="utf-8")
    write_jsonl(pref_dir / "preference_pairs.jsonl", [_pair("c1", "c2")])
    write_json(pref_dir / "preference_summary.json", {"pair_count": 1, "skip_reasons": {}})
    (pref_dir / "report.md").write_text("# prefs\n", encoding="utf-8")

    result = main(
        [
            "--output-roots",
            str(root),
            "--output-dir",
            str(tmp_path / "collection"),
            "--include-in-progress",
        ]
    )

    summary = result["summary"]
    assert summary["scanned_root_count"] == 1
    assert summary["formula_count"] == 2
    assert summary["completed_formula_count"] == 1
    assert summary["failed_formula_count"] == 1
    assert summary["total_candidates"] == 2
    assert summary["total_audit_candidates"] == 2
    assert summary["total_dpo_eligible"] == 2
    assert summary["total_preference_pairs"] == 1
    rows = [json.loads(line) for line in Path(result["files"]["formula_table_jsonl"]).read_text(encoding="utf-8").splitlines()]
    assert [row["formula"] for row in rows] == ["BaTiO3", "SrTiO3"]
    assert (tmp_path / "collection" / "report.md").exists()


def test_collect_reports_partial_and_malformed_artifacts(tmp_path) -> None:
    root = tmp_path / "partial"
    audit_dir = root / "crystalformer_audit" / "BaTiO3"
    audit_dir.mkdir(parents=True)
    write_json(root / "bulk_plan.json", {"items": [{"formula": "BaTiO3"}]})
    (audit_dir / "audit_candidates.jsonl").write_text('{"candidate_id": "ok", "composition": "BaTiO3"}\nnot-json\n', encoding="utf-8")

    result = main(
        [
            "--output-roots",
            str(root),
            "--output-dir",
            str(tmp_path / "collection"),
            "--include-in-progress",
        ]
    )

    summary = result["summary"]
    assert summary["in_progress_formula_count"] == 1
    assert summary["missing_artifact_count"] >= 1
    assert summary["corrupt_artifact_count"] >= 1
    errors = [json.loads(line) for line in Path(result["files"]["artifact_errors"]).read_text(encoding="utf-8").splitlines()]
    assert any(error["issue"] == "malformed_jsonl" for error in errors)
    assert any(error["issue"] == "missing_artifact" for error in errors)


def test_collect_counts_empty_artifacts_separately_from_corruption(tmp_path) -> None:
    root = tmp_path / "zero_pairs"
    pref_dir = root / "smoke" / "dpo_preferences" / "BaTiO3"
    pref_dir.mkdir(parents=True)
    write_json(
        root / "bulk_summary.json",
        {
            "items": [
                {
                    "formula": "BaTiO3",
                    "status": "succeeded",
                    "smoke_summary": {
                        "candidate_count": 5,
                        "dpo_eligible_count": 5,
                        "preference_pair_count": 0,
                    },
                }
            ]
        },
    )
    (pref_dir / "preference_pairs.jsonl").write_text("", encoding="utf-8")
    write_json(
        pref_dir / "preference_summary.json",
        {"pair_count": 0, "skip_reasons": {"no_comparable_margin": 10}},
    )

    result = main(
        [
            "--output-roots",
            str(root),
            "--output-dir",
            str(tmp_path / "collection"),
            "--include-in-progress",
        ]
    )

    summary = result["summary"]
    assert summary["empty_artifact_count"] == 1
    assert summary["corrupt_artifact_count"] == 0
    assert summary["total_preference_pairs"] == 0


def test_collect_strict_exits_on_artifact_errors(tmp_path) -> None:
    root = tmp_path / "partial"
    root.mkdir()
    (root / "bulk_plan.json").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="strict mode"):
        main(
            [
                "--output-roots",
                str(root),
                "--output-dir",
                str(tmp_path / "collection"),
                "--strict",
            ]
        )
