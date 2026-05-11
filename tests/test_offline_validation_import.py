import json
from pathlib import Path

from fiir_crystal.io import read_jsonl
from scripts.check_offline_validation_import import main as check_validation_main
from scripts.run_crystalformer_smoke_pipeline import main as smoke_main


FAKE_RAW_DIR = Path("examples/crystalformer_raw/BaTiO3_fake")
FAKE_VALIDATION = Path("examples/crystalformer_validation/BaTiO3_fake_validation.jsonl")


def _run_fake_audit(tmp_path):
    output_root = tmp_path / "smoke"
    smoke_main(
        [
            "--input-dir",
            str(FAKE_RAW_DIR),
            "--formula",
            "BaTiO3",
            "--output-root",
            str(output_root),
            "--parser-backend",
            "none",
        ]
    )
    return output_root / "crystalformer_audit" / "BaTiO3" / "audit_candidates.jsonl"


def test_check_offline_validation_import_reports_join_reasons(tmp_path) -> None:
    audit_path = _run_fake_audit(tmp_path)

    result = check_validation_main(
        [
            "--audit-candidates-jsonl",
            str(audit_path),
            "--validation-jsonl",
            str(FAKE_VALIDATION),
            "--formula",
            "BaTiO3",
            "--output-dir",
            str(tmp_path / "validation_check"),
        ]
    )

    summary = result["summary"]
    assert summary["validation_record_count"] == 6
    assert summary["matched_count"] == 3
    assert summary["f3_available_count"] == 2
    assert summary["validation_error_count"] == 1
    assert summary["skip_reasons"]["candidate_not_found"] == 1
    assert summary["skip_reasons"]["formula_mismatch"] == 1
    assert summary["skip_reasons"]["condition_mismatch"] == 1
    assert (tmp_path / "validation_check" / "validation_import_summary.json").exists()


def test_smoke_pipeline_with_offline_validation_updates_f3_and_dpo(tmp_path) -> None:
    output_root = tmp_path / "validated_smoke"

    result = smoke_main(
        [
            "--input-dir",
            str(FAKE_RAW_DIR),
            "--formula",
            "BaTiO3",
            "--output-root",
            str(output_root),
            "--parser-backend",
            "none",
            "--offline-validation-jsonl",
            str(FAKE_VALIDATION),
        ]
    )

    summary = result["summary"]
    assert summary["f3_validation"] == "imported_offline_results"
    assert summary["offline_validation_imported"] is True
    assert summary["validation_import_summary"]["f3_available_count"] == 2
    assert summary["f3_status_counts"] == {"fail": 1, "pass": 1, "unknown": 3}
    assert summary["preference_pair_count"] == 1

    audit_rows = read_jsonl(output_root / "crystalformer_audit" / "BaTiO3" / "audit_candidates.jsonl")
    by_id = {row["candidate_id"]: row for row in audit_rows}
    assert by_id["cf_fake_good_001"]["f3_validation_available"] is True
    assert by_id["cf_fake_good_001"]["f3_label"] == "pass"
    assert by_id["cf_fake_overlap_002"]["f3_label"] == "fail"
    assert by_id["cf_fake_equal_003"]["validation_status"] == "validation_error"
    assert by_id["cf_fake_equal_003"]["f3_validation_available"] is False

    pair_path = output_root / "dpo_preferences" / "BaTiO3" / "preference_pairs.jsonl"
    pairs = [json.loads(line) for line in pair_path.read_text(encoding="utf-8").splitlines()]
    assert len(pairs) == 1
    assert pairs[0]["preference_type"] == "stability_aware_offline_validation"
    assert "offline_validation_stability_signal" in pairs[0]["preference_reason"]
    assert pairs[0]["metadata"]["stability_preference"] is True

    provenance = json.loads(Path(result["files"]["provenance"]).read_text(encoding="utf-8"))
    assert provenance["offline_validation"]["record_count"] == 6
    assert len(provenance["offline_validation"]["sha256"]) == 64


def test_no_validation_keeps_f3_unknown(tmp_path) -> None:
    output_root = tmp_path / "unvalidated_smoke"

    result = smoke_main(
        [
            "--input-dir",
            str(FAKE_RAW_DIR),
            "--formula",
            "BaTiO3",
            "--output-root",
            str(output_root),
            "--parser-backend",
            "none",
        ]
    )

    assert result["summary"]["f3_validation"] == "unavailable"
    assert result["summary"]["f3_status_counts"] == {"unknown": 5}
