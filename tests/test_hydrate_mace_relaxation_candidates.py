import json
from pathlib import Path

import pytest

from scripts.hydrate_mace_relaxation_candidates import main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_hydrate_mace_relaxation_candidates_preserves_triage_order(tmp_path: Path) -> None:
    full_candidates = tmp_path / "selected_candidates.jsonl"
    relaxation_candidates = tmp_path / "relaxation_candidates.jsonl"
    index = tmp_path / "candidate_index.jsonl"
    output_dir = tmp_path / "relax_input"
    _write_jsonl(
        full_candidates,
        [
            {
                "candidate_id": "cf_001",
                "composition": "BaTiO3",
                "species": ["Ba", "Ti", "O", "O", "O"],
                "frac_coords": [[0, 0, 0]],
                "lattice_matrix": [[4, 0, 0], [0, 4, 0], [0, 0, 4]],
                "metadata": {"source": "fixture"},
            },
            {
                "candidate_id": "cf_002",
                "composition": "SrTiO3",
                "species": ["Sr", "Ti", "O", "O", "O"],
                "frac_coords": [[0, 0, 0]],
                "lattice_matrix": [[4, 0, 0], [0, 4, 0], [0, 0, 4]],
            },
        ],
    )
    _write_jsonl(
        relaxation_candidates,
        [
            {"candidate_id": "cf_002", "formula": "SrTiO3", "force_max": 0.2, "reasons": ["relaxation_candidate"]},
            {"candidate_id": "cf_001", "formula": "BaTiO3", "force_max": 0.1, "stress_max": 0.01},
        ],
    )
    _write_jsonl(
        index,
        [
            {"candidate_id": "cf_001", "composition": "BaTiO3"},
            {"candidate_id": "cf_002", "composition": "SrTiO3"},
        ],
    )

    result = main(
        [
            "--relaxation-candidates-jsonl",
            str(relaxation_candidates),
            "--candidate-jsonl",
            str(full_candidates),
            "--candidate-index-jsonl",
            str(index),
            "--output-dir",
            str(output_dir),
            "--strict",
        ]
    )

    hydrated = _read_jsonl(output_dir / "relaxation_candidates_full.jsonl")
    index_rows = _read_jsonl(output_dir / "candidate_index.jsonl")
    assert result["summary"]["hydrated_candidate_count"] == 2
    assert [row["candidate_id"] for row in hydrated] == ["cf_002", "cf_001"]
    assert hydrated[0]["metadata"]["mace_relaxation_selection"]["force_max"] == 0.2
    assert hydrated[1]["metadata"]["source"] == "fixture"
    assert [row["candidate_id"] for row in index_rows] == ["cf_002", "cf_001"]
    assert result["summary"]["formula_counts"] == {"BaTiO3": 1, "SrTiO3": 1}


def test_hydrate_mace_relaxation_candidates_strict_fails_on_missing_id(tmp_path: Path) -> None:
    full_candidates = tmp_path / "selected_candidates.jsonl"
    relaxation_candidates = tmp_path / "relaxation_candidates.jsonl"
    _write_jsonl(full_candidates, [{"candidate_id": "known", "composition": "BaTiO3"}])
    _write_jsonl(relaxation_candidates, [{"candidate_id": "missing", "formula": "BaTiO3"}])

    with pytest.raises(SystemExit, match="strict hydration"):
        main(
            [
                "--relaxation-candidates-jsonl",
                str(relaxation_candidates),
                "--candidate-jsonl",
                str(full_candidates),
                "--output-dir",
                str(tmp_path / "relax_input"),
                "--strict",
            ]
        )
