#!/usr/bin/env python
"""Compare matched before/after generation after MLIP consensus import."""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT in sys.path:
    sys.path.remove(PROJECT_ROOT_TEXT)
sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.io import read_json, read_jsonl, write_json


CAVEAT = (
    "Matched before/after labels are MACE+CHGNet+MatGL relaxation consensus "
    "proxy evidence, not DFT evidence and not self-consistent hull-confirmed "
    "stability."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a lightweight matched before/after report from generation "
            "summaries, candidate indexes, and imported three-MLIP consensus evidence."
        )
    )
    parser.add_argument("--generation-summary", required=True)
    parser.add_argument("--before-consensus-summary", required=True)
    parser.add_argument("--before-consensus-comparison", required=True)
    parser.add_argument("--before-candidate-index", required=True)
    parser.add_argument("--after-consensus-summary", required=True)
    parser.add_argument("--after-consensus-comparison", required=True)
    parser.add_argument("--after-candidate-index", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    generation = read_json(args.generation_summary)
    before = _side_metrics(
        "before",
        generation.get("before", {}),
        read_json(args.before_consensus_summary),
        read_jsonl(args.before_consensus_comparison),
        read_jsonl(args.before_candidate_index),
    )
    after = _side_metrics(
        "after",
        generation.get("after", {}),
        read_json(args.after_consensus_summary),
        read_jsonl(args.after_consensus_comparison),
        read_jsonl(args.after_candidate_index),
    )
    summary = {
        "generated_at": date.today().isoformat(),
        "workflow": "matched_before_after_three_mlip_consensus_comparison",
        "purpose": _purpose(before, after),
        "matched_settings": generation.get("matched_settings", {}),
        "before": before,
        "after": after,
        "delta": _delta(before, after),
        "reward_hacking_or_proxy_divergence": _proxy_divergence(before, after),
        "inputs": {
            "generation_summary": str(args.generation_summary),
            "before_consensus_summary": str(args.before_consensus_summary),
            "before_consensus_comparison": str(args.before_consensus_comparison),
            "before_candidate_index": str(args.before_candidate_index),
            "after_consensus_summary": str(args.after_consensus_summary),
            "after_consensus_comparison": str(args.after_consensus_comparison),
            "after_candidate_index": str(args.after_candidate_index),
        },
        "local_only": True,
        "runs_dft": False,
        "runs_generation": False,
        "runs_mlip": False,
        "runs_training": False,
        "downloads": False,
        "calls_external_apis": False,
        "caveat": CAVEAT,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "summary.json", summary)
    (output_dir / "report.md").write_text(_report(summary), encoding="utf-8")
    print(f"Before/after MLIP consensus comparison complete: {output_dir}")
    print(f"  before_stable_consensus_count: {before['strict_three_mlip_stable_consensus_count']}")
    print(f"  after_stable_consensus_count: {after['strict_three_mlip_stable_consensus_count']}")
    print(f"  proxy_divergence_flag: {summary['reward_hacking_or_proxy_divergence']['flag']}")
    return summary


def _purpose(before: dict[str, Any], after: dict[str, Any]) -> str:
    return (
        "Compare completed matched CrystalFormer DPO before/after generation "
        f"({before.get('candidate_count')} before candidates, "
        f"{after.get('candidate_count')} after candidates) only after importing "
        "strict MACE+CHGNet+MatGL relaxation consensus F3 proxy evidence."
    )


def _side_metrics(
    side: str,
    generation: dict[str, Any],
    consensus: dict[str, Any],
    comparison_rows: list[dict[str, Any]],
    candidate_index: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_count = _int_or_count(generation.get("total_candidates"), candidate_index)
    dpo_eligible_count = int(generation.get("dpo_eligible_count") or _count_truthy(candidate_index, "dpo_eligible"))
    f1_fail_count = int(generation.get("f1_fail_count") or _count_label(candidate_index, "f1_label", "fail"))
    f2_fail_count = int(generation.get("f2_fail_count") or _count_label(candidate_index, "f2_label", "fail"))
    stable_count = int(consensus.get("stable_consensus_count") or 0)
    unstable_count = int(consensus.get("unstable_consensus_count") or 0)
    disagreement_count = int(consensus.get("disagreement_or_unavailable_count") or 0)
    f3_available_count = int(consensus.get("f3_available_candidate_count") or stable_count + unstable_count)
    overlap_count = int(consensus.get("overlap_count") or len(comparison_rows))
    formula_counts = Counter(str(row.get("formula") or row.get("composition") or "") for row in candidate_index)
    formula_counts.pop("", None)
    spacegroups = [_spacegroup(row) for row in candidate_index]
    spacegroup_counts = Counter(str(value) for value in spacegroups if value is not None)
    prototype_counts = Counter(
        str(_nested(row, ("failure_vector", "metadata", "prototype")))
        for row in candidate_index
        if _nested(row, ("failure_vector", "metadata", "prototype")) is not None
    )
    unique_sequences = _unique_sequence_count(candidate_index)
    consensus_vote_patterns = consensus.get("vote_pattern_counts") if isinstance(consensus.get("vote_pattern_counts"), dict) else {}
    validator_stable_counts = (
        consensus.get("validator_stable_counts") if isinstance(consensus.get("validator_stable_counts"), dict) else {}
    )
    validator_count = len(validator_stable_counts)
    stable_vote_count = _sum_numeric_counts(validator_stable_counts)
    pairwise = consensus.get("pairwise_agreement") if isinstance(consensus.get("pairwise_agreement"), dict) else {}
    return {
        "side": side,
        "candidate_count": candidate_count,
        "dpo_eligible_count": dpo_eligible_count,
        "dpo_eligible_rate": _ratio(dpo_eligible_count, candidate_count),
        "f1_fail_count": f1_fail_count,
        "f1_fail_rate": _ratio(f1_fail_count, candidate_count),
        "f2_fail_count": f2_fail_count,
        "f2_fail_rate": _ratio(f2_fail_count, candidate_count),
        "f3_available_count": f3_available_count,
        "f3_available_rate": _ratio(f3_available_count, candidate_count),
        "strict_three_mlip_stable_consensus_count": stable_count,
        "unstable_consensus_count": unstable_count,
        "disagreement_count": disagreement_count,
        "all_three_agreement_rate": consensus.get("agreement_rate"),
        "validator_count": validator_count,
        "stable_vote_count": stable_vote_count,
        "average_stable_votes_per_generated_candidate": _ratio(stable_vote_count, candidate_count),
        "average_stable_vote_fraction_all_generated": _ratio(
            stable_vote_count,
            validator_count * candidate_count if validator_count and candidate_count else 0,
        ),
        "average_stable_votes_per_validated_candidate": _ratio(stable_vote_count, overlap_count),
        "average_stable_vote_fraction_validated": _ratio(
            stable_vote_count,
            validator_count * overlap_count if validator_count and overlap_count else 0,
        ),
        "pairwise_agreement_rate": {
            name: stats.get("agreement_rate")
            for name, stats in pairwise.items()
            if isinstance(stats, dict)
        },
        "pairwise_energy_pearson": {
            name: stats.get("energy_pearson")
            for name, stats in pairwise.items()
            if isinstance(stats, dict)
        },
        "stable_consensus_rate": _ratio(stable_count, candidate_count),
        "stable_consensus_rate_among_f3_available": _ratio(stable_count, f3_available_count),
        "preference_pair_yield": generation.get("preference_pair_yield"),
        "formula_count": len(formula_counts),
        "formula_coverage": dict(sorted(formula_counts.items())),
        "dominant_formula_fraction": _ratio(max(formula_counts.values()) if formula_counts else 0, candidate_count),
        "unique_sequence_count": unique_sequences,
        "unique_sequence_fraction": _ratio(unique_sequences, candidate_count),
        "spacegroup_count": len(spacegroup_counts),
        "spacegroup_entropy": _entropy(spacegroup_counts.values()),
        "spacegroup_coverage": dict(sorted(spacegroup_counts.items())),
        "prototype_count": len(prototype_counts),
        "prototype_coverage": dict(sorted(prototype_counts.items())),
        "validator_stable_counts": validator_stable_counts,
        "vote_pattern_counts": consensus_vote_patterns,
        "overlap_count": overlap_count,
        "consensus_artifact_caveat": consensus.get("caveat"),
    }


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    numeric_keys = [
        "candidate_count",
        "dpo_eligible_count",
        "dpo_eligible_rate",
        "f1_fail_rate",
        "f2_fail_rate",
        "f3_available_count",
        "f3_available_rate",
        "strict_three_mlip_stable_consensus_count",
        "unstable_consensus_count",
        "disagreement_count",
        "all_three_agreement_rate",
        "stable_vote_count",
        "average_stable_votes_per_generated_candidate",
        "average_stable_vote_fraction_all_generated",
        "average_stable_votes_per_validated_candidate",
        "average_stable_vote_fraction_validated",
        "stable_consensus_rate",
        "stable_consensus_rate_among_f3_available",
        "preference_pair_yield",
        "formula_count",
        "dominant_formula_fraction",
        "unique_sequence_fraction",
        "spacegroup_count",
        "spacegroup_entropy",
        "prototype_count",
    ]
    out: dict[str, Any] = {}
    for key in numeric_keys:
        left = before.get(key)
        right = after.get(key)
        out[key] = _subtract(right, left)
    out["pairwise_agreement_rate"] = {
        key: _subtract(after.get("pairwise_agreement_rate", {}).get(key), before.get("pairwise_agreement_rate", {}).get(key))
        for key in sorted(set(before.get("pairwise_agreement_rate", {})) | set(after.get("pairwise_agreement_rate", {})))
    }
    out["pairwise_energy_pearson"] = {
        key: _subtract(after.get("pairwise_energy_pearson", {}).get(key), before.get("pairwise_energy_pearson", {}).get(key))
        for key in sorted(set(before.get("pairwise_energy_pearson", {})) | set(after.get("pairwise_energy_pearson", {})))
    }
    return out


def _proxy_divergence(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    stable_delta = _subtract(after.get("stable_consensus_rate"), before.get("stable_consensus_rate"))
    agreement_delta = _subtract(after.get("all_three_agreement_rate"), before.get("all_three_agreement_rate"))
    disagreement_delta = _subtract(after.get("disagreement_count"), before.get("disagreement_count"))
    unique_delta = _subtract(after.get("unique_sequence_fraction"), before.get("unique_sequence_fraction"))
    spacegroup_delta = _subtract(after.get("spacegroup_count"), before.get("spacegroup_count"))
    f1_delta = _subtract(after.get("f1_fail_rate"), before.get("f1_fail_rate"))
    f2_delta = _subtract(after.get("f2_fail_rate"), before.get("f2_fail_rate"))
    average_stability_delta = _subtract(
        after.get("average_stable_vote_fraction_all_generated"),
        before.get("average_stable_vote_fraction_all_generated"),
    )
    reasons: list[str] = []
    if _positive(stable_delta) and _negative(agreement_delta):
        reasons.append("stable consensus rate increased while all-three agreement rate decreased")
    if _positive(stable_delta) and _positive(disagreement_delta):
        reasons.append("stable consensus rate increased while disagreement count increased")
    if _positive(stable_delta) and (_negative(unique_delta) or _negative(spacegroup_delta)):
        reasons.append("stable consensus rate increased while diversity/coverage decreased")
    if _positive(stable_delta) and (_positive(f1_delta) or _positive(f2_delta)):
        reasons.append("stable consensus rate increased while F1/F2 fail rate increased")
    if not _positive(stable_delta) and not _positive(average_stability_delta):
        reasons.append("no observed strict-consensus stable-rate improvement in this matched proxy audit")
    return {
        "flag": bool(reasons),
        "reasons": reasons,
        "primary_stability_signal": {
            "stable_consensus_rate_delta": stable_delta,
            "average_stable_vote_fraction_all_generated_delta": average_stability_delta,
            "f1_fail_rate_delta": f1_delta,
        },
        "interpretation": (
            "This is a proxy-divergence screen on a matched offline-validation audit. It cannot "
            "prove reward hacking absence or presence; it only identifies signals "
            "that need a larger matched audit and DFT-backed fixed audit later."
        ),
    }


def _report(summary: dict[str, Any]) -> str:
    before = summary["before"]
    after = summary["after"]
    delta = summary["delta"]
    risk = summary["reward_hacking_or_proxy_divergence"]
    lines = [
        "# Matched Before/After Three-MLIP Consensus Comparison",
        "",
        "## Scope",
        "",
        summary["purpose"],
        "",
        f"- Caveat: {summary['caveat']}",
        "",
        "## Metrics",
        "",
        "| metric | before | after | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    rows = [
        ("candidate_count", "candidate_count"),
        ("DPO eligible count", "dpo_eligible_count"),
        ("F1 fail rate", "f1_fail_rate"),
        ("F2 fail rate", "f2_fail_rate"),
        ("F3 available count", "f3_available_count"),
        ("strict three-MLIP stable consensus count", "strict_three_mlip_stable_consensus_count"),
        ("unstable consensus count", "unstable_consensus_count"),
        ("disagreement count", "disagreement_count"),
        ("stable vote count", "stable_vote_count"),
        ("average stable votes per generated candidate", "average_stable_votes_per_generated_candidate"),
        ("average stable vote fraction (all generated)", "average_stable_vote_fraction_all_generated"),
        ("average stable votes per validated candidate", "average_stable_votes_per_validated_candidate"),
        ("average stable vote fraction (validated)", "average_stable_vote_fraction_validated"),
        ("stable consensus rate", "stable_consensus_rate"),
        ("all-three agreement rate", "all_three_agreement_rate"),
        ("preference-pair yield", "preference_pair_yield"),
        ("unique sequence fraction", "unique_sequence_fraction"),
        ("spacegroup count", "spacegroup_count"),
        ("spacegroup entropy", "spacegroup_entropy"),
        ("formula count", "formula_count"),
        ("prototype count", "prototype_count"),
    ]
    for label, key in rows:
        lines.append(f"| {label} | {_fmt(before.get(key))} | {_fmt(after.get(key))} | {_fmt(delta.get(key))} |")
    lines.extend(["", "## Pairwise Agreement", "", "| pair | before | after | delta |", "| --- | ---: | ---: | ---: |"])
    for key in sorted(set(before["pairwise_agreement_rate"]) | set(after["pairwise_agreement_rate"])):
        lines.append(
            f"| {key} | {_fmt(before['pairwise_agreement_rate'].get(key))} | "
            f"{_fmt(after['pairwise_agreement_rate'].get(key))} | "
            f"{_fmt(delta['pairwise_agreement_rate'].get(key))} |"
        )
    lines.extend(
        [
            "",
            "## Coverage And Collapse Signals",
            "",
            f"- Before formula coverage: {_compact_counts(before['formula_coverage'])}",
            f"- After formula coverage: {_compact_counts(after['formula_coverage'])}",
            f"- Before spacegroup coverage: {_compact_counts(before['spacegroup_coverage'])}",
            f"- After spacegroup coverage: {_compact_counts(after['spacegroup_coverage'])}",
            f"- Prototype coverage: before={_compact_counts(before['prototype_coverage'])}, after={_compact_counts(after['prototype_coverage'])}",
            "",
            "## Reward Hacking Or Proxy Divergence Screen",
            "",
            f"- Flag: {risk['flag']}",
        ]
    )
    for reason in risk["reasons"]:
        lines.append(f"- {reason}")
    lines.extend(["", risk["interpretation"], ""])
    return "\n".join(lines)


def _int_or_count(value: Any, rows: list[dict[str, Any]]) -> int:
    if isinstance(value, int):
        return value
    return len(rows)


def _count_truthy(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if row.get(key) is True)


def _count_label(rows: list[dict[str, Any]], key: str, label: str) -> int:
    return sum(1 for row in rows if row.get(key) == label)


def _sum_numeric_counts(counts: dict[str, Any]) -> int:
    return sum(int(value) for value in counts.values() if isinstance(value, int | float) and not isinstance(value, bool))


def _spacegroup(row: dict[str, Any]) -> Any:
    return _nested(row, ("failure_vector", "metadata", "space_group")) or _nested(row, ("condition", "spacegroup"))


def _nested(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = row
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _unique_sequence_count(rows: list[dict[str, Any]]) -> int:
    sequences = set()
    for row in rows:
        fields = row.get("raw_sequence_fields")
        if isinstance(fields, dict):
            sequences.add(tuple(sorted((str(key), str(value)) for key, value in fields.items())))
    return len(sequences)


def _ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _entropy(values: Any) -> float | None:
    counts = [float(value) for value in values if value]
    total = sum(counts)
    if total <= 0:
        return None
    return -sum((count / total) * math.log(count / total) for count in counts)


def _subtract(right: Any, left: Any) -> float | int | None:
    if isinstance(left, int | float) and isinstance(right, int | float):
        return right - left
    return None


def _positive(value: Any) -> bool:
    return isinstance(value, int | float) and value > 0


def _negative(value: Any) -> bool:
    return isinstance(value, int | float) and value < 0


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _compact_counts(counts: dict[str, Any], *, limit: int = 12) -> str:
    if not counts:
        return "{}"
    parts = [f"{key}:{counts[key]}" for key in sorted(counts)[:limit]]
    if len(counts) > limit:
        parts.append("...")
    return ", ".join(parts)


if __name__ == "__main__":
    main()
