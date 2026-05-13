import json
from pathlib import Path

from scripts import compare_dpo_before_after_mlip_consensus as compare


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _index_row(candidate_id: str, formula: str, space_group: int, *, eligible: bool = True) -> dict:
    return {
        "candidate_id": candidate_id,
        "formula": formula,
        "dpo_eligible": eligible,
        "f1_label": "pass",
        "f2_label": "pass",
        "raw_sequence_fields": {"A": "[1]", "L": "[1]", "W": "[1]", "X": f"[{candidate_id}]", "g": str(space_group)},
        "failure_vector": {"metadata": {"space_group": space_group, "prototype": None}},
    }


def _consensus_summary(stable: int, unstable: int, disagreement: int, agreement_rate: float) -> dict:
    return {
        "overlap_count": stable + unstable + disagreement,
        "f3_available_candidate_count": stable + unstable,
        "stable_consensus_count": stable,
        "unstable_consensus_count": unstable,
        "disagreement_or_unavailable_count": disagreement,
        "agreement_rate": agreement_rate,
        "pairwise_agreement": {
            "mace__chgnet": {"agreement_rate": 1.0, "energy_pearson": 0.9},
            "mace__matgl": {"agreement_rate": 0.5, "energy_pearson": 0.2},
        },
        "validator_stable_counts": {"mace": stable, "chgnet": stable, "matgl": stable},
        "vote_pattern_counts": {"all_stable": stable},
        "caveat": "proxy only",
    }


def test_comparison_report_flags_proxy_divergence(tmp_path: Path) -> None:
    generation = {
        "matched_settings": {"samples_per_formula": 2},
        "before": {
            "total_candidates": 2,
            "dpo_eligible_count": 2,
            "f1_fail_count": 0,
            "f2_fail_count": 0,
            "preference_pair_yield": 1,
        },
        "after": {
            "total_candidates": 2,
            "dpo_eligible_count": 2,
            "f1_fail_count": 1,
            "f2_fail_count": 0,
            "preference_pair_yield": 1,
        },
    }
    generation_path = tmp_path / "generation.json"
    before_summary = tmp_path / "before_summary.json"
    after_summary = tmp_path / "after_summary.json"
    before_comparison = tmp_path / "before_comparison.jsonl"
    after_comparison = tmp_path / "after_comparison.jsonl"
    before_index = tmp_path / "before_index.jsonl"
    after_index = tmp_path / "after_index.jsonl"
    output_dir = tmp_path / "out"

    _write_json(generation_path, generation)
    _write_json(before_summary, _consensus_summary(stable=1, unstable=1, disagreement=0, agreement_rate=1.0))
    _write_json(after_summary, _consensus_summary(stable=2, unstable=0, disagreement=0, agreement_rate=0.5))
    _write_jsonl(before_comparison, [{"candidate_id": "before__1"}, {"candidate_id": "before__2"}])
    _write_jsonl(after_comparison, [{"candidate_id": "after__1"}, {"candidate_id": "after__2"}])
    _write_jsonl(before_index, [_index_row("before__1", "BaTiO3", 1), _index_row("before__2", "SrTiO3", 2)])
    _write_jsonl(after_index, [_index_row("after__1", "BaTiO3", 1), _index_row("after__2", "SrTiO3", 1)])

    summary = compare.main(
        [
            "--generation-summary",
            str(generation_path),
            "--before-consensus-summary",
            str(before_summary),
            "--before-consensus-comparison",
            str(before_comparison),
            "--before-candidate-index",
            str(before_index),
            "--after-consensus-summary",
            str(after_summary),
            "--after-consensus-comparison",
            str(after_comparison),
            "--after-candidate-index",
            str(after_index),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert summary["before"]["strict_three_mlip_stable_consensus_count"] == 1
    assert summary["after"]["strict_three_mlip_stable_consensus_count"] == 2
    assert summary["delta"]["stable_consensus_rate"] == 0.5
    assert summary["reward_hacking_or_proxy_divergence"]["flag"] is True
    assert (output_dir / "summary.json").exists()
    assert "not DFT" in (output_dir / "report.md").read_text(encoding="utf-8")
