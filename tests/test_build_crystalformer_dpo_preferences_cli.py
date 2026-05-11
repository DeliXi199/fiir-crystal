import json

from scripts.build_crystalformer_dpo_preferences import main


def _write_audit(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _row(candidate_id: str, score: float) -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": "BaTiO3",
        "source_format": "crystalformer_raw_csv",
        "parse_status": "parsed_full_structure",
        "raw_sequence_status": "full",
        "f1_label": "pass",
        "f2_label": "pass",
        "f3_label": "unknown",
        "failure_vector": {"f1_geometry": score, "f2_chemistry": 0.0, "f3_stability": None},
        "evidence": {},
        "fiir_score": score,
        "ranking_score": 1.0 - score,
        "dpo_eligible": True,
        "dpo_ineligible_reasons": [],
        "preference_type": "geometry_chemistry_only",
        "condition": {"mode": "csp", "formula": "BaTiO3", "spacegroup": None},
        "raw_sequence_fields": {"g": "221", "W": "W", "A": "A", "X": "X", "L": "L"},
    }


def test_build_crystalformer_dpo_preferences_cli_writes_outputs(tmp_path) -> None:
    audit_path = tmp_path / "audit" / "audit_candidates.jsonl"
    output_dir = tmp_path / "prefs"
    _write_audit(audit_path, [_row("chosen", 0.0), _row("rejected", 0.25)])

    result = main(
        [
            "--audit-candidates-jsonl",
            str(audit_path),
            "--formula",
            "BaTiO3",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result["summary"]["pair_count"] == 1
    assert (output_dir / "preference_pairs.jsonl").exists()
    assert (output_dir / "preference_summary.json").exists()
    assert (output_dir / "report.md").exists()
    pair = json.loads((output_dir / "preference_pairs.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert pair["chosen_candidate_id"] == "chosen"
    assert pair["preference_type"] == "geometry_chemistry_only"
    summary = json.loads((output_dir / "preference_summary.json").read_text(encoding="utf-8"))
    assert summary["train_dpo"] is False


def test_build_crystalformer_dpo_preferences_cli_dry_run(tmp_path, capsys) -> None:
    output_dir = tmp_path / "prefs"

    summary = main(
        [
            "--audit-dir",
            str(tmp_path / "audit"),
            "--formula",
            "BaTiO3",
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert "CrystalFormer DPO preference builder dry run" in captured.out
    assert summary["dry_run"] is True
    assert not output_dir.exists()
