#!/usr/bin/env python
"""Summarize per-candidate mean force changes from MLIP comparison rows."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT in sys.path:
    sys.path.remove(PROJECT_ROOT_TEXT)
sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.io import read_json, read_jsonl, write_json


VALIDATORS = ("MACE", "CHGNet", "MatGL")
SUBSETS = ("all_validated", "consensus_stable", "consensus_unstable", "disagreement")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build JSON/CSV/Markdown summary for per-candidate mean of MACE, "
            "CHGNet, and MatGL force_max values."
        )
    )
    parser.add_argument("--comparison-summary", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    comparison = read_json(args.comparison_summary)
    inputs = comparison["inputs"]
    result = {
        "force_quantity": "mean_of_three_mlip_force_max",
        "force_unit": "eV/Angstrom",
        "subsets": {
            "all_validated": "All candidates with completed validator force_max.",
            "consensus_stable": "Candidates where all three MLIPs agree stable.",
            "consensus_unstable": "Candidates where all three MLIPs agree unstable.",
            "disagreement": "Candidates where three MLIPs do not all agree.",
        },
    }
    for side in ("before", "after"):
        rows = read_jsonl(inputs[f"{side}_consensus_comparison"])
        result[side] = _side_stats(rows)
    result["delta"] = _delta_stats(result["before"], result["after"])

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "ensemble_mean_force_stats.json", result)
    table_rows = _table_rows(result)
    _write_csv(output_dir / "ensemble_mean_force_change_summary.csv", table_rows)
    (output_dir / "ensemble_mean_force_change_summary.md").write_text(
        _render_markdown(table_rows), encoding="utf-8"
    )

    print(f"Three-MLIP mean force change summary complete: {output_dir}")
    for row in table_rows:
        print(
            f"  {row['subset']}: mean {row['before_mean_force']:.6f} -> "
            f"{row['after_mean_force']:.6f} ({row['delta_mean_force']:+.6f})"
        )
    return result


def _side_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[float]] = {subset: [] for subset in SUBSETS}
    for row in rows:
        value = _mean_force(row)
        if value is None:
            continue
        buckets["all_validated"].append(value)
        buckets[_subset(row)].append(value)
    return {name: _stats(values) for name, values in buckets.items()}


def _delta_stats(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    delta: dict[str, dict[str, Any]] = {}
    for subset in SUBSETS:
        delta[subset] = {}
        for key in ("count", "mean", "median", "p90", "p95", "max", "min"):
            before_value = before[subset][key]
            after_value = after[subset][key]
            delta[subset][key] = (
                None if before_value is None or after_value is None else after_value - before_value
            )
    return delta


def _mean_force(row: dict[str, Any]) -> float | None:
    validators = row.get("validators") if isinstance(row.get("validators"), dict) else {}
    values = []
    for name in VALIDATORS:
        data = validators.get(name) if isinstance(validators.get(name), dict) else {}
        value = data.get("force_max")
        if isinstance(value, (int, float)) and math.isfinite(value):
            values.append(float(value))
    return sum(values) / len(values) if len(values) == len(VALIDATORS) else None


def _subset(row: dict[str, Any]) -> str:
    if row.get("agreement") is True and row.get("consensus_is_stable") is True:
        return "consensus_stable"
    if row.get("agreement") is True and row.get("consensus_is_stable") is False:
        return "consensus_unstable"
    return "disagreement"


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p90": None, "p95": None, "max": None, "min": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p90": _percentile(values, 0.9),
        "p95": _percentile(values, 0.95),
        "max": max(values),
        "min": min(values),
    }


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _table_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for subset in SUBSETS:
        before = result["before"][subset]
        after = result["after"][subset]
        delta = result["delta"][subset]
        before_mean = before["mean"]
        rows.append(
            {
                "subset": subset,
                "before_count": before["count"],
                "after_count": after["count"],
                "before_mean_force": before_mean,
                "after_mean_force": after["mean"],
                "delta_mean_force": delta["mean"],
                "relative_delta_mean_force": None if not before_mean else delta["mean"] / before_mean,
                "before_median_force": before["median"],
                "after_median_force": after["median"],
                "delta_median_force": delta["median"],
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Three-MLIP Mean Force Change Summary",
        "",
        "Force quantity: per-candidate mean of MACE, CHGNet, and MatGL `force_max` values.",
        "Unit: eV/Angstrom.",
        "",
        "| subset | before count | after count | before mean | after mean | delta mean | relative delta | before median | after median | delta median |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        relative = row["relative_delta_mean_force"]
        lines.append(
            f"| {row['subset']} | {row['before_count']} | {row['after_count']} | "
            f"{row['before_mean_force']:.6f} | {row['after_mean_force']:.6f} | "
            f"{row['delta_mean_force']:+.6f} | {relative:+.2%} | "
            f"{row['before_median_force']:.6f} | {row['after_median_force']:.6f} | "
            f"{row['delta_median_force']:+.6f} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
