#!/usr/bin/env python
"""Summarize local MACE validation results without changing source runs."""

from __future__ import annotations

import argparse
import json
import math
import platform
import socket
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import read_json, read_jsonl, write_json, write_jsonl


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize local MACE validation JSONL into QA and filtering artifacts."
    )
    parser.add_argument("--validation-jsonl", required=True)
    parser.add_argument("--output-dir", default="outputs/mlip_validation_mace_analysis")
    parser.add_argument("--normalized-summary")
    parser.add_argument("--batch-summary")
    parser.add_argument("--relax-candidates-per-formula", type=int, default=5)
    parser.add_argument("--relax-force-max", type=float, default=5.0)
    parser.add_argument("--relax-stress-max", type=float, default=0.2)
    parser.add_argument("--high-force-threshold", type=float, default=50.0)
    parser.add_argument("--high-stress-threshold", type=float, default=1.0)
    parser.add_argument("--max-outliers", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.relax_candidates_per_formula < 0:
        raise SystemExit("--relax-candidates-per-formula must be non-negative")
    if args.max_outliers < 1:
        raise SystemExit("--max-outliers must be positive")

    rows = read_jsonl(args.validation_jsonl)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_summary = _optional_json(args.normalized_summary)
    batch_summary = _optional_json(args.batch_summary)
    formula_table = _formula_table(
        rows,
        high_force_threshold=args.high_force_threshold,
        high_stress_threshold=args.high_stress_threshold,
        relax_force_max=args.relax_force_max,
        relax_stress_max=args.relax_stress_max,
    )
    outliers = _outliers(
        rows,
        high_force_threshold=args.high_force_threshold,
        high_stress_threshold=args.high_stress_threshold,
        max_outliers=args.max_outliers,
    )
    relaxation_candidates = _relaxation_candidates(
        rows,
        per_formula=args.relax_candidates_per_formula,
        force_max=args.relax_force_max,
        stress_max=args.relax_stress_max,
    )
    summary = _summary(
        rows,
        formula_table=formula_table,
        outliers=outliers,
        relaxation_candidates=relaxation_candidates,
        validation_jsonl=Path(args.validation_jsonl),
        output_dir=output_dir,
        normalized_summary=normalized_summary,
        batch_summary=batch_summary,
        args=args,
    )
    files = _write_outputs(output_dir, summary, formula_table, outliers, relaxation_candidates)
    _print_summary(summary, files)
    return {"summary": summary, "files": files}


def _summary(
    rows: list[dict[str, Any]],
    *,
    formula_table: list[dict[str, Any]],
    outliers: list[dict[str, Any]],
    relaxation_candidates: list[dict[str, Any]],
    validation_jsonl: Path,
    output_dir: Path,
    normalized_summary: dict[str, Any] | None,
    batch_summary: dict[str, Any] | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("validation_status", "unknown")) for row in rows)
    formulas = sorted({str(row.get("formula")) for row in rows if row.get("formula")})
    force_values = [_number(row.get("force_max")) for row in rows]
    stress_values = [_number(row.get("stress_max")) for row in rows]
    energy_values = [_energy_per_atom(row) for row in rows]
    return {
        "workflow": "mace_validation_result_summary",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "validation_jsonl": str(validation_jsonl),
        "output_dir": str(output_dir),
        "row_count": len(rows),
        "formula_count": len(formulas),
        "status_counts": dict(sorted(status_counts.items())),
        "completed_count": status_counts.get("completed", 0),
        "failed_count": status_counts.get("failed", 0),
        "f3_available_candidate_count": _f3_available_count(rows),
        "force_max": _metric_summary(force_values),
        "stress_max": _metric_summary(stress_values),
        "mace_total_energy_eV_per_atom": _metric_summary(energy_values),
        "high_force_threshold": args.high_force_threshold,
        "high_force_count": sum(_is_number(value) and value > args.high_force_threshold for value in force_values),
        "high_stress_threshold": args.high_stress_threshold,
        "high_stress_count": sum(_is_number(value) and value > args.high_stress_threshold for value in stress_values),
        "relax_force_max": args.relax_force_max,
        "relax_stress_max": args.relax_stress_max,
        "relaxation_candidate_count": len(relaxation_candidates),
        "outlier_count": len(outliers),
        "formula_table_count": len(formula_table),
        "normalized_summary": normalized_summary,
        "batch_summary": batch_summary,
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
        "notes": [
            "MACE single-point force/stress evidence is not an F3 stability label.",
            "energy_above_hull and is_stable remain unavailable unless supplied by a separate local validation workflow.",
            "Relaxation candidates are only a triage queue, not stable materials.",
        ],
    }


