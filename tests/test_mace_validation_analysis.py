import json
from pathlib import Path

from scripts.summarize_mace_validation_results import main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_mace_validation_analysis_summarizes_outliers_and_relaxation_candidates(tmp_path: Path) -> None:
    validation_jsonl = tmp_path / "mace_validation_results.jsonl"
    _write_jsonl(
        validation_jsonl,
        [
            {
                "candidate_id": "ba_good",
                "formula": "BaTiO3",
                "validation_status": "completed",
                "force_max": 1.5,
                "stress_max": 0.05,
                "metadata": {"mace_total_energy_eV_per_atom": -5.0},
            },
            {
                "candidate_id": "ba_bad",
                "formula": "BaTiO3",
                "validation_status": "completed",
                "force_max": 100.0,
                "stress_max": 0.25,
                "metadata": {"mace_total_energy_eV_per_atom": 10.0},
            },
            {
                "candidate_id": "sr_failed",
                "formula": "SrTiO3",
                "validation_status": "failed",
                "metadata": {"mace_error": "fixture failure"},
            },
            {
                "candidate_id": "sr_good",
                "formula": "SrTiO3",
                "validation_status": "completed",
                "force_max": 3.0,
                "stress_max": 0.1,
                "metadata": {"mace_total_energy_eV_per_atom": -4.0},
            },
        ],
    )

    result = main(
        [
            "--validation-jsonl",
            str(validation_jsonl),
            "--output-dir",
            str(tmp_path / "analysis"),
            "--relax-candidates-per-formula",
            "1",
            "--relax-force-max",
            "5.0",
            "--relax-stress-max",
            "0.2",
            "--high-force-threshold",
            "50.0",
            "--high-stress-threshold",
            "0.2",
        ]
    )

    summary_path = Path(result["files"]["summary"])
    outliers_path = Path(result["files"]["outliers_jsonl"])
    relaxation_path = Path(result["files"]["relaxation_candidates_jsonl"])
    summary = _read_json(summary_path)
    outliers = _read_jsonl(outliers_path)
    relaxation_candidates = _read_jsonl(relaxation_path)

    assert summary["row_count"] == 4
    assert summary["formula_count"] == 2
    assert summary["completed_count"] == 3
    assert summary["failed_count"] == 1
    assert summary["high_force_count"] == 1
    assert summary["high_stress_count"] == 1
    assert summary["relaxation_candidate_count"] == 2
    assert summary["f3_available_candidate_count"] == 0
    assert [row["candidate_id"] for row in outliers] == ["ba_bad"]
    assert [row["candidate_id"] for row in relaxation_candidates] == ["ba_good", "sr_good"]


def test_mace_validation_analysis_counts_only_explicit_f3_evidence(tmp_path: Path) -> None:
    validation_jsonl = tmp_path / "mace_validation_results.jsonl"
    _write_jsonl(
        validation_jsonl,
        [
            {
                "candidate_id": "mace_only",
                "formula": "BaZrO3",
                "validation_status": "completed",
                "force_max": 1.0,
                "stress_max": 0.1,
                "metadata": {"mace_total_energy_eV_per_atom": -6.0},
            },
            {
                "candidate_id": "with_hull",
                "formula": "BaZrO3",
                "validation_status": "completed",
                "force_max": 1.0,
                "stress_max": 0.1,
                "energy_above_hull": 0.05,
                "metadata": {"mace_total_energy_eV_per_atom": -6.1},
            },
        ],
    )

    result = main(
        [
            "--validation-jsonl",
            str(validation_jsonl),
            "--output-dir",
            str(tmp_path / "analysis"),
        ]
    )

    summary = _read_json(Path(result["files"]["summary"]))
    assert summary["f3_available_candidate_count"] == 1
