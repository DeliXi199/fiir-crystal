import json
from pathlib import Path

import pytest

from fiir_crystal.io import JsonlFormatError, read_jsonl, write_jsonl
from fiir_crystal.validation import F4NoveltyAuditError
from scripts.import_f4_novelty_audit import main as import_f4_main


def _candidate(candidate_id: str, formula: str = "BaTiO3") -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {"mode": "csp", "formula": formula, "spacegroup": None},
        "evidence": {"f3_status": "unknown_unavailable"},
        "failure_vector": {
            "candidate_id": candidate_id,
            "f1_geometry": 0.0,
            "f2_chemistry": 0.0,
            "f3_stability": None,
            "metadata": {},
        },
    }


def _f4(candidate_id: str, score: float, nearest_reference_id: str = "mp-1") -> dict:
    return {
        "candidate_id": candidate_id,
        "f4_novelty_leakage": score,
        "nearest_reference_id": nearest_reference_id,
        "reference_source": "materials_project_snapshot",
        "match_type": "structure_matcher",
        "fingerprint_distance": round(max(0.0, 1.0 - score), 6),
        "confidence": 0.95,
        "reference_pool_id": "reference_pool_v1",
        "audit_run_id": "f4_test_run",
    }


def test_import_f4_novelty_audit_writes_joined_candidates_and_summary(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate_index.jsonl"
    f4_results = tmp_path / "f4_results.jsonl"
    output_dir = tmp_path / "f4_import"
    write_jsonl(candidates, [_candidate("c1"), _candidate("c2"), _candidate("c3")])
    write_jsonl(f4_results, [_f4("c1", 0.92, "mp-high"), _f4("c2", 0.03, "mp-low"), _f4("orphan", 0.4)])

    result = import_f4_main(
        [
            "--candidate-index",
            str(candidates),
            "--f4-results-jsonl",
            str(f4_results),
            "--output-dir",
            str(output_dir),
        ]
    )

    summary = result["summary"]
    assert summary["workflow"] == "f4_novelty_audit_import"
    assert summary["runs_structure_matcher"] is False
    assert summary["candidate_count"] == 3
    assert summary["f4_record_count"] == 3
    assert summary["matched_count"] == 2
    assert summary["missing_count"] == 1
    assert summary["orphan_count"] == 1
    assert summary["high_leakage_count"] == 1
    assert summary["missing_candidate_ids"] == ["c3"]
    assert summary["orphan_candidate_ids"] == ["orphan"]
    assert summary["score_stats"]["max"] == 0.92
    assert summary["score_bins"]["0.80-1.00"] == 1
    assert len(summary["input_provenance"]["f4_results_jsonl"]["sha256"]) == 64

    rows = read_jsonl(output_dir / "candidates_with_f4.jsonl")
    by_id = {row["candidate_id"]: row for row in rows}
    assert by_id["c1"]["f4_novelty_available"] is True
    assert by_id["c1"]["f4_novelty_leakage"] == 0.92
    assert by_id["c1"]["f4_leakage_risk_label"] == "high"
    assert by_id["c1"]["evidence"]["f4_novelty_audit"]["nearest_reference_id"] == "mp-high"
    assert by_id["c1"]["failure_vector"]["f4_novelty_leakage"] == 0.92
    assert by_id["c3"]["f4_status"] == "missing"
    assert by_id["c3"]["f4_novelty_available"] is False

    summary_file = json.loads((output_dir / "f4_import_summary.json").read_text(encoding="utf-8"))
    assert summary_file["output_files"]["report"] == str(output_dir / "f4_import_report.md")
    report = (output_dir / "f4_import_report.md").read_text(encoding="utf-8")
    assert "Does not run StructureMatcher" in report
    assert "c1: f4_novelty_leakage=0.92" in report


def test_import_f4_novelty_audit_rejects_duplicate_f4_ids(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate_index.jsonl"
    f4_results = tmp_path / "f4_results.jsonl"
    write_jsonl(candidates, [_candidate("c1")])
    write_jsonl(f4_results, [_f4("c1", 0.1), _f4("c1", 0.2)])

    with pytest.raises(F4NoveltyAuditError, match="duplicate_f4_candidate_id:c1"):
        import_f4_main(
            [
                "--candidate-index",
                str(candidates),
                "--f4-results-jsonl",
                str(f4_results),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )


def test_import_f4_novelty_audit_can_count_allowed_duplicates(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate_index.jsonl"
    f4_results = tmp_path / "f4_results.jsonl"
    write_jsonl(candidates, [_candidate("c1")])
    write_jsonl(f4_results, [_f4("c1", 0.1), _f4("c1", 0.2)])

    result = import_f4_main(
        [
            "--candidate-index",
            str(candidates),
            "--f4-results-jsonl",
            str(f4_results),
            "--output-dir",
            str(tmp_path / "out"),
            "--allow-duplicate-results",
        ]
    )

    assert result["summary"]["duplicate_result_count"] == 1
    rows = read_jsonl(tmp_path / "out" / "candidates_with_f4.jsonl")
    assert rows[0]["f4_novelty_leakage"] == 0.1


def test_import_f4_novelty_audit_rejects_malformed_jsonl(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate_index.jsonl"
    f4_results = tmp_path / "f4_results.jsonl"
    write_jsonl(candidates, [_candidate("c1")])
    f4_results.write_text('{"candidate_id": "c1"\n', encoding="utf-8")

    with pytest.raises(JsonlFormatError):
        import_f4_main(
            [
                "--candidate-index",
                str(candidates),
                "--f4-results-jsonl",
                str(f4_results),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )


def test_import_f4_novelty_audit_rejects_out_of_range_score(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate_index.jsonl"
    f4_results = tmp_path / "f4_results.jsonl"
    write_jsonl(candidates, [_candidate("c1")])
    write_jsonl(f4_results, [_f4("c1", 1.2)])

    with pytest.raises(F4NoveltyAuditError, match="f4_novelty_leakage_out_of_range"):
        import_f4_main(
            [
                "--candidate-index",
                str(candidates),
                "--f4-results-jsonl",
                str(f4_results),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )


def test_f4_novelty_audit_spec_documents_offline_boundary() -> None:
    text = Path("docs/specs/f4_novelty_leakage_audit.md").read_text(encoding="utf-8")
    assert "does not run StructureMatcher" in text
    assert "f4_novelty_leakage" in text
    assert "outputs/f4_novelty_import_1024_YYYYMMDD" in text