def _formula_table(
    rows: list[dict[str, Any]],
    *,
    high_force_threshold: float,
    high_stress_threshold: float,
    relax_force_max: float,
    relax_stress_max: float,
) -> list[dict[str, Any]]:
    by_formula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_formula[str(row.get("formula", "unknown"))].append(row)
    table = []
    for formula in sorted(by_formula):
        items = by_formula[formula]
        force_values = [_number(row.get("force_max")) for row in items]
        stress_values = [_number(row.get("stress_max")) for row in items]
        energy_values = [_energy_per_atom(row) for row in items]
        completed = sum(str(row.get("validation_status")) == "completed" for row in items)
        high_force = sum(_is_number(value) and value > high_force_threshold for value in force_values)
        high_stress = sum(_is_number(value) and value > high_stress_threshold for value in stress_values)
        relax_candidates = [
            row for row in items
            if _relax_candidate(row, force_max=relax_force_max, stress_max=relax_stress_max)
        ]
        worst_force = _worst_row(items, "force_max")
        table.append(
            {
                "formula": formula,
                "row_count": len(items),
                "completed_count": completed,
                "failed_count": sum(str(row.get("validation_status")) == "failed" for row in items),
                "force_max_p50": _quantile(force_values, 0.5),
                "force_max_p90": _quantile(force_values, 0.9),
                "force_max_max": _max_number(force_values),
                "stress_max_p50": _quantile(stress_values, 0.5),
                "stress_max_p90": _quantile(stress_values, 0.9),
                "stress_max_max": _max_number(stress_values),
                "energy_eV_per_atom_p50": _quantile(energy_values, 0.5),
                "energy_eV_per_atom_p90": _quantile(energy_values, 0.9),
                "high_force_count": high_force,
                "high_force_rate": _rate(high_force, len(items)),
                "high_stress_count": high_stress,
                "high_stress_rate": _rate(high_stress, len(items)),
                "relaxation_candidate_count": len(relax_candidates),
                "worst_force_candidate_id": None if worst_force is None else worst_force.get("candidate_id"),
            }
        )
    return table


def _outliers(
    rows: list[dict[str, Any]],
    *,
    high_force_threshold: float,
    high_stress_threshold: float,
    max_outliers: int,
) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        force = _number(row.get("force_max"))
        stress = _number(row.get("stress_max"))
        reasons = []
        score = 0.0
        if _is_number(force) and force > high_force_threshold:
            reasons.append("high_force")
            score = max(score, force / high_force_threshold)
        if _is_number(stress) and stress > high_stress_threshold:
            reasons.append("high_stress")
            score = max(score, stress / high_stress_threshold)
        if reasons:
            out.append(_compact_row(row, reasons=reasons, severity_score=score))
    return sorted(out, key=lambda row: (-float(row["severity_score"]), row["formula"], row["candidate_id"]))[:max_outliers]


