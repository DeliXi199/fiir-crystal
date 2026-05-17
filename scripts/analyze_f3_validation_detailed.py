#!/usr/bin/env python
"""Build detailed per-formula and high-confidence F3 validation tables."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT in sys.path:
    sys.path.remove(PROJECT_ROOT_TEXT)
sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.io import read_json, read_jsonl, write_json, write_jsonl


VALIDATOR_ORDER = ("MACE", "CHGNet", "MatGL")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Expand a matched before/after MLIP consensus summary into per-formula "
            "metrics and ranked high-confidence after candidates."
        )
    )
    parser.add_argument("--comparison-summary", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--samples-per-formula", type=int)
    parser.add_argument("--high-confidence-force-max", type=float, default=0.05)
    parser.add_argument("--tier-a-force-max", type=float, default=0.03)
    parser.add_argument("--tier-b-force-max", type=float, default=0.04)
    parser.add_argument("--top-per-formula", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    comparison_summary_path = Path(args.comparison_summary)
    comparison = read_json(comparison_summary_path)
    inputs = comparison.get("inputs", {})
    generation_summary = read_json(inputs["generation_summary"])
    samples_per_formula = int(
        args.samples_per_formula
        or comparison.get("matched_settings", {}).get("samples_per_formula")
        or generation_summary.get("matched_settings", {}).get("samples_per_formula")
        or 80
    )

    before_rows = read_jsonl(inputs["before_consensus_comparison"])
    after_rows = read_jsonl(inputs["after_consensus_comparison"])
    before_index = read_jsonl(inputs["before_candidate_index"])
    after_index = read_jsonl(inputs["after_candidate_index"])
    after_selected_path = generation_summary.get("after", {}).get("selected_candidates")
    after_selected = read_jsonl(after_selected_path) if after_selected_path else []

    before_formula = _side_by_formula(before_rows, before_index, samples_per_formula)
    after_formula = _side_by_formula(after_rows, after_index, samples_per_formula)
    formulas = sorted(set(before_formula) | set(after_formula))
    high_confidence = _high_confidence_candidates(
        after_rows=after_rows,
        after_selected=after_selected,
        force_max=args.high_confidence_force_max,
        tier_a_force_max=args.tier_a_force_max,
        tier_b_force_max=args.tier_b_force_max,
    )
    global_force_stats = _global_force_stats(before_rows, after_rows)
    force_stats_by_formula = _force_stats_by_formula(before_rows, after_rows)
    high_conf_by_formula = Counter(row["formula"] for row in high_confidence)
    per_formula = [
        _merge_formula(
            formula=formula,
            before=before_formula.get(formula, _empty_formula(samples_per_formula)),
            after=after_formula.get(formula, _empty_formula(samples_per_formula)),
            high_confidence_count=high_conf_by_formula.get(formula, 0),
        )
        for formula in formulas
    ]
    top_per_formula = _top_per_formula(high_confidence, args.top_per_formula)
    summary = _summary(
        comparison=comparison,
        per_formula=per_formula,
        high_confidence=high_confidence,
        samples_per_formula=samples_per_formula,
        args=args,
        global_force_stats=global_force_stats,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "global_force_stats.json", global_force_stats)
    write_jsonl(output_dir / "per_formula_metrics.jsonl", per_formula)
    write_jsonl(output_dir / "force_stats_by_formula.jsonl", force_stats_by_formula)
    write_jsonl(output_dir / "high_confidence_candidates.jsonl", high_confidence)
    write_jsonl(output_dir / "high_confidence_top_per_formula.jsonl", top_per_formula)
    _write_csv(output_dir / "per_formula_metrics.csv", per_formula)
    _write_csv(output_dir / "force_stats_by_formula.csv", force_stats_by_formula)
    _write_csv(output_dir / "high_confidence_candidates.csv", high_confidence)
    _write_csv(output_dir / "high_confidence_top_per_formula.csv", top_per_formula)
    (output_dir / "per_formula_metrics.md").write_text(_formula_table(per_formula), encoding="utf-8")
    (output_dir / "force_stats_by_formula.md").write_text(
        _force_formula_table(force_stats_by_formula), encoding="utf-8"
    )
    (output_dir / "high_confidence_top_per_formula.md").write_text(
        _candidate_table(top_per_formula), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(_report(summary, per_formula, top_per_formula), encoding="utf-8")

    print(f"Detailed F3 validation analysis complete: {output_dir}")
    print(f"  formula_count: {summary['formula_count']}")
    print(f"  stable_consensus_delta_total: {summary['stable_consensus_delta_total']}")
    print(f"  high_confidence_count: {summary['high_confidence']['count']}")
    print(f"  tier_a_count: {summary['high_confidence']['tier_a_count']}")
    print(f"  tier_b_count: {summary['high_confidence']['tier_b_count']}")
    return summary


def _side_by_formula(
    comparison_rows: list[dict[str, Any]],
    candidate_index: list[dict[str, Any]],
    samples_per_formula: int,
) -> dict[str, dict[str, Any]]:
    selected_counts = Counter(_formula(row) for row in candidate_index)
    selected_counts.pop("", None)
    metrics: dict[str, dict[str, Any]] = {
        formula: _empty_formula(samples_per_formula) for formula in selected_counts
    }
    for formula, count in selected_counts.items():
        metrics[formula]["selected_count"] = count
        metrics[formula]["f1_f2_fail_count"] = max(samples_per_formula - count, 0)

    for row in comparison_rows:
        formula = _formula(row)
        if not formula:
            continue
        item = metrics.setdefault(formula, _empty_formula(samples_per_formula))
        item["validated_count"] += 1
        item["stable_vote_count"] += int(row.get("stable_votes") or 0)
        agreement = bool(row.get("agreement"))
        consensus = row.get("consensus_is_stable")
        if agreement:
            item["f3_available_count"] += 1
            if consensus is True:
                item["stable_consensus_count"] += 1
                forces = _validator_values(row, "force_max")
                stresses = _validator_values(row, "stress_max")
                if forces:
                    item["stable_force_max_values"].append(max(forces))
                    item["stable_force_mean_values"].append(statistics.fmean(forces))
                if stresses:
                    item["stable_stress_max_values"].append(max(stresses))
            elif consensus is False:
                item["unstable_consensus_count"] += 1
        else:
            item["disagreement_count"] += 1

        validators = row.get("validators") if isinstance(row.get("validators"), dict) else {}
        for validator in VALIDATOR_ORDER:
            data = validators.get(validator)
            if isinstance(data, dict) and data.get("is_stable") is True:
                item[f"{validator}_stable_count"] += 1

    for item in metrics.values():
        _finalize_formula(item)
    return metrics


def _empty_formula(samples_per_formula: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "generated_count": samples_per_formula,
        "selected_count": 0,
        "f1_f2_fail_count": samples_per_formula,
        "validated_count": 0,
        "f3_available_count": 0,
        "stable_consensus_count": 0,
        "unstable_consensus_count": 0,
        "disagreement_count": 0,
        "stable_vote_count": 0,
        "MACE_stable_count": 0,
        "CHGNet_stable_count": 0,
        "MatGL_stable_count": 0,
        "stable_force_max_values": [],
        "stable_force_mean_values": [],
        "stable_stress_max_values": [],
    }
    return item


def _finalize_formula(item: dict[str, Any]) -> None:
    generated = item["generated_count"]
    selected = item["selected_count"]
    validated = item["validated_count"]
    item["selected_rate"] = _ratio(selected, generated)
    item["f1_f2_fail_rate"] = _ratio(item["f1_f2_fail_count"], generated)
    item["stable_consensus_rate_generated"] = _ratio(item["stable_consensus_count"], generated)
    item["stable_consensus_rate_validated"] = _ratio(item["stable_consensus_count"], validated)
    item["unstable_consensus_rate_validated"] = _ratio(item["unstable_consensus_count"], validated)
    item["disagreement_rate_validated"] = _ratio(item["disagreement_count"], validated)
    item["f3_available_rate_validated"] = _ratio(item["f3_available_count"], validated)
    item["avg_stable_votes_per_validated"] = _ratio(item["stable_vote_count"], validated)
    item["avg_stable_vote_fraction_validated"] = _ratio(item["stable_vote_count"], 3 * validated)
    for validator in VALIDATOR_ORDER:
        item[f"{validator}_stable_rate_validated"] = _ratio(item[f"{validator}_stable_count"], validated)
    item["stable_force_max_median"] = _median(item["stable_force_max_values"])
    item["stable_force_max_p90"] = _percentile(item["stable_force_max_values"], 0.9)
    item["stable_force_mean_median"] = _median(item["stable_force_mean_values"])
    item["stable_stress_max_median"] = _median(item["stable_stress_max_values"])
    item.pop("stable_force_max_values", None)
    item.pop("stable_force_mean_values", None)
    item.pop("stable_stress_max_values", None)


def _merge_formula(
    formula: str,
    before: dict[str, Any],
    after: dict[str, Any],
    high_confidence_count: int,
) -> dict[str, Any]:
    keys = [
        "generated_count",
        "selected_count",
        "f1_f2_fail_count",
        "f1_f2_fail_rate",
        "validated_count",
        "f3_available_count",
        "f3_available_rate_validated",
        "stable_consensus_count",
        "stable_consensus_rate_generated",
        "stable_consensus_rate_validated",
        "unstable_consensus_count",
        "unstable_consensus_rate_validated",
        "disagreement_count",
        "disagreement_rate_validated",
        "stable_vote_count",
        "avg_stable_votes_per_validated",
        "avg_stable_vote_fraction_validated",
        "MACE_stable_count",
        "CHGNet_stable_count",
        "MatGL_stable_count",
        "stable_force_max_median",
        "stable_force_max_p90",
        "stable_force_mean_median",
        "stable_stress_max_median",
    ]
    row: dict[str, Any] = {"formula": formula}
    for key in keys:
        row[f"before_{key}"] = before.get(key)
        row[f"after_{key}"] = after.get(key)
        if isinstance(before.get(key), (int, float)) and isinstance(after.get(key), (int, float)):
            row[f"delta_{key}"] = after[key] - before[key]
    row["after_high_confidence_count"] = high_confidence_count
    row["after_high_confidence_rate_generated"] = _ratio(high_confidence_count, after.get("generated_count"))
    row["after_high_confidence_rate_validated"] = _ratio(high_confidence_count, after.get("validated_count"))
    return row


def _high_confidence_candidates(
    after_rows: list[dict[str, Any]],
    after_selected: list[dict[str, Any]],
    force_max: float,
    tier_a_force_max: float,
    tier_b_force_max: float,
) -> list[dict[str, Any]]:
    selected_by_id = {str(row.get("candidate_id")): row for row in after_selected}
    candidates = []
    for row in after_rows:
        if row.get("consensus_is_stable") is not True or int(row.get("available_votes") or 0) != 3:
            continue
        validators = row.get("validators") if isinstance(row.get("validators"), dict) else {}
        if not validators:
            continue
        forces = _validator_values(row, "force_max")
        stresses = _validator_values(row, "stress_max")
        energies = _validator_values(row, "energy_eV_per_atom")
        converged = [
            bool(validators.get(validator, {}).get("relaxation_converged"))
            for validator in VALIDATOR_ORDER
            if isinstance(validators.get(validator), dict)
        ]
        stable_flags = [
            validators.get(validator, {}).get("is_stable") is True
            for validator in VALIDATOR_ORDER
            if isinstance(validators.get(validator), dict)
        ]
        if len(forces) != 3 or not all(converged) or not all(stable_flags):
            continue
        max_force = max(forces)
        if max_force > force_max:
            continue
        selected = selected_by_id.get(str(row.get("candidate_id")), {})
        tier = "C_consensus_0.05"
        if max_force <= tier_a_force_max:
            tier = "A_force_le_0.03"
        elif max_force <= tier_b_force_max:
            tier = "B_force_le_0.04"
        candidate = {
            "candidate_id": row.get("candidate_id"),
            "formula": _formula(row),
            "confidence_tier": tier,
            "spacegroup": _spacegroup_from_consensus_or_selected(row, selected),
            "num_sites": selected.get("num_sites"),
            "max_force": max_force,
            "mean_force": statistics.fmean(forces),
            "median_force": statistics.median(forces),
            "force_spread": max(forces) - min(forces),
            "max_stress": max(stresses) if stresses else None,
            "mean_stress": statistics.fmean(stresses) if stresses else None,
            "energy_range": max(energies) - min(energies) if energies else None,
            "mean_energy_eV_per_atom": statistics.fmean(energies) if energies else None,
            "stable_votes": row.get("stable_votes"),
            "vote_pattern": row.get("vote_pattern"),
            "MACE_force_max": _validator_value(row, "MACE", "force_max"),
            "CHGNet_force_max": _validator_value(row, "CHGNet", "force_max"),
            "MatGL_force_max": _validator_value(row, "MatGL", "force_max"),
            "MACE_stress_max": _validator_value(row, "MACE", "stress_max"),
            "CHGNet_stress_max": _validator_value(row, "CHGNet", "stress_max"),
            "MatGL_stress_max": _validator_value(row, "MatGL", "stress_max"),
            "MACE_energy_eV_per_atom": _validator_value(row, "MACE", "energy_eV_per_atom"),
            "CHGNet_energy_eV_per_atom": _validator_value(row, "CHGNet", "energy_eV_per_atom"),
            "MatGL_energy_eV_per_atom": _validator_value(row, "MatGL", "energy_eV_per_atom"),
            "raw_L": _nested(selected, ("metadata", "raw_L")),
            "raw_A": _nested(selected, ("metadata", "raw_A")),
            "raw_W": _nested(selected, ("metadata", "raw_W")),
            "raw_X": _nested(selected, ("metadata", "raw_X")),
        }
        candidates.append(candidate)
    return sorted(candidates, key=_candidate_sort_key)


def _global_force_stats(
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    before = _side_force_stats(before_rows)
    after = _side_force_stats(after_rows)
    return {
        "before": before,
        "after": after,
        "delta": _force_delta(before, after),
        "force_quantity": "force_max",
        "force_unit": "eV/Angstrom",
        "subsets": {
            "all_validated": "All candidates with completed validator force_max.",
            "model_stable": "Candidates that the specific MLIP labels stable.",
            "model_unstable": "Candidates that the specific MLIP labels unstable.",
            "consensus_stable": "Candidates where all three MLIPs agree stable.",
            "consensus_unstable": "Candidates where all three MLIPs agree unstable.",
            "disagreement": "Candidates where three MLIPs do not all agree.",
        },
    }


def _side_force_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for validator in VALIDATOR_ORDER:
        buckets: dict[str, list[float]] = {
            "all_validated": [],
            "model_stable": [],
            "model_unstable": [],
            "consensus_stable": [],
            "consensus_unstable": [],
            "disagreement": [],
        }
        for row in rows:
            value = _validator_value(row, validator, "force_max")
            if value is None:
                continue
            buckets["all_validated"].append(value)
            validators = row.get("validators") if isinstance(row.get("validators"), dict) else {}
            model_data = validators.get(validator) if isinstance(validators.get(validator), dict) else {}
            if model_data.get("is_stable") is True:
                buckets["model_stable"].append(value)
            elif model_data.get("is_stable") is False:
                buckets["model_unstable"].append(value)
            consensus = row.get("consensus_is_stable")
            if consensus is True:
                buckets["consensus_stable"].append(value)
            elif consensus is False:
                buckets["consensus_unstable"].append(value)
            else:
                buckets["disagreement"].append(value)
        stats[validator] = {name: _distribution(values) for name, values in buckets.items()}
    return stats


def _force_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for validator in VALIDATOR_ORDER:
        delta[validator] = {}
        before_validator = before.get(validator, {})
        after_validator = after.get(validator, {})
        for subset in sorted(set(before_validator) | set(after_validator)):
            delta[validator][subset] = {}
            before_subset = before_validator.get(subset, {})
            after_subset = after_validator.get(subset, {})
            for key in ("count", "mean", "median", "p90", "p95", "max"):
                delta[validator][subset][key] = _subtract(after_subset.get(key), before_subset.get(key))
    return delta


def _force_stats_by_formula(
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before = _side_formula_force_stats(before_rows)
    after = _side_formula_force_stats(after_rows)
    rows: list[dict[str, Any]] = []
    formulas = sorted(set(before) | set(after))
    for formula in formulas:
        for validator in VALIDATOR_ORDER:
            row: dict[str, Any] = {"formula": formula, "validator": validator}
            before_stats = before.get(formula, {}).get(validator, {})
            after_stats = after.get(formula, {}).get(validator, {})
            for subset in ("all_validated", "model_stable", "consensus_stable", "disagreement"):
                left = before_stats.get(subset, _distribution([]))
                right = after_stats.get(subset, _distribution([]))
                for key in ("count", "mean", "median", "p90"):
                    row[f"before_{subset}_{key}"] = left.get(key)
                    row[f"after_{subset}_{key}"] = right.get(key)
                    row[f"delta_{subset}_{key}"] = _subtract(right.get(key), left.get(key))
            rows.append(row)
    return rows


def _side_formula_force_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    buckets: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: {
            validator: {
                "all_validated": [],
                "model_stable": [],
                "consensus_stable": [],
                "disagreement": [],
            }
            for validator in VALIDATOR_ORDER
        }
    )
    for row in rows:
        formula = _formula(row)
        if not formula:
            continue
        validators = row.get("validators") if isinstance(row.get("validators"), dict) else {}
        consensus = row.get("consensus_is_stable")
        for validator in VALIDATOR_ORDER:
            value = _validator_value(row, validator, "force_max")
            if value is None:
                continue
            validator_buckets = buckets[formula][validator]
            validator_buckets["all_validated"].append(value)
            data = validators.get(validator) if isinstance(validators.get(validator), dict) else {}
            if data.get("is_stable") is True:
                validator_buckets["model_stable"].append(value)
            if consensus is True:
                validator_buckets["consensus_stable"].append(value)
            elif consensus is None:
                validator_buckets["disagreement"].append(value)

    stats: dict[str, dict[str, dict[str, Any]]] = {}
    for formula, validator_buckets in buckets.items():
        stats[formula] = {}
        for validator, subset_buckets in validator_buckets.items():
            stats[formula][validator] = {
                subset: _distribution(values) for subset, values in subset_buckets.items()
            }
    return stats


def _top_per_formula(candidates: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[row["formula"]].append(row)
    top_rows: list[dict[str, Any]] = []
    for formula in sorted(grouped):
        for rank, row in enumerate(grouped[formula][:count], start=1):
            ranked = dict(row)
            ranked["rank_within_formula"] = rank
            top_rows.append(ranked)
    return top_rows


def _summary(
    comparison: dict[str, Any],
    per_formula: list[dict[str, Any]],
    high_confidence: list[dict[str, Any]],
    samples_per_formula: int,
    args: argparse.Namespace,
    global_force_stats: dict[str, Any],
) -> dict[str, Any]:
    stable_deltas = [row["delta_stable_consensus_count"] for row in per_formula]
    rate_deltas = [row["delta_stable_consensus_rate_generated"] for row in per_formula]
    high_force_values = [row["max_force"] for row in high_confidence]
    formula_positive = [row for row in per_formula if row["delta_stable_consensus_count"] > 0]
    formula_negative = [row for row in per_formula if row["delta_stable_consensus_count"] < 0]
    formula_zero = [row for row in per_formula if row["delta_stable_consensus_count"] == 0]
    return {
        "workflow": "f3_rank_neighbor_detailed_validation_analysis",
        "generated_at": date.today().isoformat(),
        "formula_count": len(per_formula),
        "samples_per_formula": samples_per_formula,
        "global_before_after": {
            "before_stable_consensus_count": comparison.get("before", {}).get("strict_three_mlip_stable_consensus_count"),
            "after_stable_consensus_count": comparison.get("after", {}).get("strict_three_mlip_stable_consensus_count"),
            "stable_consensus_count_delta": comparison.get("delta", {}).get("strict_three_mlip_stable_consensus_count"),
            "before_stable_consensus_rate": comparison.get("before", {}).get("stable_consensus_rate"),
            "after_stable_consensus_rate": comparison.get("after", {}).get("stable_consensus_rate"),
            "stable_consensus_rate_delta": comparison.get("delta", {}).get("stable_consensus_rate"),
            "before_disagreement_count": comparison.get("before", {}).get("disagreement_count"),
            "after_disagreement_count": comparison.get("after", {}).get("disagreement_count"),
            "disagreement_count_delta": comparison.get("delta", {}).get("disagreement_count"),
            "before_unique_sequence_fraction": comparison.get("before", {}).get("unique_sequence_fraction"),
            "after_unique_sequence_fraction": comparison.get("after", {}).get("unique_sequence_fraction"),
            "unique_sequence_fraction_delta": comparison.get("delta", {}).get("unique_sequence_fraction"),
        },
        "stable_consensus_delta_total": sum(stable_deltas),
        "stable_consensus_delta_formula_counts": {
            "positive": len(formula_positive),
            "zero": len(formula_zero),
            "negative": len(formula_negative),
        },
        "stable_consensus_delta_distribution": {
            "min": min(stable_deltas) if stable_deltas else None,
            "max": max(stable_deltas) if stable_deltas else None,
            "mean": statistics.fmean(stable_deltas) if stable_deltas else None,
            "median": statistics.median(stable_deltas) if stable_deltas else None,
            "rate_delta_mean": statistics.fmean(rate_deltas) if rate_deltas else None,
            "rate_delta_median": statistics.median(rate_deltas) if rate_deltas else None,
        },
        "top_improved_formulas": _project_formulas(
            sorted(per_formula, key=lambda row: (row["delta_stable_consensus_count"], row["after_stable_consensus_count"]), reverse=True)[:12]
        ),
        "top_regressed_formulas": _project_formulas(
            sorted(per_formula, key=lambda row: (row["delta_stable_consensus_count"], row["after_stable_consensus_count"]))[:12]
        ),
        "high_confidence": {
            "count": len(high_confidence),
            "force_max_threshold": args.high_confidence_force_max,
            "tier_a_threshold": args.tier_a_force_max,
            "tier_b_threshold": args.tier_b_force_max,
            "tier_a_count": sum(1 for row in high_confidence if row["confidence_tier"] == "A_force_le_0.03"),
            "tier_b_count": sum(1 for row in high_confidence if row["confidence_tier"] == "B_force_le_0.04"),
            "tier_c_count": sum(1 for row in high_confidence if row["confidence_tier"] == "C_consensus_0.05"),
            "formula_count_with_high_confidence": len(set(row["formula"] for row in high_confidence)),
            "max_force_min": min(high_force_values) if high_force_values else None,
            "max_force_median": _median(high_force_values),
            "max_force_p90": _percentile(high_force_values, 0.9),
            "max_force_max": max(high_force_values) if high_force_values else None,
            "top_formula_counts": Counter(row["formula"] for row in high_confidence).most_common(12),
        },
        "force_stats": global_force_stats,
        "caveat": "All labels are MLIP relaxation consensus proxy evidence, not DFT or hull-confirmed stability.",
    }


def _project_formulas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [
        "formula",
        "before_stable_consensus_count",
        "after_stable_consensus_count",
        "delta_stable_consensus_count",
        "before_stable_consensus_rate_generated",
        "after_stable_consensus_rate_generated",
        "delta_stable_consensus_rate_generated",
        "before_disagreement_count",
        "after_disagreement_count",
        "delta_disagreement_count",
        "after_high_confidence_count",
    ]
    return [{key: row.get(key) for key in keys} for row in rows]


def _formula(row: dict[str, Any]) -> str:
    return str(row.get("formula") or row.get("composition") or "")


def _spacegroup(row: dict[str, Any]) -> Any:
    return (
        row.get("spacegroup")
        or row.get("space_group")
        or _nested(row, ("condition", "spacegroup"))
        or _nested(row, ("failure_vector", "metadata", "space_group"))
        or _nested(row, ("metadata", "raw_g"))
    )


def _spacegroup_from_consensus_or_selected(row: dict[str, Any], selected: dict[str, Any]) -> Any:
    return row.get("spacegroup") or _spacegroup(selected)


def _validator_values(row: dict[str, Any], key: str) -> list[float]:
    values = []
    validators = row.get("validators") if isinstance(row.get("validators"), dict) else {}
    for validator in VALIDATOR_ORDER:
        value = validators.get(validator, {}).get(key) if isinstance(validators.get(validator), dict) else None
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return values


def _validator_value(row: dict[str, Any], validator: str, key: str) -> float | None:
    validators = row.get("validators") if isinstance(row.get("validators"), dict) else {}
    data = validators.get(validator)
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else None


def _nested(row: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = row
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _candidate_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    tier_rank = {"A_force_le_0.03": 0, "B_force_le_0.04": 1, "C_consensus_0.05": 2}
    return (
        tier_rank.get(str(row.get("confidence_tier")), 9),
        row.get("max_force") if row.get("max_force") is not None else float("inf"),
        row.get("mean_force") if row.get("mean_force") is not None else float("inf"),
        row.get("force_spread") if row.get("force_spread") is not None else float("inf"),
        str(row.get("candidate_id")),
    )


def _ratio(numerator: Any, denominator: Any) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        return None
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _subtract(right: Any, left: Any) -> float | int | None:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return right - left
    return None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p90": None,
            "p95": None,
            "max": None,
        }
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p90": _percentile(values, 0.9),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return repr(value)
    return value


def _formula_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "formula",
        "before stable",
        "after stable",
        "delta",
        "before rate",
        "after rate",
        "after high-conf",
        "delta disagree",
    ]
    lines = [
        "# Per-Formula F3 Validation Metrics",
        "",
        "| " + " | ".join(headers) + " |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(rows, key=lambda item: item["formula"]):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["formula"]),
                    str(row["before_stable_consensus_count"]),
                    str(row["after_stable_consensus_count"]),
                    str(row["delta_stable_consensus_count"]),
                    _fmt(row["before_stable_consensus_rate_generated"]),
                    _fmt(row["after_stable_consensus_rate_generated"]),
                    str(row["after_high_confidence_count"]),
                    str(row["delta_disagreement_count"]),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _candidate_table(rows: list[dict[str, Any]]) -> str:
    headers = ["formula", "rank", "candidate_id", "tier", "sg", "max force", "mean force", "energy range"]
    lines = [
        "# High-Confidence Candidates, Top Per Formula",
        "",
        "| " + " | ".join(headers) + " |",
        "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("formula")),
                    str(row.get("rank_within_formula")),
                    str(row.get("candidate_id")),
                    str(row.get("confidence_tier")),
                    str(row.get("spacegroup")),
                    _fmt(row.get("max_force")),
                    _fmt(row.get("mean_force")),
                    _fmt(row.get("energy_range")),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _force_formula_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Per-Formula MLIP Force Statistics",
        "",
        "| formula | validator | before mean F | after mean F | delta mean F | before stable mean F | after stable mean F | delta stable mean F |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["formula"]),
                    str(row["validator"]),
                    _fmt(row.get("before_all_validated_mean")),
                    _fmt(row.get("after_all_validated_mean")),
                    _fmt(row.get("delta_all_validated_mean")),
                    _fmt(row.get("before_consensus_stable_mean")),
                    _fmt(row.get("after_consensus_stable_mean")),
                    _fmt(row.get("delta_consensus_stable_mean")),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _report(summary: dict[str, Any], per_formula: list[dict[str, Any]], top_candidates: list[dict[str, Any]]) -> str:
    improved = summary["top_improved_formulas"][:8]
    regressed = summary["top_regressed_formulas"][:8]
    lines = [
        "# Detailed F3 Rank-Neighbor Validation Analysis",
        "",
        "## Global",
        "",
        f"- Formula count: {summary['formula_count']}",
        f"- Stable consensus delta total: {summary['stable_consensus_delta_total']}",
        f"- Positive/zero/negative formula deltas: {summary['stable_consensus_delta_formula_counts']}",
        f"- High-confidence candidates: {summary['high_confidence']['count']}",
        f"- Tier A/B/C counts: {summary['high_confidence']['tier_a_count']} / "
        f"{summary['high_confidence']['tier_b_count']} / {summary['high_confidence']['tier_c_count']}",
        "",
        "## Global MLIP Force Change",
        "",
        _global_force_table(summary["force_stats"]),
        "",
        "## Top Improved Formulas",
        "",
        _mini_formula_table(improved),
        "",
        "## Top Regressed Formulas",
        "",
        _mini_formula_table(regressed),
        "",
        "## Best High-Confidence Candidates",
        "",
        _candidate_table(top_candidates[:20]),
        "",
        "## Caveat",
        "",
        summary["caveat"],
        "",
    ]
    return "\n".join(lines)


def _global_force_table(force_stats: dict[str, Any]) -> str:
    before = force_stats.get("before", {})
    after = force_stats.get("after", {})
    delta = force_stats.get("delta", {})
    lines = [
        "| validator | subset | before mean F | after mean F | delta mean F | before median F | after median F | delta median F |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for validator in VALIDATOR_ORDER:
        for subset in ("all_validated", "consensus_stable", "model_stable", "disagreement", "consensus_unstable"):
            lines.append(
                f"| {validator} | {subset} | "
                f"{_fmt(before.get(validator, {}).get(subset, {}).get('mean'))} | "
                f"{_fmt(after.get(validator, {}).get(subset, {}).get('mean'))} | "
                f"{_fmt(delta.get(validator, {}).get(subset, {}).get('mean'))} | "
                f"{_fmt(before.get(validator, {}).get(subset, {}).get('median'))} | "
                f"{_fmt(after.get(validator, {}).get(subset, {}).get('median'))} | "
                f"{_fmt(delta.get(validator, {}).get(subset, {}).get('median'))} |"
            )
    return "\n".join(lines)


def _mini_formula_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| formula | before stable | after stable | delta | after high-conf | delta disagree |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['formula']} | {row['before_stable_consensus_count']} | "
            f"{row['after_stable_consensus_count']} | {row['delta_stable_consensus_count']} | "
            f"{row['after_high_confidence_count']} | {row['delta_disagreement_count']} |"
        )
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return "" if value is None else str(value)


if __name__ == "__main__":
    main()
