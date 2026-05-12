#!/usr/bin/env python
"""Build conservative MLIP relaxation consensus evidence from normalized rows."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT in sys.path:
    sys.path.remove(PROJECT_ROOT_TEXT)
sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.io import read_jsonl, write_json, write_jsonl


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine normalized MLIP relaxation validation JSONL files into an all-agree consensus artifact."
    )
    parser.add_argument(
        "--validation",
        action="append",
        required=True,
        help="Validator input as NAME=path/to/normalized/validation_results.jsonl. Repeat for each MLIP.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--validator-name")
    parser.add_argument("--validation-source")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    validations = [_parse_validation_arg(item) for item in args.validation]
    if len(validations) < 2:
        raise SystemExit("at least two --validation NAME=PATH inputs are required")
    names = [name for name, _ in validations]
    if len(set(names)) != len(names):
        raise SystemExit("validator names must be unique")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    validator_name = args.validator_name or "+".join(names)
    validation_source = args.validation_source or f"local_mlip_{'_'.join(names)}_relaxation_consensus"

    datasets = {name: _load_by_candidate(path) for name, path in validations}
    overlap_ids = sorted(set.intersection(*(set(rows) for rows in datasets.values())))
    comparison_rows = [
        _comparison_row(candidate_id, datasets, validations)
        for candidate_id in overlap_ids
    ]
    consensus_rows = [
        _consensus_row(
            comparison,
            datasets=datasets,
            validations=validations,
            validator_name=validator_name,
            validation_source=validation_source,
        )
        for comparison in comparison_rows
    ]
    consensus_rows.sort(key=lambda row: (str(row.get("formula")), str(row.get("candidate_id"))))
    comparison_rows.sort(key=lambda row: (str(row.get("formula")), str(row.get("candidate_id"))))

    summary = _summary(names, validations, comparison_rows, consensus_rows)
    write_jsonl(output_dir / "comparison_rows.jsonl", comparison_rows)
    write_jsonl(output_dir / "consensus_validation_results.jsonl", consensus_rows)
    write_json(output_dir / "summary.json", summary)
    (output_dir / "report.md").write_text(_report(summary), encoding="utf-8")
    print(f"MLIP ensemble consensus complete: {output_dir}")
    print(f"  overlap_count: {summary['overlap_count']}")
    print(f"  f3_available_candidate_count: {summary['f3_available_candidate_count']}")
    print(f"  disagreement_or_unavailable_count: {summary['disagreement_or_unavailable_count']}")
    return {"summary": summary, "rows": consensus_rows, "comparison_rows": comparison_rows}


def _parse_validation_arg(item: str) -> tuple[str, Path]:
    if "=" not in item:
        raise SystemExit(f"--validation must be NAME=PATH, got: {item}")
    name, path = item.split("=", 1)
    name = name.strip()
    if not name:
        raise SystemExit(f"empty validator name in --validation: {item}")
    return name, Path(path)


def _load_by_candidate(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id:
            continue
        rows[candidate_id] = row
    return rows


def _comparison_row(
    candidate_id: str,
    datasets: dict[str, dict[str, dict[str, Any]]],
    validations: list[tuple[str, Path]],
) -> dict[str, Any]:
    rows = {name: datasets[name][candidate_id] for name, _ in validations}
    labels = {name: row.get("is_stable") for name, row in rows.items()}
    bool_labels = [value for value in labels.values() if isinstance(value, bool)]
    agreement = len(bool_labels) == len(labels) and len(set(bool_labels)) == 1
    stable_votes = sum(1 for value in bool_labels if value is True)
    unstable_votes = sum(1 for value in bool_labels if value is False)
    first = next(iter(rows.values()))
    return {
        "candidate_id": candidate_id,
        "formula": first.get("formula"),
        "agreement": agreement,
        "available_votes": len(bool_labels),
        "stable_votes": stable_votes,
        "unstable_votes": unstable_votes,
        "vote_pattern": _vote_pattern(labels),
        "consensus_is_stable": bool_labels[0] if agreement else None,
        "validators": {
            name: {
                "is_stable": row.get("is_stable"),
                "force_max": row.get("force_max"),
                "stress_max": row.get("stress_max"),
                "relaxation_converged": row.get("relaxation_converged"),
                "energy_eV_per_atom": _energy_per_atom(row),
                "validation_status": row.get("validation_status"),
            }
            for name, row in rows.items()
        },
    }


def _consensus_row(
    comparison: dict[str, Any],
    *,
    datasets: dict[str, dict[str, dict[str, Any]]],
    validations: list[tuple[str, Path]],
    validator_name: str,
    validation_source: str,
) -> dict[str, Any]:
    candidate_id = str(comparison["candidate_id"])
    rows = {name: datasets[name][candidate_id] for name, _ in validations}
    first = next(iter(rows.values()))
    agreement = bool(comparison["agreement"])
    consensus_is_stable = comparison["consensus_is_stable"] if agreement else None
    max_force = _max_present(row.get("force_max") for row in rows.values())
    max_stress = _max_present(row.get("stress_max") for row in rows.values())
    all_converged = all(row.get("relaxation_converged") is True for row in rows.values())
    row = {
        "candidate_id": candidate_id,
        "formula": first.get("formula"),
        "validation_status": "completed",
        "validator": validator_name,
        "validation_source": validation_source,
        "calibration_tier": "tier2_mlip_ensemble" if agreement else "tier3_mlip_disagreement",
        "energy_above_hull": None,
        "formation_energy": None,
        "relaxed": all(bool(source.get("relaxed")) for source in rows.values()),
        "relaxation_converged": all_converged if agreement else None,
        "force_max": max_force,
        "stress_max": max_stress,
        "uncertainty": 0.0 if agreement else 1.0,
        "spacegroup": first.get("spacegroup"),
        "source_checkpoint": first.get("source_checkpoint"),
        "generation_condition": first.get("generation_condition"),
        "top_k": first.get("top_k"),
        "K": first.get("K"),
        "temperature": first.get("temperature"),
        "condition": first.get("condition"),
        "is_stable": consensus_is_stable,
        "relaxed_structure_ref": None,
        "error_reason": None if agreement else _disagreement_reason(comparison),
        "metadata": {
            "script": "scripts/build_mlip_ensemble_consensus.py",
            "ensemble_policy": "require_all_matching_binary_relaxation_proxy_labels",
            "validator_count": len(validations),
            "available_votes": comparison["available_votes"],
            "stable_votes": comparison["stable_votes"],
            "unstable_votes": comparison["unstable_votes"],
            "vote_pattern": comparison["vote_pattern"],
            "f3_available_after_consensus": agreement,
            "local_only": True,
            "downloads": False,
            "runs_dft": False,
            "runs_generation": False,
            "runs_mlip": False,
            "runs_training": False,
            "calls_external_apis": False,
            "caveat": "Relaxation consensus is still MLIP proxy evidence, not DFT or hull-confirmed stability.",
        },
    }
    for name, path in validations:
        source = rows[name]
        row["metadata"].update(
            {
                f"{name}_validation_jsonl": str(path),
                f"{name}_is_stable": source.get("is_stable"),
                f"{name}_force_max": source.get("force_max"),
                f"{name}_stress_max": source.get("stress_max"),
                f"{name}_relaxation_converged": source.get("relaxation_converged"),
                f"{name}_energy_eV_per_atom": _energy_per_atom(source),
            }
        )
    return row


def _summary(
    names: list[str],
    validations: list[tuple[str, Path]],
    comparison_rows: list[dict[str, Any]],
    consensus_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    vote_patterns = Counter(str(row["vote_pattern"]) for row in comparison_rows)
    agreement_count = sum(1 for row in comparison_rows if row["agreement"])
    stable_count = sum(1 for row in consensus_rows if row.get("is_stable") is True)
    unstable_count = sum(1 for row in consensus_rows if row.get("is_stable") is False)
    validator_stable_counts = {
        name: sum(1 for row in comparison_rows if row["validators"][name]["is_stable"] is True)
        for name in names
    }
    pairwise = _pairwise_agreements(names, comparison_rows)
    return {
        "workflow": "mlip_relaxation_ensemble_consensus",
        "validator_names": names,
        "validation_inputs": {name: str(path) for name, path in validations},
        "overlap_count": len(comparison_rows),
        "formula_count": len({str(row.get("formula")) for row in comparison_rows}),
        "agreement_count": agreement_count,
        "agreement_rate": agreement_count / len(comparison_rows) if comparison_rows else None,
        "f3_available_candidate_count": stable_count + unstable_count,
        "stable_consensus_count": stable_count,
        "unstable_consensus_count": unstable_count,
        "disagreement_or_unavailable_count": len(comparison_rows) - agreement_count,
        "validator_stable_counts": validator_stable_counts,
        "vote_pattern_counts": dict(sorted(vote_patterns.items())),
        "pairwise_agreement": pairwise,
        "local_only": True,
        "runs_dft": False,
        "runs_generation": False,
        "runs_mlip": False,
        "runs_training": False,
        "downloads": False,
        "calls_external_apis": False,
        "caveat": "Consensus labels are relaxation-threshold MLIP proxy evidence, not DFT or hull-confirmed stability.",
    }


def _pairwise_agreements(names: list[str], comparison_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            compared = 0
            agreed = 0
            left_energy: list[float] = []
            right_energy: list[float] = []
            for row in comparison_rows:
                left_label = row["validators"][left]["is_stable"]
                right_label = row["validators"][right]["is_stable"]
                if isinstance(left_label, bool) and isinstance(right_label, bool):
                    compared += 1
                    agreed += int(left_label == right_label)
                left_e = row["validators"][left]["energy_eV_per_atom"]
                right_e = row["validators"][right]["energy_eV_per_atom"]
                if isinstance(left_e, int | float) and isinstance(right_e, int | float):
                    left_energy.append(float(left_e))
                    right_energy.append(float(right_e))
            key = f"{left}__{right}"
            out[key] = {
                "compared_count": compared,
                "agreement_count": agreed,
                "agreement_rate": agreed / compared if compared else None,
                "energy_pearson": _pearson(left_energy, right_energy),
            }
    return out


def _energy_per_atom(row: dict[str, Any]) -> float | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    keys = (
        "mace_total_energy_eV_per_atom",
        "chgnet_energy_eV_per_atom",
        "matgl_total_energy_eV_per_atom",
    )
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, int | float):
            return float(value)
    for key, value in metadata.items():
        if key.endswith("energy_eV_per_atom") and isinstance(value, int | float):
            return float(value)
    return None


def _vote_pattern(labels: dict[str, Any]) -> str:
    parts = []
    for name in sorted(labels):
        value = labels[name]
        label = "stable" if value is True else "unstable" if value is False else "unknown"
        parts.append(f"{name}:{label}")
    return "|".join(parts)


def _disagreement_reason(comparison: dict[str, Any]) -> str:
    if comparison["available_votes"] < len(comparison["validators"]):
        return "mlip_relaxation_proxy_unavailable"
    return "mlip_relaxation_proxy_disagreement"


def _max_present(values: Any) -> float | None:
    present = [float(value) for value in values if isinstance(value, int | float)]
    return max(present) if present else None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if x_den == 0 or y_den == 0:
        return None
    return numerator / (x_den * y_den)


def _report(summary: dict[str, Any]) -> str:
    lines = [
        "# MLIP Relaxation Ensemble Consensus",
        "",
        f"- Validators: {', '.join(summary['validator_names'])}",
        f"- Overlap candidates: {summary['overlap_count']}",
        f"- Formula count: {summary['formula_count']}",
        f"- Agreement rate: {summary['agreement_rate']}",
        f"- F3-available consensus candidates: {summary['f3_available_candidate_count']}",
        f"- Stable consensus: {summary['stable_consensus_count']}",
        f"- Unstable consensus: {summary['unstable_consensus_count']}",
        f"- Disagreement or unavailable: {summary['disagreement_or_unavailable_count']}",
        "",
        "## Pairwise Agreement",
    ]
    for name, stats in summary["pairwise_agreement"].items():
        lines.append(
            f"- {name}: agreement_rate={stats['agreement_rate']}, energy_pearson={stats['energy_pearson']}"
        )
    lines.extend(["", "## Caveat", "", str(summary["caveat"])])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