def _relaxation_candidates(
    rows: list[dict[str, Any]],
    *,
    per_formula: int,
    force_max: float,
    stress_max: float,
) -> list[dict[str, Any]]:
    if per_formula == 0:
        return []
    by_formula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _relax_candidate(row, force_max=force_max, stress_max=stress_max):
            by_formula[str(row.get("formula", "unknown"))].append(row)
    selected = []
    for formula in sorted(by_formula):
        candidates = sorted(
            by_formula[formula],
            key=lambda row: (
                _number(row.get("force_max")) or float("inf"),
                _number(row.get("stress_max")) or float("inf"),
                _energy_per_atom(row) or float("inf"),
                str(row.get("candidate_id")),
            ),
        )
        selected.extend(_compact_row(row, reasons=["relaxation_candidate"], severity_score=0.0) for row in candidates[:per_formula])
    return selected


def _relax_candidate(row: dict[str, Any], *, force_max: float, stress_max: float) -> bool:
    force = _number(row.get("force_max"))
    stress = _number(row.get("stress_max"))
    return (
        str(row.get("validation_status")) == "completed"
        and _is_number(force)
        and force <= force_max
        and (stress is None or (_is_number(stress) and stress <= stress_max))
    )


def _compact_row(row: dict[str, Any], *, reasons: list[str], severity_score: float) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "candidate_id": row.get("candidate_id"),
        "formula": row.get("formula"),
        "validation_status": row.get("validation_status"),
        "force_max": row.get("force_max"),
        "stress_max": row.get("stress_max"),
        "mace_total_energy_eV_per_atom": metadata.get("mace_total_energy_eV_per_atom"),
        "spacegroup": row.get("spacegroup"),
        "reasons": reasons,
        "severity_score": severity_score,
    }


def _write_outputs(
    output_dir: Path,
    summary: dict[str, Any],
    formula_table: list[dict[str, Any]],
    outliers: list[dict[str, Any]],
    relaxation_candidates: list[dict[str, Any]],
) -> dict[str, str]:
    summary_path = output_dir / "mace_validation_analysis_summary.json"
    formula_jsonl = output_dir / "formula_table.jsonl"
    formula_md = output_dir / "formula_table.md"
    outliers_jsonl = output_dir / "outliers.jsonl"
    outliers_md = output_dir / "outliers.md"
    relaxation_jsonl = output_dir / "relaxation_candidates.jsonl"
    relaxation_md = output_dir / "relaxation_candidates.md"
    report = output_dir / "report.md"
    write_json(summary_path, summary)
    write_jsonl(formula_jsonl, formula_table)
    write_jsonl(outliers_jsonl, outliers)
    write_jsonl(relaxation_jsonl, relaxation_candidates)
    formula_md.write_text(_formula_markdown(formula_table), encoding="utf-8")
    outliers_md.write_text(_compact_markdown("MACE Outliers", outliers), encoding="utf-8")
    relaxation_md.write_text(_compact_markdown("MACE Relaxation Candidates", relaxation_candidates), encoding="utf-8")
    report.write_text(_report_markdown(summary), encoding="utf-8")
    return {
        "summary": str(summary_path),
        "formula_table_jsonl": str(formula_jsonl),
        "formula_table_md": str(formula_md),
        "outliers_jsonl": str(outliers_jsonl),
        "outliers_md": str(outliers_md),
        "relaxation_candidates_jsonl": str(relaxation_jsonl),
        "relaxation_candidates_md": str(relaxation_md),
        "report": str(report),
    }


def _report_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# MACE Validation Analysis",
            "",
            "## Boundary",
            "- Reads local MACE validation results only.",
            "- Does not run generation, MLIP, DFT, training, downloads, or external APIs.",
            "- Does not mark candidates as stable or F3-available.",
            "",
            "## Summary",
            f"- row_count: {summary['row_count']}",
            f"- formula_count: {summary['formula_count']}",
            f"- completed_count: {summary['completed_count']}",
            f"- failed_count: {summary['failed_count']}",
            f"- f3_available_candidate_count: {summary['f3_available_candidate_count']}",
            f"- force_max: {summary['force_max']}",
            f"- stress_max: {summary['stress_max']}",
            f"- high_force_count: {summary['high_force_count']}",
            f"- high_stress_count: {summary['high_stress_count']}",
            f"- relaxation_candidate_count: {summary['relaxation_candidate_count']}",
            "",
            "## Notes",
            *[f"- {note}" for note in summary["notes"]],
            "",
        ]
    )


