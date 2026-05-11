import json
from pathlib import Path

import pytest

from fiir_crystal.io import write_json, write_jsonl
from scripts.check_crystalformer_bulk_artifacts import main


SEQUENCE = {"g": "221", "W": "W", "A": "A", "X": "X", "L": "L"}


def _audit_row(
    candidate_id: str,
    formula: str,
    *,
    generation: dict | None = None,
    f3_label: str = "unknown",
    f3_validation_available: bool = False,
    validation_status: str = "not_provided",
    offline_validation: dict | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {
            "mode": "csp",
            "formula": formula,
            "spacegroup": None,
            "generation": generation or {"top_k": "40"},
        },
        "f3_label": f3_label,
        "failure_vector": {
            "f1_geometry": 0.0,
            "f2_chemistry": 0.0,
            "f3_stability": None,
            "metadata": {"f3_status": "unknown_unavailable"},
        },
        "evidence": {"f3_status": "unknown_unavailable"},
        "dpo_eligible": True,
        "f3_validation_available": f3_validation_available,
        "validation_status": validation_status,
        "offline_validation": offline_validation,
        "raw_sequence_fields": SEQUENCE,
    }


def _pair(chosen: str, rejected: str, formula: str = "BaTiO3", *, generation: dict | None = None) -> dict:
    return {
        "pair_id": f"{formula}:{chosen}>{rejected}",
        "condition": {
            "mode": "csp",
            "formula": formula,
            "spacegroup": None,
            "generation": generation or {"top_k": "40"},
        },
        "chosen_candidate_id": chosen,
        "rejected_candidate_id": rejected,
        "chosen_sequence": SEQUENCE,
        "rejected_sequence": SEQUENCE,
        "chosen_score": 0.0,
        "rejected_score": 0.2,
        "preference_margin": 0.2,
        "preference_type": "geometry_chemistry_only",
        "chosen_failure_vector": {"f1_geometry": 0.0, "f2_chemistry": 0.0, "f3_stability": None},
        "rejected_failure_vector": {"f1_geometry": 0.2, "f2_chemistry": 0.0, "f3_stability": None},
    }


def _write_audit(root: Path, formula: str, rows: list[dict]) -> None:
    audit_dir = root / "crystalformer_audit" / formula
    audit_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(audit_dir / "audit_candidates.jsonl", rows)
    write_jsonl(audit_dir / "candidates.jsonl", rows)
    write_json(audit_dir / "audit_summary.json", {"total_candidates": len(rows), "dpo_eligible_count": len(rows)})
    write_jsonl(audit_dir / "failure_vectors.jsonl", [row["failure_vector"] for row in rows])
    (audit_dir / "report.md").write_text("# audit\n", encoding="utf-8")


def _write_preferences(root: Path, formula: str, pairs: list[dict], summary: dict | None = None) -> None:
    pref_dir = root / "dpo_preferences" / formula
    pref_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(pref_dir / "preference_pairs.jsonl", pairs)
    write_json(pref_dir / "preference_summary.json", summary or {"pair_count": len(pairs), "skip_reasons": {}})
    (pref_dir / "report.md").write_text("# prefs\n", encoding="utf-8")


def _critical_checks(result: dict) -> set[str]:
    return {
        failure["check"]
        for failure in (item.to_dict() for item in result["failures"])
        if failure["severity"] == "critical"
    }


def test_qa_detects_cross_formula_pairs(tmp_path) -> None:
    root = tmp_path / "qa"
    _write_audit(root, "BaTiO3", [_audit_row("chosen", "BaTiO3")])
    _write_audit(root, "SrTiO3", [_audit_row("rejected", "SrTiO3")])
    _write_preferences(root, "BaTiO3", [_pair("chosen", "rejected", "BaTiO3")])

    result = main(["--input-roots", str(root), "--output-dir", str(tmp_path / "out")])

    checks = _critical_checks(result)
    assert "cross_formula_pair" in checks
    assert "formula_mismatch" in checks
    assert result["summary"]["critical_count"] >= 1


def test_qa_detects_missing_pair_candidate_ids(tmp_path) -> None:
    root = tmp_path / "qa"
    _write_audit(root, "BaTiO3", [_audit_row("rejected", "BaTiO3")])
    _write_preferences(root, "BaTiO3", [_pair("missing", "rejected", "BaTiO3")])

    result = main(["--input-roots", str(root), "--output-dir", str(tmp_path / "out")])

    assert "missing_chosen_candidate" in _critical_checks(result)


def test_qa_detects_fabricated_f3_labels(tmp_path) -> None:
    root = tmp_path / "qa"
    _write_audit(root, "BaTiO3", [_audit_row("stable_without_validation", "BaTiO3", f3_label="pass")])

    result = main(["--input-roots", str(root), "--output-dir", str(tmp_path / "out")])

    assert "fabricated_f3_or_stability" in _critical_checks(result)


def test_qa_detects_malformed_jsonl_and_fail_on_critical(tmp_path) -> None:
    root = tmp_path / "qa"
    pref_dir = root / "dpo_preferences" / "BaTiO3"
    pref_dir.mkdir(parents=True)
    (pref_dir / "preference_pairs.jsonl").write_text("not-json\n", encoding="utf-8")
    write_json(pref_dir / "preference_summary.json", {"pair_count": 1, "skip_reasons": {}})
    (pref_dir / "report.md").write_text("# prefs\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="critical"):
        main(["--input-roots", str(root), "--output-dir", str(tmp_path / "out"), "--fail-on-critical"])

    result = main(["--input-roots", str(root), "--output-dir", str(tmp_path / "out2")])
    assert "malformed_jsonl" in _critical_checks(result)


def test_qa_allows_documented_zero_pair_cases(tmp_path) -> None:
    root = tmp_path / "qa"
    _write_preferences(
        root,
        "BaTiO3",
        [],
        {"pair_count": 0, "skip_reasons": {"no_comparable_margin": 2}},
    )

    result = main(["--input-roots", str(root), "--output-dir", str(tmp_path / "out")])

    assert "zero_preference_pairs" not in _critical_checks(result)
    assert result["summary"]["warning_count"] >= 1


def test_qa_reports_partial_roots_as_warning_or_strict_critical(tmp_path) -> None:
    root = tmp_path / "partial"
    root.mkdir()
    write_json(root / "bulk_plan.json", {"items": [{"formula": "BaTiO3"}]})

    result = main(["--input-roots", str(root), "--output-dir", str(tmp_path / "out")])
    warnings = {failure.check for failure in result["failures"] if failure.severity == "warning"}
    assert "partial_or_in_progress_root" in warnings

    strict = main(["--input-roots", str(root), "--output-dir", str(tmp_path / "strict"), "--strict"])
    assert "partial_or_in_progress_root" in _critical_checks(strict)
