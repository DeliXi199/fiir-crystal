import json
from pathlib import Path

from scripts import build_mlip_ensemble_consensus as consensus


def _row(candidate_id: str, formula: str, stable: bool, energy: float) -> dict:
    return {
        "candidate_id": candidate_id,
        "formula": formula,
        "validation_status": "completed",
        "validator": "validator",
        "validation_source": "local_mlip_relaxation",
        "calibration_tier": "tier3_single_mlip",
        "is_stable": stable,
        "force_max": 0.01 if stable else 0.2,
        "stress_max": 0.1,
        "relaxed": True,
        "relaxation_converged": stable,
        "metadata": {"matgl_total_energy_eV_per_atom": energy},
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def test_consensus_requires_all_labels_to_agree(tmp_path: Path) -> None:
    left = tmp_path / "left.jsonl"
    middle = tmp_path / "middle.jsonl"
    right = tmp_path / "right.jsonl"
    output_dir = tmp_path / "consensus"
    _write_jsonl(left, [_row("a", "BaTiO3", True, -1.0), _row("b", "BaTiO3", False, -0.5)])
    _write_jsonl(middle, [_row("a", "BaTiO3", True, -1.1), _row("b", "BaTiO3", False, -0.4)])
    _write_jsonl(right, [_row("a", "BaTiO3", False, -0.9), _row("b", "BaTiO3", False, -0.6)])

    result = consensus.main(
        [
            "--validation",
            f"mace={left}",
            "--validation",
            f"chgnet={middle}",
            "--validation",
            f"matgl={right}",
            "--output-dir",
            str(output_dir),
        ]
    )

    rows = [json.loads(line) for line in (output_dir / "consensus_validation_results.jsonl").read_text().splitlines()]
    assert result["summary"]["overlap_count"] == 2
    assert result["summary"]["f3_available_candidate_count"] == 1
    assert result["summary"]["disagreement_or_unavailable_count"] == 1
    assert {row["candidate_id"]: row["is_stable"] for row in rows} == {"a": None, "b": False}
    assert rows[0]["metadata"]["ensemble_policy"] == "require_all_matching_binary_relaxation_proxy_labels"


def test_consensus_uses_intersection_only(tmp_path: Path) -> None:
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    output_dir = tmp_path / "consensus"
    _write_jsonl(left, [_row("a", "BaTiO3", True, -1.0), _row("left_only", "BaTiO3", True, -1.0)])
    _write_jsonl(right, [_row("a", "BaTiO3", True, -1.0), _row("right_only", "BaTiO3", True, -1.0)])

    result = consensus.main(
        [
            "--validation",
            f"mace={left}",
            "--validation",
            f"matgl={right}",
            "--output-dir",
            str(output_dir),
        ]
    )

    rows = [json.loads(line) for line in (output_dir / "consensus_validation_results.jsonl").read_text().splitlines()]
    assert result["summary"]["overlap_count"] == 1
    assert rows[0]["candidate_id"] == "a"
    assert rows[0]["calibration_tier"] == "tier2_mlip_ensemble"
