import json
from pathlib import Path

import pytest

from scripts import run_mace_offline_validation as mace_runner


def test_raw_sequence_fallback_builds_structure_payload() -> None:
    row = {
        "candidate_id": "cf_001",
        "composition": "BaTiO3",
        "raw_sequence_fields": {
            "A": "[56, 22, 8, 8, 8, 0]",
            "X": "[[0, 0, 0], [0.5, 0.5, 0.5], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5], [0, 0, 0]]",
            "L": "[4.0, 4.0, 4.0, 90, 90, 90]",
        },
    }

    species, coords, lattice = mace_runner._structure_from_raw_sequence(row)

    assert species == ["Ba", "Ti", "O", "O", "O"]
    assert len(coords) == 5
    expected = [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]]
    assert [value for row in lattice for value in row] == pytest.approx(
        [value for row in expected for value in row]
    )


def test_dry_run_writes_no_fabricated_f3(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    model = tmp_path / "local_mace.model"
    output = tmp_path / "mace_validation_results.jsonl"
    summary = tmp_path / "mace_validation_summary.json"
    report = tmp_path / "report.md"
    model.write_text("fake-local-model", encoding="utf-8")
    candidates.write_text(
        json.dumps(
            {
                "candidate_id": "cf_001",
                "composition": "BaTiO3",
                "species": ["Ba", "Ti", "O", "O", "O"],
                "frac_coords": [[0, 0, 0], [0.5, 0.5, 0.5], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]],
                "lattice_matrix": [[4, 0, 0], [0, 4, 0], [0, 0, 4]],
                "condition": {"formula": "BaTiO3", "mode": "csp", "generation": {"top_k": "40"}},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = mace_runner.main(
        [
            "--candidates-jsonl",
            str(candidates),
            "--model-path",
            str(model),
            "--output-jsonl",
            str(output),
            "--output-summary",
            str(summary),
            "--report",
            str(report),
            "--dry-run",
        ]
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert result["summary"]["runs_mlip"] is False
    assert rows[0]["validation_status"] == "planned_not_executed"
    assert rows[0]["energy_above_hull"] is None
    assert rows[0]["is_stable"] is None
    assert rows[0]["metadata"]["energy_above_hull_status"] == "unavailable_without_local_hull_reference"
