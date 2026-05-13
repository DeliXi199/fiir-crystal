#!/usr/bin/env python
"""Readiness checks for external F4 novelty/leakage audit plans."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import JsonlFormatError, read_json, read_jsonl, write_json
from fiir_crystal.validation import F4NoveltyAuditError, read_f4_novelty_audit_jsonl


DEFAULT_PLAN_JSON = Path("outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether a local F4 novelty/leakage audit plan is ready for external workers."
    )
    parser.add_argument("--plan-json", default=str(DEFAULT_PLAN_JSON))
    parser.add_argument("--tasks-jsonl")
    parser.add_argument("--reference-manifest")
    parser.add_argument("--output-json")
    parser.add_argument("--require-results", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    plan_path = Path(args.plan_json)
    plan, plan_issues = _load_plan(plan_path)
    tasks_path = Path(args.tasks_jsonl or plan.get("tasks_jsonl", plan_path.with_name("f4_audit_tasks.jsonl")))
    manifest_path = Path(args.reference_manifest or _default_manifest_path(plan, plan_path))
    results_path = Path(plan.get("expected_results_jsonl", plan_path.with_name("f4_results.jsonl")))

    task_check = _check_tasks(tasks_path, plan)
    shard_check = _check_shards(plan)
    manifest_check = _check_manifest(manifest_path, plan)
    results_check = _check_results(results_path, plan, require_results=args.require_results)
    issues = [
        *plan_issues,
        *task_check["issues"],
        *shard_check["issues"],
        *manifest_check["issues"],
        *results_check["issues"],
    ]
    ready = not issues
    summary = {
        "workflow": "f4_novelty_audit_readiness_check",
        "ready": ready,
        "plan_json": str(plan_path),
        "tasks_jsonl": str(tasks_path),
        "reference_manifest": str(manifest_path),
        "expected_results_jsonl": str(results_path),
        "plan": {
            "exists": plan_path.exists(),
            "selected_task_count": plan.get("selected_task_count"),
            "shard_count": plan.get("shard_count"),
            "reference_pool_id": plan.get("reference_pool_id"),
        },
        "tasks": task_check,
        "shards": shard_check,
        "reference_pool": manifest_check,
        "results": results_check,
        "issue_count": len(issues),
        "issues": issues,
        "local_only": True,
        "runs_structure_matcher": False,
        "runs_pymatgen": False,
        "runs_database_query": False,
        "calls_external_apis": False,
        "downloads": False,
    }
    if args.output_json:
        write_json(args.output_json, summary)
    print(f"F4 novelty/leakage audit ready: {ready}")
    print(f"  tasks: exists={task_check['exists']} row_count={task_check['row_count']} ready={task_check['ready']}")
    print(
        "  reference_pool: "
        f"exists={manifest_check['exists']} total_reference_count={manifest_check['total_reference_count']} "
        f"ready={manifest_check['ready']}"
    )
    print(
        f"  results: exists={results_check['exists']} row_count={results_check['row_count']} "
        f"ready={results_check['ready']}"
    )
    if issues:
        print(f"  issues: {issues}")
    return summary


def _load_plan(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, [f"missing_plan:{path}"]
    try:
        data = read_json(path)
    except json.JSONDecodeError as exc:
        return {}, [f"invalid_plan_json:{path}:{exc.msg}"]
    if not isinstance(data, dict):
        return {}, [f"plan_must_be_object:{path}"]
    return data, []


def _check_tasks(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return _check_result(False, 0, ["missing_tasks_jsonl"])
    try:
        rows = read_jsonl(path)
    except JsonlFormatError as exc:
        return _check_result(True, None, [f"invalid_tasks_jsonl:{exc}"])
    issues: list[str] = []
    expected = plan.get("selected_task_count")
    if expected is not None and len(rows) != int(expected):
        issues.append(f"task_count_mismatch:expected_{expected}:actual_{len(rows)}")
    task_ids = [str(row.get("task_id")) for row in rows if row.get("task_id") not in (None, "")]
    candidate_ids = [str(row.get("candidate_id")) for row in rows if row.get("candidate_id") not in (None, "")]
    if len(task_ids) != len(rows):
        issues.append("task_missing_task_id")
    if len(candidate_ids) != len(rows):
        issues.append("task_missing_candidate_id")
    issues.extend(f"duplicate_task_id:{value}" for value in sorted(_duplicates(task_ids)))
    issues.extend(f"duplicate_candidate_id:{value}" for value in sorted(_duplicates(candidate_ids)))
    schema_versions = sorted({str(row.get("schema_version")) for row in rows})
    if rows and schema_versions != ["f4-audit-task-v1"]:
        issues.append(f"unexpected_task_schema_versions:{schema_versions}")
    shard_counts = Counter(str(row.get("shard_id")) for row in rows)
    return {
        "exists": True,
        "row_count": len(rows),
        "ready": not issues,
        "issue": None if not issues else "task_validation_failed",
        "issues": issues,
        "candidate_count": len(candidate_ids),
        "shard_counts": dict(sorted(shard_counts.items())),
    }


def _check_shards(plan: dict[str, Any]) -> dict[str, Any]:
    paths = [Path(path) for path in plan.get("shard_paths", [])]
    if not paths:
        return {"exists": False, "row_count": 0, "ready": False, "issues": ["missing_shard_paths"], "shards": []}
    issues: list[str] = []
    shards: list[dict[str, Any]] = []
    total = 0
    for path in paths:
        if not path.exists():
            issues.append(f"missing_shard:{path}")
            shards.append({"path": str(path), "exists": False, "row_count": 0})
            continue
        try:
            rows = read_jsonl(path)
        except JsonlFormatError as exc:
            issues.append(f"invalid_shard_jsonl:{exc}")
            shards.append({"path": str(path), "exists": True, "row_count": None})
            continue
        total += len(rows)
        shards.append({"path": str(path), "exists": True, "row_count": len(rows)})
    expected = plan.get("selected_task_count")
    if expected is not None and total != int(expected):
        issues.append(f"shard_task_count_mismatch:expected_{expected}:actual_{total}")
    return {
        "exists": all(row["exists"] for row in shards),
        "row_count": total,
        "ready": not issues,
        "issues": issues,
        "shards": shards,
    }


def _check_manifest(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "ready": False,
            "total_reference_count": 0,
            "source_count": 0,
            "issues": [f"missing_reference_manifest:{path}"],
            "sources": [],
        }
    try:
        data = read_json(path)
    except json.JSONDecodeError as exc:
        return {
            "exists": True,
            "ready": False,
            "total_reference_count": 0,
            "source_count": 0,
            "issues": [f"invalid_reference_manifest_json:{exc.msg}"],
            "sources": [],
        }
    issues: list[str] = []
    if data.get("schema_version") != "f4-reference-pool-manifest-v1":
        issues.append("reference_manifest_schema_mismatch")
    if data.get("example_manifest"):
        issues.append("reference_manifest_is_example")
    if plan.get("reference_pool_id") and data.get("reference_pool_id") != plan.get("reference_pool_id"):
        issues.append("reference_pool_id_mismatch")
    sources = data.get("reference_sources", [])
    if not isinstance(sources, list) or not sources:
        sources = []
        issues.append("reference_sources_empty")
    source_rows = []
    total_reference_count = _optional_int(data.get("total_reference_count")) or 0
    if total_reference_count < 1:
        issues.append("reference_pool_empty")
    for source in sources:
        source_path = Path(str(source.get("path", "")))
        source_count = _optional_int(source.get("reference_count")) or 0
        source_issue = None
        if source_count < 1:
            source_issue = "reference_source_empty"
        elif not source_path.exists():
            source_issue = "reference_source_missing"
        if source_issue:
            issues.append(f"{source_issue}:{source.get('name')}")
        source_rows.append(
            {
                "name": source.get("name"),
                "path": str(source_path),
                "exists": source_path.exists(),
                "reference_count": source_count,
                "issue": source_issue,
            }
        )
    return {
        "exists": True,
        "ready": not issues,
        "total_reference_count": total_reference_count,
        "source_count": len(source_rows),
        "issues": issues,
        "sources": source_rows,
    }


def _check_results(path: Path, plan: dict[str, Any], *, require_results: bool) -> dict[str, Any]:
    if not path.exists():
        issues = ["missing_results_jsonl"] if require_results else []
        return {
            "exists": False,
            "row_count": 0,
            "ready": not issues,
            "required": require_results,
            "issues": issues,
        }
    try:
        records = read_f4_novelty_audit_jsonl(path)
    except (JsonlFormatError, F4NoveltyAuditError, ValueError) as exc:
        return {
            "exists": True,
            "row_count": None,
            "ready": False,
            "required": require_results,
            "issues": [f"invalid_results_jsonl:{exc}"],
        }
    issues: list[str] = []
    candidate_ids = [record.candidate_id for record in records]
    issues.extend(f"duplicate_result_candidate_id:{value}" for value in sorted(_duplicates(candidate_ids)))
    expected = plan.get("selected_task_count")
    if require_results and expected is not None and len(records) != int(expected):
        issues.append(f"result_count_mismatch:expected_{expected}:actual_{len(records)}")
    return {
        "exists": True,
        "row_count": len(records),
        "ready": not issues,
        "required": require_results,
        "issues": issues,
    }


def _default_manifest_path(plan: dict[str, Any], plan_path: Path) -> str:
    real_manifest = plan_path.with_name("reference_pool_manifest.json")
    if real_manifest.exists():
        return str(real_manifest)
    return str(plan.get("reference_pool_manifest", plan_path.with_name("reference_pool_manifest.example.json")))


def _check_result(exists: bool, row_count: int | None, issues: list[str]) -> dict[str, Any]:
    return {
        "exists": exists,
        "row_count": row_count,
        "ready": not issues,
        "issue": None if not issues else issues[0],
        "issues": issues,
    }


def _duplicates(values: list[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
