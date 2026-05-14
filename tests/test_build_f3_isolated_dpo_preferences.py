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


def _consensus_row(candidate_id: str, stable: bool | None) -> dict:
    return {
        "candidate_id": f"after64__{candidate_id}",
        "formula": "BaTiO3",
        "validation_status": "completed",
        "validator": "mace+chgnet+matgl",
        "validation_source": "local_mlip_mace_chgnet_matgl_relaxation_consensus_fixture",
        "is_stable": stable,
        "force_max": 0.01 if stable else 0.5,
        "stress_max": 0.1,
        "relaxation_converged": stable,
        "metadata": {
            "vote_pattern": (
                "chgnet:stable|mace:stable|matgl:stable"
                if stable
                else "chgnet:unstable|mace:unstable|matgl:unstable"
            )
        },
    }


def test_f3_isolated_builder_controls_f1_f2_and_uses_prefixed_consensus_ids(tmp_path: Path) -> None:
    audit = tmp_path / "audit_candidates.jsonl"
    consensus = tmp_path / "consensus.jsonl"
    output_dir = tmp_path / "artifact"
    _write_jsonl(
        audit,
        [
            _audit_row("stable"),
            _audit_row("unstable"),
            _audit_row("geometry_bad", f1=0.2),
            _audit_row("disagreement"),
        ],
    )
    _write_jsonl(
        consensus,
        [
            _consensus_row("stable", True),
            _consensus_row("unstable", False),
            _consensus_row("geometry_bad", False),
            _consensus_row("disagreement", None),
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
        "non_agreement_or_missing_f3": 1,
    }
    assert summary["pair_count"] == 1
    assert summary["training_pair_validation"]["valid_pair_count"] == 1

    pair = json.loads((output_dir / "dpo_preferences" / "preference_pairs.jsonl").read_text(encoding="utf-8"))
    assert pair["chosen_candidate_id"] == "after64__stable"
    assert pair["rejected_candidate_id"] == "after64__unstable"
    assert pair["preference_reason"] == [
        "f3_consensus_only",
        "three_mlip_all_agree",
        "f1_f2_controlled",
    ]
    assert pair["chosen_failure_vector"]["f3_stability"] == 0.0
    assert pair["rejected_failure_vector"]["f3_stability"] == 1.0
    assert pair["metadata"]["f3_only_preference"] is True
    assert pair["condition"]["generation"]["sample_label"] == "after64"