def _formula_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# MACE Formula Table",
        "",
        "| formula | rows | force_p50 | force_p90 | force_max | high_force | relax_candidates |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {formula} | {row_count} | {force_max_p50} | {force_max_p90} | {force_max_max} | {high_force_count} | {relaxation_candidate_count} |".format(
                **{key: _fmt(value) for key, value in row.items()}
            )
        )
    lines.append("")
    return "\n".join(lines)


def _compact_markdown(title: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# {title}",
        "",
        "| candidate_id | formula | force_max | stress_max | energy_eV_per_atom | reasons |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {candidate_id} | {formula} | {force_max} | {stress_max} | {mace_total_energy_eV_per_atom} | {reasons} |".format(
                candidate_id=_fmt(row.get("candidate_id")),
                formula=_fmt(row.get("formula")),
                force_max=_fmt(row.get("force_max")),
                stress_max=_fmt(row.get("stress_max")),
                mace_total_energy_eV_per_atom=_fmt(row.get("mace_total_energy_eV_per_atom")),
                reasons=",".join(str(item) for item in row.get("reasons", [])),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _metric_summary(values: Iterable[float | None]) -> dict[str, Any]:
    vals = _finite_values(values)
    if not vals:
        return {"count": 0, "min": None, "p10": None, "p50": None, "p90": None, "p95": None, "p99": None, "max": None}
    return {
        "count": len(vals),
        "min": min(vals),
        "p10": _quantile(vals, 0.10),
        "p50": _quantile(vals, 0.50),
        "p90": _quantile(vals, 0.90),
        "p95": _quantile(vals, 0.95),
        "p99": _quantile(vals, 0.99),
        "max": max(vals),
    }


def _quantile(values: Iterable[float | None], probability: float) -> float | None:
    vals = sorted(_finite_values(values))
    if not vals:
        return None
    index = (len(vals) - 1) * probability
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return vals[low]
    return vals[low] * (high - index) + vals[high] * (index - low)


def _finite_values(values: Iterable[float | None]) -> list[float]:
    return [float(value) for value in values if _is_number(value)]


def _number(value: Any) -> float | None:
    if value in (None, "", "null", "None", "none"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _max_number(values: Iterable[float | None]) -> float | None:
    vals = _finite_values(values)
    return None if not vals else max(vals)


def _energy_per_atom(row: dict[str, Any]) -> float | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return _number(metadata.get("mace_total_energy_eV_per_atom"))


def _worst_row(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    valid = [row for row in rows if _is_number(_number(row.get(field)))]
    if not valid:
        return None
    return max(valid, key=lambda row: _number(row.get(field)) or float("-inf"))


def _f3_available_count(rows: list[dict[str, Any]]) -> int:
    return sum(
        str(row.get("validation_status", "")).lower() in {"completed", "success", "succeeded", "validated"}
        and (row.get("energy_above_hull") is not None or row.get("is_stable") is not None)
        for row in rows
    )


def _optional_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    source = Path(path)
    if not source.exists():
        return None
    data = read_json(source)
    return data if isinstance(data, dict) else {"value": data}


def _rate(count: int, total: int) -> float:
    return 0.0 if total == 0 else round(count / total, 6)


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _print_summary(summary: dict[str, Any], files: dict[str, str]) -> None:
    print("MACE validation analysis complete")
    print(f"  row_count: {summary['row_count']}")
    print(f"  formula_count: {summary['formula_count']}")
    print(f"  high_force_count: {summary['high_force_count']}")
    print(f"  high_stress_count: {summary['high_stress_count']}")
    print(f"  relaxation_candidate_count: {summary['relaxation_candidate_count']}")
    print(f"  f3_available_candidate_count: {summary['f3_available_candidate_count']}")
    print(f"  summary: {files['summary']}")
    print(f"  report: {files['report']}")


if __name__ == "__main__":
    main()
