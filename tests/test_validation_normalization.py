import csv
import json
from pathlib import Path

import pytest

from fiir_crystal.io import read_jsonl, write_jsonl
from fiir_crystal.validation import (
    OfflineValidationImportConfig,
    import_offline_validation_to_audit_rows,
    read_offline_validation_jsonl,
)
from scripts.normalize_offline_validation_results import main


def _audit_row(candidate_id: str, formula: str = "BaTiO3") -> dict:
    generation = {"source_checkpoint": "ckpt", "temperature": "1.0", "top_k": "40", "K": "40"}
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {"mode": "csp", "formula": formula, "spacegroup": None, "generation": generation},
        "dpo_eligible": True,
        "f3_label": "unknown",
        "failure_vector": {"f1_geometry": 0.0, "f2_chemistry": 0.0, "f3_stability": None},
        "evidence": {"f3_status": "unknown_unavailable"},
        "raw_sequence_fields": {"g": "221", "W": "W", "A": "A", "X": "X", "L": "L"},
    }


def test_normalize_csv_preserves_unknowns_and_numeric_nulls(tmp_path) -> None:
    source = tmp_path / "validation.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "candidate_id",
                "formula",
                "validator",
                "validation_status",
                "energy_above_hull",
                "calibration_tier",
                "source_checkpoint",
                "top_k",
                "K",
                "temperature",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "candidate_id": "c1",
                "formula": "BaTiO3",
                "validator": "mace_mpa_0",
                "validation_status": "completed",
                "energy_above_hull": "",
                "calibration_tier": "unknown",
                "source_checkpoint": "ckpt",
                "top_k": "40",
                "K": "40",
                "temperature": "1.0",
            }
        )

    result = main(
        [
            "--input",
            str(source),
            "--input-format",
            "auto",
            "--output-jsonl",
            str(tmp_path / "normalized" / "validation_results.jsonl"),
            "--output-summary",
            str(tmp_path / "normalized" / "normalization_summary.json"),
            "--report",
            str(tmp_path / "normalized" / "report.md"),
        ]
    )

    rows = read_jsonl(result["files"]["normalized_validation_results"])
    assert len(rows) == 1
    assert rows[0]["energy_above_hull"] is None
    assert rows[0]["e_above_hull"] is None
    assert rows[0]["calibration_tier"] == "unknown"
    assert rows[0]["condition"]["generation"]["source_checkpoint"] == "ckpt"
    assert result["summary"]["f3_available_candidate_count"] == 0
    assert (tmp_path / "normalized" / "normalized_validation_results.jsonl").exists()


def test_normalized_output_feeds_existing_offline_import_path(tmp_path) -> None:
    source = tmp_path / "validation.jsonl"
    generation = {"source_checkpoint": "ckpt", "temperature": "1.0", "top_k": "40", "K": "40"}
    write_jsonl(
        source,
        [
            {
                "candidate_id": "good",
                "formula": "BaTiO3",
                "validator": "mace_mpa_0",
                "validation_source": "local_mlip",
                "validation_status": "completed",
                "energy_above_hull": 0.02,
                "calibration_tier": "tier3_single_mlip",
                "generation_condition": generation,
            },
            {
                "candidate_id": "failed",
                "formula": "BaTiO3",
                "validator": "chgnet",
                "validation_source": "local_mlip",
                "validation_status": "failed",
                "error_reason": "relaxation did not converge",
                "generation_condition": generation,
            },
        ],
    )

    result = main(
        [
            "--input",
            str(source),
            "--output-jsonl",
            str(tmp_path / "normalized" / "validation_results.jsonl"),
            "--output-summary",
            str(tmp_path / "normalized" / "normalization_summary.json"),
            "--report",
            str(tmp_path / "normalized" / "report.md"),
        ]
    )

    validation_records = read_offline_validation_jsonl(result["files"]["normalized_validation_results"])
    updated, summary = import_offline_validation_to_audit_rows(
        [_audit_row("good"), _audit_row("failed")],
        validation_records,
        OfflineValidationImportConfig(formula="BaTiO3"),
    )

    by_id = {row["candidate_id"]: row for row in updated}
    assert summary.f3_available_count == 1
    assert summary.validation_error_count == 1
    assert by_id["good"]["f3_validation_available"] is True
    assert by_id["failed"]["f3_validation_available"] is False
    assert by_id["failed"]["validation_status"] == "validation_error"


def test_candidate_index_reports_unmatched_and_formula_mismatch(tmp_path) -> None:
    source = tmp_path / "validation.json"
    source.write_text(
        json.dumps(
            [
                {
                    "candidate_id": "known",
                    "formula": "SrTiO3",
                    "validation_source": "local_mlip",
                    "validation_status": "completed",
                    "energy_above_hull": 0.1,
                },
                {
                    "candidate_id": "missing",
                    "formula": "BaTiO3",
                    "validation_source": "local_mlip",
                    "validation_status": "completed",
                    "energy_above_hull": 0.1,
                },
            ]
        ),
        encoding="utf-8",
    )
    index = tmp_path / "candidate_index.jsonl"
    write_jsonl(index, [{"candidate_id": "known", "composition": "BaTiO3"}])

    result = main(
        [
            "--input",
            str(source),
            "--input-format",
            "json",
            "--candidate-index",
            str(index),
            "--output-jsonl",
            str(tmp_path / "normalized" / "validation_results.jsonl"),
            "--output-summary",
            str(tmp_path / "normalized" / "normalization_summary.json"),
            "--report",
            str(tmp_path / "normalized" / "report.md"),
        ]
    )

    assert result["summary"]["unmatched_candidate_id_count"] == 1
    assert result["summary"]["formula_mismatch_count"] == 1
    unmatched = read_jsonl(result["files"]["unmatched_validation_rows"])
    assert {row["reason"] for row in unmatched} == {"candidate_not_found", "formula_mismatch"}


def test_strict_normalization_exits_on_blocking_index_issues(tmp_path) -> None:
    source = tmp_path / "validation.jsonl"
    write_jsonl(
        source,
        [
            {
                "candidate_id": "missing",
                "formula": "BaTiO3",
                "validation_source": "local_mlip",
                "validation_status": "completed",
                "energy_above_hull": 0.1,
            }
        ],
    )
    index = tmp_path / "candidate_index.jsonl"
    write_jsonl(index, [{"candidate_id": "other", "composition": "BaTiO3"}])

    with pytest.raises(SystemExit, match="strict normalization"):
        main(
            [
                "--input",
                str(source),
                "--candidate-index",
                str(index),
                "--output-jsonl",
                str(tmp_path / "normalized" / "validation_results.jsonl"),
                "--output-summary",
                str(tmp_path / "normalized" / "normalization_summary.json"),
                "--report",
                str(tmp_path / "normalized" / "report.md"),
                "--strict",
            ]
        )


def test_missing_required_fields_are_not_normalized(tmp_path) -> None:
    source = tmp_path / "bad.json"
    source.write_text(json.dumps({"formula": "BaTiO3", "validation_source": "local_mlip"}), encoding="utf-8")

    result = main(
        [
            "--input",
            str(source),
            "--output-jsonl",
            str(tmp_path / "normalized" / "validation_results.jsonl"),
            "--output-summary",
            str(tmp_path / "normalized" / "normalization_summary.json"),
            "--report",
            str(tmp_path / "normalized" / "report.md"),
        ]
    )

    assert result["summary"]["normalized_row_count"] == 0
    assert result["summary"]["missing_required_field_count"] == 1
