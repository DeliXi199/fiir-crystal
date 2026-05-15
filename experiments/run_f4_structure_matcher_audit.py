#!/usr/bin/env python
"""External F4 StructureMatcher audit worker.

This is intentionally outside the stdlib-only ``fiir_crystal`` core package.
It reads local F4 audit task/reference artifacts, runs pymatgen
StructureMatcher over exact-formula reference buckets, and writes
``f4-audit-v1`` JSONL rows for the core import step.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
import socket
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.io import read_json, read_jsonl, write_json, write_jsonl
from scripts.run_mlip_offline_validation import _pymatgen_structure_from_candidate


DEFAULT_PLAN_JSON = Path("outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run an external local StructureMatcher audit over planned F4 tasks. "
            "This worker is not part of the fiir_crystal core package."
        )
    )
    parser.add_argument("--plan-json", default=str(DEFAULT_PLAN_JSON))
    parser.add_argument("--tasks-jsonl")
    parser.add_argument("--reference-manifest")
    parser.add_argument("--output-jsonl")
    parser.add_argument("--summary-json")
    parser.add_argument("--report")
    parser.add_argument("--audit-run-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--ltol", type=float, default=0.2)
    parser.add_argument("--stol", type=float, default=0.3)
    parser.add_argument("--angle-tol", type=float, default=5.0)
    parser.add_argument("--confidence-match", type=float, default=0.95)
    parser.add_argument("--confidence-no-match", type=float, default=0.75)
    parser.add_argument("--confidence-no-bucket", type=float, default=0.0)
    parser.add_argument("--positive-control-count", type=int, default=1)
    parser.add_argument("--control-results-jsonl")
    parser.add_argument("--skip-no-bucket-control", action="store_true")
    parser.add_argument("--allow-control-failures", action="store_true")
    parser.add_argument(
        "--allow-candidate-parse-failures",
        action="store_true",
        help="Emit low-confidence parse_failed rows instead of failing the run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    _validate_args(args)
    started = datetime.now(timezone.utc)
    start_time = time.monotonic()

    plan_path = Path(args.plan_json)
    plan = read_json(plan_path)
    tasks_path = Path(args.tasks_jsonl or plan.get("tasks_jsonl") or plan_path.with_name("f4_audit_tasks.jsonl"))
    manifest_path = Path(args.reference_manifest or plan.get("reference_pool_manifest") or plan_path.with_name("reference_pool_manifest.json"))
    output_jsonl = Path(args.output_jsonl or plan.get("expected_results_jsonl") or plan_path.with_name("f4_results.jsonl"))
    summary_json = Path(args.summary_json or output_jsonl.with_name("f4_structure_matcher_audit_summary.json"))
    report_path = Path(args.report or output_jsonl.with_name("f4_structure_matcher_audit_report.md"))
    control_results_jsonl = Path(args.control_results_jsonl or output_jsonl.with_name("f4_control_results.jsonl"))

    if output_jsonl.exists() and not args.overwrite:
        raise SystemExit(f"output already exists, pass --overwrite to replace it: {output_jsonl}")

    tasks = read_jsonl(tasks_path)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    if not tasks:
        raise SystemExit("no F4 tasks selected")

    manifest = read_json(manifest_path)
    reference_pool_id = str(plan.get("reference_pool_id") or manifest.get("reference_pool_id") or "")
    audit_run_id = args.audit_run_id or _default_audit_run_id(reference_pool_id)
    wanted_formulas = sorted({str(task.get("formula") or "") for task in tasks if task.get("formula")})

    reference_buckets, reference_summary = _load_reference_buckets(manifest, wanted_formulas)
    matcher = _structure_matcher(args)

    control_tasks, control_setup_issues = _build_control_tasks(
        reference_buckets,
        positive_control_count=args.positive_control_count,
        include_no_bucket_control=not args.skip_no_bucket_control,
        reference_pool_id=reference_pool_id,
    )
    control_results = [
        _audit_task(
            task,
            matcher=matcher,
            reference_buckets=reference_buckets,
            reference_pool_id=reference_pool_id,
            audit_run_id=audit_run_id,
            args=args,
        )
        for task in control_tasks
    ]
    control_gate = _control_gate(control_tasks, control_results, control_setup_issues)
    if control_tasks or control_setup_issues:
        write_jsonl(control_results_jsonl, control_results)

    results: list[dict[str, Any]] = []
    candidate_parse_failures: list[dict[str, str]] = []
    for task in tasks:
        try:
            results.append(
                _audit_task(
                    task,
                    matcher=matcher,
                    reference_buckets=reference_buckets,
                    reference_pool_id=reference_pool_id,
                    audit_run_id=audit_run_id,
                    args=args,
                )
            )
        except Exception as exc:
            if not args.allow_candidate_parse_failures:
                raise
            candidate_id = str(task.get("candidate_id") or "")
            candidate_parse_failures.append({"candidate_id": candidate_id, "error": f"{exc.__class__.__name__}: {exc}"})
            results.append(
                _result_row(
                    task=task,
                    reference_pool_id=reference_pool_id,
                    audit_run_id=audit_run_id,
                    f4_novelty_leakage=0.5,
                    nearest_reference_id=None,
                    reference_source="candidate_parse_failed",
                    match_type="candidate_parse_failed",
                    confidence=0.0,
                    metadata={"error_reason": f"{exc.__class__.__name__}: {exc}"},
                )
            )

    results = sorted(results, key=lambda row: str(row["candidate_id"]))
    summary = _summary(
        args=args,
        plan_path=plan_path,
        tasks_path=tasks_path,
        manifest_path=manifest_path,
        output_jsonl=output_jsonl,
        summary_json=summary_json,
        report_path=report_path,
        started=started,
        elapsed_seconds=time.monotonic() - start_time,
        tasks=tasks,
        results=results,
        reference_summary=reference_summary,
        candidate_parse_failures=candidate_parse_failures,
        control_results_jsonl=control_results_jsonl,
        control_tasks=control_tasks,
        control_results=control_results,
        control_gate=control_gate,
        reference_pool_id=reference_pool_id,
        audit_run_id=audit_run_id,
    )
    write_jsonl(output_jsonl, results)
    write_json(summary_json, summary)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(summary), encoding="utf-8")
    _print_summary(summary)
    if control_gate["status"] == "failed" and not args.allow_control_failures:
        raise SystemExit("F4 control gate failed")
    return {"summary": summary, "rows": results}


def _validate_args(args: argparse.Namespace) -> None:
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.ltol <= 0:
        raise SystemExit("--ltol must be positive")
    if args.stol <= 0:
        raise SystemExit("--stol must be positive")
    if args.angle_tol <= 0:
        raise SystemExit("--angle-tol must be positive")
    if args.positive_control_count < 0:
        raise SystemExit("--positive-control-count must be non-negative")
    for field in ("confidence_match", "confidence_no_match", "confidence_no_bucket"):
        value = float(getattr(args, field))
        if value < 0.0 or value > 1.0:
            raise SystemExit(f"--{field.replace('_', '-')} must be in [0, 1]")


def _load_reference_buckets(
    manifest: dict[str, Any],
    wanted_formulas: list[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    wanted = set(wanted_formulas)
    buckets: dict[str, list[dict[str, Any]]] = {formula: [] for formula in wanted_formulas}
    source_rows_seen: dict[str, int] = {}
    source_rows_selected: dict[str, int] = {}
    reference_parse_failures: list[dict[str, str]] = []

    for source in manifest.get("reference_sources", []):
        source_name = str(source.get("name") or source.get("source_database") or "unknown_reference_source")
        path = Path(str(source.get("path") or ""))
        if not path.exists():
            raise SystemExit(f"reference source missing: {path}")
        seen = 0
        selected = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                seen += 1
                row = json.loads(stripped)
                formula = None if row.get("formula") in (None, "") else str(row["formula"])
                if formula not in wanted:
                    continue
                selected += 1
                try:
                    structure = _structure_from_reference(row)
                except Exception as exc:
                    reference_parse_failures.append(
                        {
                            "reference_id": str(row.get("reference_id") or ""),
                            "source": source_name,
                            "line": str(line_no),
                            "error": f"{exc.__class__.__name__}: {exc}",
                        }
                    )
                    continue
                item = {
                    "reference_id": str(row.get("reference_id") or f"{source_name}:{line_no}"),
                    "reference_source": source_name,
                    "formula": formula,
                    "structure": structure,
                }
                buckets[formula].append(item)
        source_rows_seen[source_name] = seen
        source_rows_selected[source_name] = selected

    formula_bucket_counts = {formula: len(buckets.get(formula, [])) for formula in wanted_formulas}
    return buckets, {
        "wanted_formula_count": len(wanted_formulas),
        "source_rows_seen": source_rows_seen,
        "source_rows_selected": source_rows_selected,
        "selected_reference_count": sum(formula_bucket_counts.values()),
        "formula_bucket_counts": formula_bucket_counts,
        "formulas_without_reference_bucket": [formula for formula, count in formula_bucket_counts.items() if count == 0],
        "reference_parse_failure_count": len(reference_parse_failures),
        "reference_parse_failures": reference_parse_failures[:20],
    }


def _structure_from_reference(row: dict[str, Any]) -> Any:
    from pymatgen.core import Structure  # type: ignore[import-not-found]

    structure_ref = row.get("structure_ref")
    if structure_ref in (None, ""):
        raise ValueError("missing structure_ref")
    structure_format = str(row.get("structure_format") or "")
    text = str(structure_ref)
    if structure_format == "cif_path":
        return Structure.from_file(text)
    if structure_format == "cif_inline" or text.lstrip().startswith("data_"):
        return Structure.from_str(text, fmt="cif")
    if structure_format == "structure_inline" or text.lstrip().startswith("{"):
        data = _parse_structure_dict(text)
        return Structure.from_dict(data)
    path = Path(text)
    if path.exists():
        return Structure.from_file(str(path))
    return Structure.from_str(text, fmt="cif")


def _parse_structure_dict(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = ast.literal_eval(text)
    if not isinstance(data, dict):
        raise ValueError("structure inline payload is not an object")
    return data


def _structure_matcher(args: argparse.Namespace) -> Any:
    from pymatgen.analysis.structure_matcher import StructureMatcher  # type: ignore[import-not-found]

    return StructureMatcher(
        ltol=args.ltol,
        stol=args.stol,
        angle_tol=args.angle_tol,
        primitive_cell=True,
        scale=True,
        attempt_supercell=False,
        allow_subset=False,
    )


def _build_control_tasks(
    reference_buckets: dict[str, list[dict[str, Any]]],
    *,
    positive_control_count: int,
    include_no_bucket_control: bool,
    reference_pool_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    tasks: list[dict[str, Any]] = []
    issues: list[str] = []
    references = _control_reference_candidates(reference_buckets)
    if positive_control_count and len(references) < positive_control_count:
        issues.append(f"positive_control_shortfall:expected_{positive_control_count}:actual_{len(references)}")
    for index, reference in enumerate(references[:positive_control_count], start=1):
        reference_id = str(reference["reference_id"])
        tasks.append(
            {
                "schema_version": "f4-control-task-v1",
                "task_id": f"{reference_pool_id}_positive_control_{index:04d}",
                "task_index": index - 1,
                "candidate_id": f"__f4_positive_control__{_safe_id(reference_id)}",
                "formula": reference["formula"],
                "reference_pool_id": reference_pool_id,
                "match_type": "structure_matcher",
                "status": "planned_control",
                "control": {
                    "type": "positive_known_reference",
                    "expected_outcome": "high_leakage_match",
                    "expected_reference_id": reference_id,
                    "expected_reference_source": reference["reference_source"],
                },
                "_candidate_structure": reference["structure"],
            }
        )

    if include_no_bucket_control:
        reference = references[0] if references else None
        if reference is None:
            issues.append("no_bucket_control_not_created:no_reference_available")
        else:
            tasks.append(
                {
                    "schema_version": "f4-control-task-v1",
                    "task_id": f"{reference_pool_id}_no_bucket_control_0001",
                    "task_index": len(tasks),
                    "candidate_id": "__f4_no_exact_formula_bucket_control__",
                    "formula": "__F4_NO_EXACT_FORMULA_BUCKET_CONTROL__",
                    "reference_pool_id": reference_pool_id,
                    "match_type": "structure_matcher",
                    "status": "planned_control",
                    "control": {
                        "type": "no_exact_formula_bucket",
                        "expected_outcome": "coverage_gap_no_bucket",
                        "source_reference_id": reference["reference_id"],
                    },
                    "_candidate_structure": reference["structure"],
                }
            )
    return tasks, issues


def _control_reference_candidates(reference_buckets: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for formula in sorted(reference_buckets):
        references.extend(reference_buckets[formula])
    return references


def _audit_task(
    task: dict[str, Any],
    *,
    matcher: Any,
    reference_buckets: dict[str, list[dict[str, Any]]],
    reference_pool_id: str,
    audit_run_id: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    formula = str(task.get("formula") or "")
    refs = reference_buckets.get(formula, [])
    metadata = {
        "reference_scope": "alex20_only",
        "bucket_policy": "exact_formula",
        "formula": formula,
        "formula_bucket_size": len(refs),
        "score_policy": "binary_structurematcher_exact_formula_v1",
        "ltol": args.ltol,
        "stol": args.stol,
        "angle_tol": args.angle_tol,
    }
    control = task.get("control") if isinstance(task.get("control"), dict) else None
    if control:
        metadata["control_type"] = control.get("type")
        metadata["control_expected_outcome"] = control.get("expected_outcome")
    if not refs:
        metadata["interpretation"] = "coverage_gap_not_low_risk_evidence"
        return _result_row(
            task=task,
            reference_pool_id=reference_pool_id,
            audit_run_id=audit_run_id,
            f4_novelty_leakage=0.0,
            nearest_reference_id=None,
            reference_source="alex20_no_exact_formula_bucket",
            match_type="no_exact_formula_reference",
            confidence=args.confidence_no_bucket,
            metadata=metadata,
        )

    candidate = _candidate_structure_from_task(task)
    checked = 0
    for reference in refs:
        checked += 1
        if matcher.fit(candidate, reference["structure"]):
            metadata["checked_reference_count"] = checked
            return _result_row(
                task=task,
                reference_pool_id=reference_pool_id,
                audit_run_id=audit_run_id,
                f4_novelty_leakage=1.0,
                nearest_reference_id=reference["reference_id"],
                reference_source=reference["reference_source"],
                match_type="structure_matcher_formula_bucket_match",
                confidence=args.confidence_match,
                metadata=metadata,
            )

    metadata["checked_reference_count"] = checked
    return _result_row(
        task=task,
        reference_pool_id=reference_pool_id,
        audit_run_id=audit_run_id,
        f4_novelty_leakage=0.0,
        nearest_reference_id=None,
        reference_source="alex20_exact_formula_bucket",
        match_type="structure_matcher_formula_bucket_no_match",
        confidence=args.confidence_no_match,
        metadata=metadata,
    )


def _candidate_structure_from_task(task: dict[str, Any]) -> Any:
    if "_candidate_structure" in task:
        return task["_candidate_structure"]
    snapshot = task.get("candidate_snapshot") if isinstance(task.get("candidate_snapshot"), dict) else {}
    for row in (snapshot, task):
        if isinstance(row, dict) and row.get("structure_ref") not in (None, ""):
            return _structure_from_reference(row)
    return _pymatgen_structure_from_candidate(snapshot or task)


def _result_row(
    *,
    task: dict[str, Any],
    reference_pool_id: str,
    audit_run_id: str,
    f4_novelty_leakage: float,
    nearest_reference_id: str | None,
    reference_source: str,
    match_type: str,
    confidence: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "f4-audit-v1",
        "reference_pool_id": reference_pool_id,
        "audit_run_id": audit_run_id,
        "candidate_id": str(task.get("candidate_id") or ""),
        "f4_novelty_leakage": float(f4_novelty_leakage),
        "nearest_reference_id": nearest_reference_id,
        "reference_source": reference_source,
        "match_type": match_type,
        "fingerprint_distance": None,
        "confidence": float(confidence),
        "metadata": metadata,
    }


def _control_gate(
    control_tasks: list[dict[str, Any]],
    control_results: list[dict[str, Any]],
    setup_issues: list[str],
) -> dict[str, Any]:
    result_by_id = {str(row["candidate_id"]): row for row in control_results}
    positive_tasks = [_control_row(task) for task in control_tasks if _control_type(task) == "positive_known_reference"]
    no_bucket_tasks = [_control_row(task) for task in control_tasks if _control_type(task) == "no_exact_formula_bucket"]
    failures: list[dict[str, Any]] = []
    positive_pass_count = 0
    no_bucket_pass_count = 0

    for task in positive_tasks:
        result = result_by_id.get(str(task["candidate_id"]))
        passed = bool(
            result
            and float(result["f4_novelty_leakage"]) >= 0.8
            and result["match_type"] == "structure_matcher_formula_bucket_match"
            and result.get("nearest_reference_id")
        )
        if passed:
            positive_pass_count += 1
            continue
        failures.append(
            {
                "candidate_id": task["candidate_id"],
                "control_type": "positive_known_reference",
                "expected": "high leakage StructureMatcher match",
                "actual": _control_actual(result),
            }
        )

    for task in no_bucket_tasks:
        result = result_by_id.get(str(task["candidate_id"]))
        passed = bool(result and result["match_type"] == "no_exact_formula_reference" and result["confidence"] == 0.0)
        if passed:
            no_bucket_pass_count += 1
            continue
        failures.append(
            {
                "candidate_id": task["candidate_id"],
                "control_type": "no_exact_formula_bucket",
                "expected": "no_exact_formula_reference with zero confidence",
                "actual": _control_actual(result),
            }
        )

    for issue in setup_issues:
        failures.append({"control_type": "setup", "expected": "control task creation", "actual": issue})

    status = "passed" if not failures else "failed"
    return {
        "status": status,
        "positive_control_count": len(positive_tasks),
        "positive_control_pass_count": positive_pass_count,
        "no_bucket_control_count": len(no_bucket_tasks),
        "no_bucket_control_pass_count": no_bucket_pass_count,
        "failure_count": len(failures),
        "failures": failures,
        "control_set_sha256": _control_set_sha256(control_results, setup_issues),
    }


def _control_type(task: dict[str, Any]) -> str | None:
    control = task.get("control") if isinstance(task.get("control"), dict) else {}
    value = control.get("type")
    return None if value in (None, "") else str(value)


def _control_row(task: dict[str, Any]) -> dict[str, Any]:
    control = task.get("control") if isinstance(task.get("control"), dict) else {}
    return {
        "candidate_id": str(task.get("candidate_id") or ""),
        "control_type": str(control.get("type") or ""),
        "expected_outcome": str(control.get("expected_outcome") or ""),
    }


def _control_actual(result: dict[str, Any] | None) -> dict[str, Any] | str:
    if result is None:
        return "missing_control_result"
    return {
        "f4_novelty_leakage": result.get("f4_novelty_leakage"),
        "nearest_reference_id": result.get("nearest_reference_id"),
        "match_type": result.get("match_type"),
        "confidence": result.get("confidence"),
    }


def _control_set_sha256(control_results: list[dict[str, Any]], setup_issues: list[str]) -> str:
    payload = {
        "control_results": [
            {
                "candidate_id": row.get("candidate_id"),
                "f4_novelty_leakage": row.get("f4_novelty_leakage"),
                "nearest_reference_id": row.get("nearest_reference_id"),
                "reference_source": row.get("reference_source"),
                "match_type": row.get("match_type"),
                "confidence": row.get("confidence"),
                "metadata": row.get("metadata", {}),
            }
            for row in control_results
        ],
        "setup_issues": setup_issues,
    }
    text = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summary(
    *,
    args: argparse.Namespace,
    plan_path: Path,
    tasks_path: Path,
    manifest_path: Path,
    output_jsonl: Path,
    summary_json: Path,
    report_path: Path,
    started: datetime,
    elapsed_seconds: float,
    tasks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    reference_summary: dict[str, Any],
    candidate_parse_failures: list[dict[str, str]],
    control_results_jsonl: Path,
    control_tasks: list[dict[str, Any]],
    control_results: list[dict[str, Any]],
    control_gate: dict[str, Any],
    reference_pool_id: str,
    audit_run_id: str,
) -> dict[str, Any]:
    match_type_counts = Counter(str(row["match_type"]) for row in results)
    reference_source_counts = Counter(str(row["reference_source"]) for row in results)
    high_leakage = [row for row in results if float(row["f4_novelty_leakage"]) >= 0.8]
    exact_formula_matches = [row["candidate_id"] for row in results if row["match_type"] == "structure_matcher_formula_bucket_match"]
    no_match_with_bucket = [
        row["candidate_id"] for row in results if row["match_type"] == "structure_matcher_formula_bucket_no_match"
    ]
    no_bucket = [row["candidate_id"] for row in results if row["match_type"] == "no_exact_formula_reference"]
    candidate_parse_failed = [row["candidate_id"] for row in results if row["match_type"] == "candidate_parse_failed"]
    outcome_counts = {
        "exact_formula_structure_match": len(exact_formula_matches),
        "exact_formula_no_structure_match": len(no_match_with_bucket),
        "no_exact_formula_bucket": len(no_bucket),
        "candidate_parse_failed": len(candidate_parse_failed),
    }
    return {
        "workflow": "external_f4_structure_matcher_audit",
        "local_only": True,
        "runs_structure_matcher": True,
        "runs_pymatgen": True,
        "runs_database_query": False,
        "calls_external_apis": False,
        "downloads": False,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "reference_scope": "alex20_only",
        "score_policy": "binary_structurematcher_exact_formula_v1",
        "plan_json": str(plan_path),
        "tasks_jsonl": str(tasks_path),
        "reference_manifest": str(manifest_path),
        "output_jsonl": str(output_jsonl),
        "summary_json": str(summary_json),
        "report": str(report_path),
        "control_results_jsonl": str(control_results_jsonl),
        "reference_pool_id": reference_pool_id,
        "audit_run_id": audit_run_id,
        "task_count": len(tasks),
        "result_count": len(results),
        "control_task_count": len(control_tasks),
        "control_result_count": len(control_results),
        "control_gate": control_gate,
        "high_leakage_count": len(high_leakage),
        "outcome_counts": outcome_counts,
        "exact_formula_structure_match_count": len(exact_formula_matches),
        "exact_formula_no_structure_match_count": len(no_match_with_bucket),
        "no_exact_formula_bucket_count": len(no_bucket),
        "candidate_parse_failed_count": len(candidate_parse_failed),
        "exact_formula_structure_match_candidate_ids": exact_formula_matches[:50],
        "exact_formula_no_structure_match_candidate_ids": no_match_with_bucket[:50],
        "no_exact_formula_bucket_candidate_ids": no_bucket[:50],
        "candidate_parse_failed_candidate_ids": candidate_parse_failed[:50],
        "match_type_counts": dict(sorted(match_type_counts.items())),
        "reference_source_counts": dict(sorted(reference_source_counts.items())),
        "reference_summary": reference_summary,
        "candidate_parse_failure_count": len(candidate_parse_failures),
        "candidate_parse_failures": candidate_parse_failures[:20],
        "matcher": {
            "ltol": args.ltol,
            "stol": args.stol,
            "angle_tol": args.angle_tol,
            "primitive_cell": True,
            "scale": True,
            "attempt_supercell": False,
            "allow_subset": False,
        },
        "input_sha256": {
            "plan_json": _sha256(plan_path),
            "tasks_jsonl": _sha256(tasks_path),
            "reference_manifest": _sha256(manifest_path),
        },
        "start_time_utc": started.isoformat(),
        "end_time_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
        "notes": [
            "This is an external worker, not fiir_crystal core functionality.",
            "Only exact-formula Alex-20 reference buckets are compared in this first audit pass.",
            "Scores are binary: StructureMatcher match = 1.0 leakage risk, otherwise 0.0.",
            "Materials Project, GNoME, and ICSD are not included in this reference pool.",
            "no_exact_formula_reference is a coverage gap, not evidence of global low leakage risk.",
        ],
    }


def _render_report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# External F4 StructureMatcher Audit",
            "",
            "## Boundary",
            "- Runs outside the `fiir_crystal` core package.",
            "- Reads local task and reference-pool JSONL artifacts only.",
            "- Runs local pymatgen StructureMatcher.",
            "- Does not query databases, call external APIs, download data, train models, run generation, or run DFT.",
            "",
            "## Summary",
            f"- reference_scope: {summary['reference_scope']}",
            f"- task_count: {summary['task_count']}",
            f"- result_count: {summary['result_count']}",
            f"- high_leakage_count: {summary['high_leakage_count']}",
            f"- outcome_counts: {summary['outcome_counts']}",
            f"- no_exact_formula_bucket_count: {summary['no_exact_formula_bucket_count']}",
            f"- match_type_counts: {summary['match_type_counts']}",
            f"- reference_source_counts: {summary['reference_source_counts']}",
            f"- selected_reference_count: {summary['reference_summary']['selected_reference_count']}",
            f"- reference_parse_failure_count: {summary['reference_summary']['reference_parse_failure_count']}",
            f"- elapsed_seconds: {summary['elapsed_seconds']}",
            f"- output_jsonl: `{summary['output_jsonl']}`",
            "",
            "## Control Gate",
            f"- status: {summary['control_gate']['status']}",
            f"- positive_control_count: {summary['control_gate']['positive_control_count']}",
            f"- positive_control_pass_count: {summary['control_gate']['positive_control_pass_count']}",
            f"- no_bucket_control_count: {summary['control_gate']['no_bucket_control_count']}",
            f"- no_bucket_control_pass_count: {summary['control_gate']['no_bucket_control_pass_count']}",
            f"- failure_count: {summary['control_gate']['failure_count']}",
            f"- control_set_sha256: {summary['control_gate']['control_set_sha256']}",
            f"- control_results_jsonl: `{summary['control_results_jsonl']}`",
            "",
            "## Caveats",
            "- This is Alex-20-only leakage evidence, not an all-known-materials novelty claim.",
            "- This first pass uses exact-formula buckets and binary StructureMatcher scores.",
            "- `no_exact_formula_reference` rows are coverage gaps, not low-risk novelty evidence.",
            "",
        ]
    )


def _print_summary(summary: dict[str, Any]) -> None:
    print("External F4 StructureMatcher audit complete")
    print(f"  task_count: {summary['task_count']}")
    print(f"  result_count: {summary['result_count']}")
    print(f"  control_gate: {summary['control_gate']['status']}")
    print(f"  high_leakage_count: {summary['high_leakage_count']}")
    print(f"  no_exact_formula_bucket_count: {summary['no_exact_formula_bucket_count']}")
    print(f"  output_jsonl: {summary['output_jsonl']}")
    print(f"  summary: {summary['summary_json']}")
    print(f"  report: {summary['report']}")


def _default_audit_run_id(reference_pool_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = reference_pool_id or "reference_pool"
    return f"{prefix}_structure_matcher_{stamp}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)[:80] or "reference"


if __name__ == "__main__":
    main()
