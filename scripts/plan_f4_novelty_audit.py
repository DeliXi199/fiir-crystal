#!/usr/bin/env python
"""Plan external F4 novelty/leakage audit tasks without running matching."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import read_jsonl, write_json, write_jsonl
from fiir_crystal.validation import F4_AUDIT_SCHEMA_VERSION


DEFAULT_CANDIDATE_INDEX = Path("outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl")
DEFAULT_OUTPUT_DIR = Path("outputs/f4_novelty_audit/reference_pool_v1")
TASK_SCHEMA_VERSION = "f4-audit-task-v1"
REFERENCE_POOL_MANIFEST_SCHEMA_VERSION = "f4-reference-pool-manifest-v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a deterministic local task plan for an external F4 StructureMatcher-style audit. "
            "This script does not run pymatgen, database queries, downloads, or matching."
        )
    )
    parser.add_argument("--candidate-index", default=str(DEFAULT_CANDIDATE_INDEX))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--reference-pool-id", default="reference_pool_v1")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--shard-count", type=int, default=16)
    parser.add_argument("--sort", choices=("candidate_id", "ranking"), default="candidate_id")
    parser.add_argument("--require-dpo-eligible", action="store_true")
    parser.add_argument("--require-f1-pass", action="store_true")
    parser.add_argument("--require-f2-pass", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.shard_count < 1:
        raise SystemExit("--shard-count must be positive")

    candidate_index = Path(args.candidate_index)
    if not candidate_index.exists():
        raise SystemExit(f"candidate index does not exist: {candidate_index}")

    output_dir = Path(args.output_dir)
    rows = read_jsonl(candidate_index)
    selected, skipped = _select_rows(rows, args)
    if args.limit is not None:
        overflow = selected[args.limit:]
        selected = selected[: args.limit]
        skipped.extend(_skip_row(row, "limit_overflow") for row in overflow)
    if args.strict and not selected:
        raise SystemExit("strict F4 audit planning selected zero candidates")

    files = _write_outputs(
        output_dir=output_dir,
        candidate_index=candidate_index,
        rows=rows,
        selected=selected,
        skipped=skipped,
        args=args,
    )
    summary = json.loads(Path(files["plan"]).read_text(encoding="utf-8"))
    _print_summary(summary, files)
    return {"summary": summary, "files": files}


def _select_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row_index, row in enumerate(rows, start=1):
        candidate_id = _candidate_id(row)
        if candidate_id is None:
            skipped.append(
                {
                    "candidate_id": None,
                    "formula": _formula(row),
                    "row_index": row_index,
                    "reason": "missing_candidate_id",
                }
            )
            continue
        if candidate_id in seen_ids:
            raise SystemExit(f"duplicate candidate_id in candidate index: {candidate_id}")
        seen_ids.add(candidate_id)
        reason = _skip_reason(row, args)
        if reason:
            skipped.append(_skip_row(row, reason, row_index=row_index))
            continue
        copied = dict(row)
        copied["_f4_candidate_index_row"] = row_index
        selected.append(copied)
    selected = sorted(selected, key=_sort_key(args.sort))
    return selected, skipped


def _write_outputs(
    *,
    output_dir: Path,
    candidate_index: Path,
    rows: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shards_dir = output_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    manifest_example_path = output_dir / "reference_pool_manifest.example.json"
    manifest_path = output_dir / "reference_pool_manifest.json"
    tasks_path = output_dir / "f4_audit_tasks.jsonl"
    skipped_path = output_dir / "skipped_candidates.jsonl"
    plan_path = output_dir / "f4_audit_plan.json"
    report_path = output_dir / "report.md"
    expected_results_path = output_dir / "f4_results.jsonl"

    tasks = [
        _task_row(
            row=row,
            task_index=index,
            shard_id=index % args.shard_count,
            candidate_index=candidate_index,
            reference_pool_id=args.reference_pool_id,
            manifest_path=manifest_path,
            expected_results_path=expected_results_path,
        )
        for index, row in enumerate(selected)
    ]
    shard_paths = _write_shards(shards_dir, tasks, args.shard_count)
    formula_counts = Counter(task["formula"] for task in tasks if task.get("formula"))
    skipped_counts = Counter(str(row["reason"]) for row in skipped)
    plan = {
        "workflow": "f4_novelty_audit_plan",
        "task_schema_version": TASK_SCHEMA_VERSION,
        "result_schema_version": F4_AUDIT_SCHEMA_VERSION,
        "reference_pool_manifest_schema_version": REFERENCE_POOL_MANIFEST_SCHEMA_VERSION,
        "local_only": True,
        "runs_structure_matcher": False,
        "runs_pymatgen": False,
        "runs_database_query": False,
        "calls_external_apis": False,
        "downloads": False,
        "candidate_index": str(candidate_index),
        "candidate_index_sha256": _sha256(candidate_index),
        "candidate_input_count": len(rows),
        "selected_task_count": len(tasks),
        "skipped_candidate_count": len(skipped),
        "skipped_reason_counts": dict(sorted(skipped_counts.items())),
        "formula_count": len(formula_counts),
        "formula_counts": dict(sorted(formula_counts.items())),
        "filters": {
            "require_dpo_eligible": bool(args.require_dpo_eligible),
            "require_f1_pass": bool(args.require_f1_pass),
            "require_f2_pass": bool(args.require_f2_pass),
            "limit": args.limit,
            "sort": args.sort,
        },
        "reference_pool_id": args.reference_pool_id,
        "reference_pool_manifest": str(manifest_path),
        "reference_pool_manifest_example": str(manifest_example_path),
        "expected_results_jsonl": str(expected_results_path),
        "output_dir": str(output_dir),
        "tasks_jsonl": str(tasks_path),
        "shard_count": args.shard_count,
        "shard_paths": shard_paths,
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
        "worker_contract": _worker_contract(),
    }

    write_jsonl(tasks_path, tasks)
    write_jsonl(skipped_path, skipped)
    write_json(manifest_example_path, _reference_manifest_example(args.reference_pool_id, output_dir))
    write_json(plan_path, plan)
    report_path.write_text(_render_report(plan), encoding="utf-8")
    return {
        "plan": str(plan_path),
        "tasks": str(tasks_path),
        "skipped_candidates": str(skipped_path),
        "reference_pool_manifest": str(manifest_path),
        "reference_pool_manifest_example": str(manifest_example_path),
        "report": str(report_path),
        "expected_results": str(expected_results_path),
        "shards_dir": str(shards_dir),
        **{f"shard_{index:04d}": path for index, path in enumerate(shard_paths)},
    }


def _task_row(
    *,
    row: dict[str, Any],
    task_index: int,
    shard_id: int,
    candidate_index: Path,
    reference_pool_id: str,
    manifest_path: Path,
    expected_results_path: Path,
) -> dict[str, Any]:
    candidate_id = _candidate_id(row)
    formula = _formula(row)
    task_id = f"{reference_pool_id}_{task_index:06d}"
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task_id,
        "task_index": task_index,
        "shard_id": shard_id,
        "candidate_id": candidate_id,
        "formula": formula,
        "condition": row.get("condition") if isinstance(row.get("condition"), dict) else {},
        "source_candidate_index": str(candidate_index),
        "candidate_index_row": row.get("_f4_candidate_index_row"),
        "reference_pool_id": reference_pool_id,
        "reference_pool_manifest": str(manifest_path),
        "expected_result_schema_version": F4_AUDIT_SCHEMA_VERSION,
        "expected_results_jsonl": str(expected_results_path),
        "match_type": "structure_matcher",
        "status": "planned_not_executed",
        "run_structure_matcher": False,
        "candidate_snapshot": _candidate_snapshot(row),
    }


def _candidate_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for key in (
        "candidate_id",
        "composition",
        "condition",
        "source_format",
        "parse_status",
        "raw_sequence_status",
        "raw_sequence_fields",
        "species",
        "frac_coords",
        "lattice_matrix",
        "structure_format",
        "structure_ref",
    ):
        if key in row:
            snapshot[key] = row[key]
    failure_vector = row.get("failure_vector")
    if isinstance(failure_vector, dict):
        snapshot["failure_vector_metadata"] = failure_vector.get("metadata", {})
    return snapshot


def _write_shards(shards_dir: Path, tasks: list[dict[str, Any]], shard_count: int) -> list[str]:
    shards: list[list[dict[str, Any]]] = [[] for _ in range(shard_count)]
    for task in tasks:
        shards[int(task["shard_id"])].append(task)
    paths: list[str] = []
    for shard_id, rows in enumerate(shards):
        path = shards_dir / f"f4_audit_tasks_shard_{shard_id:04d}.jsonl"
        write_jsonl(path, rows)
        paths.append(str(path))
    return paths


def _reference_manifest_example(reference_pool_id: str, output_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": REFERENCE_POOL_MANIFEST_SCHEMA_VERSION,
        "reference_pool_id": reference_pool_id,
        "example_manifest": True,
        "created_time_utc": None,
        "total_reference_count": 0,
        "reference_sources": [
            {
                "name": "materials_project_snapshot",
                "path": str(output_dir / "references" / "materials_project_snapshot.structures.jsonl"),
                "format": "structure_jsonl",
                "reference_count": 0,
                "sha256": None,
            },
            {
                "name": "training_set_snapshot",
                "path": str(output_dir / "references" / "training_set_snapshot.structures.jsonl"),
                "format": "structure_jsonl",
                "reference_count": 0,
                "sha256": None,
            },
        ],
        "notes": "Replace this example with a real local reference_pool_manifest.json before running F4 audit workers.",
    }


def _worker_contract() -> dict[str, Any]:
    return {
        "task_input": {
            "required_fields": [
                "task_id",
                "candidate_id",
                "reference_pool_id",
                "reference_pool_manifest",
                "source_candidate_index",
            ],
            "candidate_structure_source": "candidate_snapshot or source_candidate_index row",
        },
        "result_output": {
            "jsonl_path": "f4_results.jsonl",
            "required_fields": [
                "candidate_id",
                "f4_novelty_leakage",
                "reference_source",
                "match_type",
                "confidence",
            ],
            "score_semantics": "f4_novelty_leakage is in [0, 1]; lower is better.",
        },
    }


def _render_report(plan: dict[str, Any]) -> str:
    lines = [
        "# F4 Novelty Leakage Audit Plan",
        "",
        "## Boundary",
        "- This is a planning artifact only.",
        "- It does not run StructureMatcher, pymatgen, database queries, downloads, or external APIs.",
        "- External workers should read task shards and write `f4_results.jsonl` with schema `f4-audit-v1`.",
        "",
        "## Summary",
        f"- candidate_input_count: {plan['candidate_input_count']}",
        f"- selected_task_count: {plan['selected_task_count']}",
        f"- skipped_candidate_count: {plan['skipped_candidate_count']}",
        f"- skipped_reason_counts: {plan['skipped_reason_counts']}",
        f"- formula_count: {plan['formula_count']}",
        f"- shard_count: {plan['shard_count']}",
        f"- tasks_jsonl: `{plan['tasks_jsonl']}`",
        f"- reference_pool_manifest: `{plan['reference_pool_manifest']}`",
        f"- reference_pool_manifest_example: `{plan['reference_pool_manifest_example']}`",
        f"- expected_results_jsonl: `{plan['expected_results_jsonl']}`",
        "",
        "## Formula Counts",
    ]
    for formula, count in sorted(plan["formula_counts"].items()):
        lines.append(f"- {formula}: {count}")
    lines.append("")
    return "\n".join(lines)


def _print_summary(summary: dict[str, Any], files: dict[str, str]) -> None:
    print("F4 novelty/leakage audit plan complete")
    print(f"  candidate_input_count: {summary['candidate_input_count']}")
    print(f"  selected_task_count: {summary['selected_task_count']}")
    print(f"  skipped_candidate_count: {summary['skipped_candidate_count']}")
    print(f"  shard_count: {summary['shard_count']}")
    print(f"  tasks: {files['tasks']}")
    print(f"  plan: {files['plan']}")
    print(f"  report: {files['report']}")


def _skip_reason(row: dict[str, Any], args: argparse.Namespace) -> str | None:
    if args.require_dpo_eligible and row.get("dpo_eligible") is not True:
        return "not_dpo_eligible"
    if args.require_f1_pass and row.get("f1_label") != "pass":
        return "f1_not_pass"
    if args.require_f2_pass and row.get("f2_label") != "pass":
        return "f2_not_pass"
    return None


def _skip_row(row: dict[str, Any], reason: str, row_index: int | None = None) -> dict[str, Any]:
    return {
        "candidate_id": _candidate_id(row),
        "formula": _formula(row),
        "row_index": row_index or row.get("_f4_candidate_index_row"),
        "reason": reason,
    }


def _sort_key(sort_mode: str):
    if sort_mode == "ranking":
        return lambda row: (
            -1.0 if _optional_float(row.get("ranking_score")) is None else -float(row["ranking_score"]),
            1.0 if _optional_float(row.get("fiir_score")) is None else float(row["fiir_score"]),
            _candidate_id(row) or "",
        )
    return lambda row: (_candidate_id(row) or "",)


def _candidate_id(row: dict[str, Any]) -> str | None:
    value = row.get("candidate_id", row.get("sample_id", row.get("id")))
    return None if value in (None, "") else str(value)


def _formula(row: dict[str, Any]) -> str | None:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    value = row.get("formula", row.get("composition", condition.get("formula")))
    return None if value in (None, "") else str(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "null", "None", "none"):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
