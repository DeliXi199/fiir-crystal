import json
from pathlib import Path

from scripts.import_offline_validation_and_build_dpo import main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _audit_row(candidate_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": "BaTiO3",
        "condition": {"mode": "csp", "formula": "BaTiO3", "spacegroup": None, "generation": {}},
        "dpo_eligible": True,
        "dpo_ineligible_reasons": [],
        "f1_label": "pass",
        "f2_label": "pass",
        "f3_label": "unknown",
        "failure_vector": {
            "candidate_id": candidate_id,
            "f1_geometry": 0.0,
            "f2_chemistry": 0.0,
            "f3_stability": None,
        },
        "evidence": {"f3_status": "unknown_unavailable"},
        "fiir_score": 0.0,
        "ranking_score": 1.0,
        "parse_status": "parsed_full_structure",
        "raw_sequence_status": "full",
        "raw_sequence_fields": {"g": "221", "W": "W", "A": "A", "X": "X", "L": "L"},
        "preference_type": "geometry_chemistry_only",
    }


def test_import_validation_and_rebuild_dpo_emits_stability_aware_pairs(tmp_path: Path) -> None:
    audit = tmp_path / "audit_candidates.jsonl"
    validation = tmp_path / "validation_results.jsonl"
    output_dir = tmp_path / "closed_loop"
    _write_jsonl(audit, [_audit_row("stable"), _audit_row("unstable")])
    _write_jsonl(
        validation,
        [
            {
                "candidate_id": "stable",
                "formula": "BaTiO3",
                "condition": {"mode": "csp", "formula": "BaTiO3", "spacegroup": None, "generation": {}},
                "validation_source": "local_mlip_mace_relaxation",
                "validation_status": "completed",
                "is_stable": True,
            },
            {
                "candidate_id": "unstable",
                "formula": "BaTiO3",
                "condition": {"mode": "csp", "formula": "BaTiO3", "spacegroup": None, "generation": {}},
                "validation_source": "local_mlip_mace_relaxation",
                "validation_status": "completed",
                "is_stable": False,
            },
        ],
    )

    result = main(
        [
            "--audit-candidates-jsonl",
            str(audit),
            "--validation-jsonl",
            str(validation),
            "--formula",
            "BaTiO3",
            "--output-dir",
            str(output_dir),
            "--fail-on-zero-stability-pairs",
        ]
    )

    assert result["summary"]["validation_import_summary"]["f3_available_count"] == 2
    assert result["summary"]["stability_aware_pair_count"] == 1
    pair = json.loads((output_dir / "dpo_preferences" / "preference_pairs.jsonl").read_text(encoding="utf-8"))
    assert pair["preference_type"] == "stability_aware_offline_validation"
    assert pair["metadata"]["stability_preference"] is True
    updated_rows = [
        json.loads(line)
        for line in (output_dir / "audit_candidates_with_validation.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {row["f3_label"] for row in updated_rows} == {"pass", "fail"}
