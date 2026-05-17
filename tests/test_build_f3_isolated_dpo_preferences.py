import json
from pathlib import Path

from scripts import build_f3_isolated_dpo_preferences as f3_pairs


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _audit_row(candidate_id: str, *, f1: float = 0.0, f2: float = 0.0) -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": "BaTiO3",
        "condition": {
            "mode": "csp",
            "formula": "BaTiO3",
            "spacegroup": None,
            "generation": {"source_model": "fixture"},
        },
        "dpo_eligible": True,
        "parse_status": "parsed_full_structure",
        "raw_sequence_fields": {
            "g": "221",
            "W": "[1, 1, 1]",
            "A": "[56, 22, 8]",
            "X": "[[0, 0, 0]]",
            "L": "[4, 4, 4, 90, 90, 90]",
        },
        "failure_vector": {
            "candidate_id": candidate_id,
            "f1_geometry": f1,
            "f2_chemistry": f2,
            "f3_stability": None,
        },
    }


def _consensus_row(
    candidate_id: str,
    *,
    forces: tuple[float | None, float | None, float | None],
    converged: tuple[bool | None, bool | None, bool | None],
) -> dict:
    force_values = [value for value in forces if value is not None]
    return {
        "candidate_id": f"after64__{candidate_id}",
        "formula": "BaTiO3",
        "validation_status": "completed",
        "validator": "mace+chgnet+matgl",
        "validation_source": "local_mlip_mace_chgnet_matgl_relaxation_consensus_fixture",
        "force_max": max(force_values) if force_values else None,
        "stress_max": 0.1,
        "relaxation_converged": all(value is True for value in converged),
        "metadata": {
            "vote_pattern": "mace:force|chgnet:force|matgl:force",
            "mace_force_max": forces[0],
            "chgnet_force_max": forces[1],
            "matgl_force_max": forces[2],
            "mace_relaxation_converged": converged[0],
            "chgnet_relaxation_converged": converged[1],
            "matgl_relaxation_converged": converged[2],
            "mace_stress_max": 0.11,
            "chgnet_stress_max": 0.12,
            "matgl_stress_max": 0.13,
            "mace_energy_eV_per_atom": -1.1,
            "chgnet_energy_eV_per_atom": -1.2,
            "matgl_energy_eV_per_atom": -1.3,
        },
    }


def test_f3_isolated_builder_controls_f1_f2_and_uses_prefixed_consensus_ids(tmp_path: Path) -> None:
    audit = tmp_path / "audit_candidates.jsonl"
    consensus = tmp_path / "consensus.jsonl"
    output_dir = tmp_path / "artifact"
    _write_jsonl(
        audit,
        [
            _audit_row("good"),
            _audit_row("near_miss"),
            _audit_row("geometry_bad", f1=0.2),
            _audit_row("missing_force"),
        ],
    )
    _write_jsonl(
        consensus,
        [
            _consensus_row(
                "good",
                forces=(0.02, 0.03, 0.04),
                converged=(True, True, True),
            ),
            _consensus_row(
                "near_miss",
                forces=(0.04, 0.06, 0.08),
                converged=(True, False, False),
            ),
            _consensus_row(
                "geometry_bad",
                forces=(0.04, 0.06, 0.08),
                converged=(True, False, False),
            ),
            _consensus_row(
                "missing_force",
                forces=(0.04, 0.06, None),
                converged=(True, False, None),
            ),
        ],
    )

    result = f3_pairs.main(
        [
            "--consensus-jsonl",
            str(consensus),
            "--audit-candidates-jsonl",
            str(audit),
            "--candidate-id-prefix",
            "after64__",
            "--sample-label",
            "after64",
            "--output-dir",
            str(output_dir),
            "--fail-on-zero-pairs",
        ]
    )

    summary = result["summary"]
    assert summary["matched_f3_candidate_count"] == 2
    assert summary["candidate_skip_reasons"] == {
        "f1_f2_not_passing": 1,
        "missing_three_mlip_force_evidence": 1,
    }
    assert summary["f3_good_candidate_count"] == 1
    assert summary["f3_near_miss_candidate_count"] == 1
    assert summary["pair_count"] == 1
    assert summary["training_pair_validation"]["valid_pair_count"] == 1

    pair = json.loads((output_dir / "dpo_preferences" / "preference_pairs.jsonl").read_text(encoding="utf-8"))
    assert pair["chosen_candidate_id"] == "after64__good"
    assert pair["rejected_candidate_id"] == "after64__near_miss"
    assert pair["preference_reason"] == [
        "same_formula_rank_neighbor_f3_pairing_v1",
        "good_vs_near_miss_mlip_force",
        "f1_f2_controlled",
    ]
    assert pair["chosen_failure_vector"]["f3_stability"] is None
    assert pair["rejected_failure_vector"]["f3_stability"] is None
    assert pair["metadata"]["f3_only_preference"] is True
    assert pair["metadata"]["f3_pair_rule"] == "same_formula_rank_neighbor_f3_pairing_v1"
    assert pair["metadata"]["chosen_mlip_force_evidence"]["model_forces"] == {
        "CHGNet": 0.03,
        "MACE": 0.02,
        "MatGL": 0.04,
    }
    assert pair["metadata"]["rejected_mlip_force_evidence"]["model_forces"] == {
        "CHGNet": 0.06,
        "MACE": 0.04,
        "MatGL": 0.08,
    }
    assert pair["condition"]["generation"]["sample_label"] == "after64"
