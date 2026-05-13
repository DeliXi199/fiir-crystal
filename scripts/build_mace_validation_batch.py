#!/usr/bin/env python
"""Build deterministic local MACE validation batches from existing candidates.

The script is read-only with respect to CrystalFormer run directories. It reads
existing ``candidates.jsonl`` and sibling ``audit_candidates.jsonl`` files,
selects a bounded per-formula subset, and writes a standalone batch directory
for ``scripts/run_mace_offline_validation.py``.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import platform
import socket
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import read_jsonl, write_json, write_jsonl


@dataclass(slots=True)
class CandidateBundle:
    candidate: dict[str, Any]
    audit: dict[str, Any] | None
    source_candidates_jsonl: Path
    source_audit_jsonl: Path | None
    formula: str
    candidate_id: str
    ranking_score: float | None
    fiir_score: float | None
    f1_label: str | None
    f2_label: str | None
    dpo_eligible: bool | None
    selection_warnings: list[str] = field(default_factory=list)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select existing CrystalFormer candidates for local MACE validation."
    )
    parser.add_argument("--candidate-glob", action="append", default=[])
    parser.add_argument("--candidate-jsonl", action="append", default=[])
    parser.add_argument("--output-dir", default="outputs/mlip_validation_mace_overnight_batch")
    parser.add_argument("--per-formula-limit", type=int, default=50)
    parser.add_argument("--max-total", type=int)
    parser.add_argument("--sort", choices=("ranking", "candidate_id"), default="ranking")
    parser.add_argument("--require-audit", action="store_true")
    parser.add_argument("--require-dpo-eligible", action="store_true")
    parser.add_argument("--require-f1-pass", action="store_true")
    parser.add_argument("--require-f2-pass", action="store_true")
    parser.add_argument("--exclude-validation-jsonl", action="append", default=[])
    parser.add_argument(
        "--candidate-id-prefix",
        default="",
        help="Optional prefix applied to selected output candidate_id values; original ids are preserved in metadata.",
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.per_formula_limit < 1:
        raise SystemExit("--per-formula-limit must be positive")
    if args.max_total is not None and args.max_total < 1:
        raise SystemExit("--max-total must be positive")

    output_dir = Path(args.output_dir)
    candidate_paths = _candidate_paths(args)
    if not candidate_paths:
        raise SystemExit("no candidate JSONL files matched")

    excluded_ids = _load_excluded_candidate_ids(args.exclude_validation_jsonl)
    bundles, load_issues = _load_bundles(candidate_paths)
    selected, skipped = _select_bundles(
        bundles,
        excluded_ids=excluded_ids,
        per_formula_limit=args.per_formula_limit,
        max_total=args.max_total,
        sort_mode=args.sort,
        require_audit=args.require_audit,
        require_dpo_eligible=args.require_dpo_eligible,
        require_f1_pass=args.require_f1_pass,
        require_f2_pass=args.require_f2_pass,
    )
    files = _write_outputs(output_dir, selected, skipped, load_issues, args, candidate_paths)
    summary = json.loads(Path(files["summary"]).read_text(encoding="utf-8"))
    _print_summary(summary, files)
    if args.strict and (summary["load_issue_count"] or summary["selected_candidate_count"] == 0):
        raise SystemExit("strict batch build found blocking issues")
    return {"summary": summary, "files": files}


def _candidate_paths(args: argparse.Namespace) -> list[Path]:
    paths = [Path(path) for path in args.candidate_jsonl]
    for pattern in args.candidate_glob:
        paths.extend(Path(path) for path in glob.glob(pattern))
    unique = sorted({path.resolve() for path in paths if path.exists() and path.is_file()})
    return [Path(path) for path in unique]


def _load_excluded_candidate_ids(paths: Iterable[str]) -> set[str]:
    excluded: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        for row in read_jsonl(path):
            candidate_id = _candidate_id(row)
            if candidate_id:
                excluded.add(candidate_id)
    return excluded


def _load_bundles(paths: list[Path]) -> tuple[list[CandidateBundle], list[dict[str, Any]]]:
    bundles: list[CandidateBundle] = []
    issues: list[dict[str, Any]] = []
    for path in paths:
        audit_path = path.with_name("audit_candidates.jsonl")
        audit_by_id: dict[str, dict[str, Any]] = {}
        if audit_path.exists():
            try:
                audit_by_id = {
                    str(row["candidate_id"]): row
                    for row in read_jsonl(audit_path)
                    if row.get("candidate_id") not in (None, "")
                }
            except Exception as exc:
                issues.append(
                    {
                        "path": str(audit_path),
                        "reason": "audit_read_error",
                        "message": str(exc),
                    }
                )
        try:
            rows = read_jsonl(path)
        except Exception as exc:
            issues.append({"path": str(path), "reason": "candidate_read_error", "message": str(exc)})
            continue
        for row_index, row in enumerate(rows, start=1):
            candidate_id = _candidate_id(row)
            formula = _formula(row)
            if not candidate_id or not formula:
                issues.append(
                    {
                        "path": str(path),
                        "row_index": row_index,
                        "reason": "missing_candidate_id_or_formula",
                    }
                )
                continue
            audit = audit_by_id.get(candidate_id)
            warnings = []
            if audit_path.exists() and audit is None:
                warnings.append("missing_matching_audit_row")
            bundles.append(
                CandidateBundle(
                    candidate=dict(row),
                    audit=dict(audit) if audit is not None else None,
                    source_candidates_jsonl=path,
                    source_audit_jsonl=audit_path if audit_path.exists() else None,
                    formula=formula,
                    candidate_id=candidate_id,
                    ranking_score=_optional_float((audit or {}).get("ranking_score")),
                    fiir_score=_optional_float((audit or {}).get("fiir_score")),
                    f1_label=_optional_str((audit or {}).get("f1_label")),
                    f2_label=_optional_str((audit or {}).get("f2_label")),
                    dpo_eligible=_optional_bool((audit or {}).get("dpo_eligible")),
                    selection_warnings=warnings,
                )
            )
    return bundles, issues


def _select_bundles(
    bundles: list[CandidateBundle],
    *,
    excluded_ids: set[str],
    per_formula_limit: int,
    max_total: int | None,
    sort_mode: str,
    require_audit: bool,
    require_dpo_eligible: bool,
    require_f1_pass: bool,
    require_f2_pass: bool,
) -> tuple[list[CandidateBundle], list[dict[str, Any]]]:
    selected: list[CandidateBundle] = []
    skipped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    by_formula: dict[str, list[CandidateBundle]] = defaultdict(list)
    for bundle in bundles:
        reason = _skip_reason(
            bundle,
            excluded_ids=excluded_ids,
            seen_ids=seen_ids,
            require_audit=require_audit,
            require_dpo_eligible=require_dpo_eligible,
            require_f1_pass=require_f1_pass,
            require_f2_pass=require_f2_pass,
        )
        if reason:
            skipped.append(_skip_row(bundle, reason))
            continue
        seen_ids.add(bundle.candidate_id)
        by_formula[bundle.formula].append(bundle)

    for formula in sorted(by_formula):
        rows = sorted(by_formula[formula], key=_sort_key(sort_mode))
        selected.extend(rows[:per_formula_limit])
        skipped.extend(_skip_row(bundle, "per_formula_limit_overflow") for bundle in rows[per_formula_limit:])
    selected = sorted(selected, key=lambda item: (item.formula, _sort_key(sort_mode)(item)))
    if max_total is not None:
        overflow = selected[max_total:]
        selected = selected[:max_total]
        skipped.extend(_skip_row(bundle, "max_total_overflow") for bundle in overflow)
    return selected, sorted(skipped, key=lambda row: (str(row["formula"]), str(row["candidate_id"]), str(row["reason"])))


def _skip_reason(
    bundle: CandidateBundle,
    *,
    excluded_ids: set[str],
    seen_ids: set[str],
    require_audit: bool,
    require_dpo_eligible: bool,
    require_f1_pass: bool,
    require_f2_pass: bool,
) -> str | None:
    if bundle.candidate_id in excluded_ids:
        return "already_validated"
    if bundle.candidate_id in seen_ids:
        return "duplicate_candidate_id"
    if require_audit and bundle.audit is None:
        return "missing_audit_row"
    if require_dpo_eligible and bundle.dpo_eligible is not True:
        return "not_dpo_eligible"
    if require_f1_pass and bundle.f1_label != "pass":
        return "f1_not_pass"
    if require_f2_pass and bundle.f2_label != "pass":
        return "f2_not_pass"
    return None


def _skip_row(bundle: CandidateBundle, reason: str) -> dict[str, Any]:
    return {
        "candidate_id": bundle.candidate_id,
        "formula": bundle.formula,
        "reason": reason,
        "source_candidates_jsonl": str(bundle.source_candidates_jsonl),
    }


def _sort_key(sort_mode: str):
    if sort_mode == "candidate_id":
        return lambda item: (item.candidate_id,)
    return lambda item: (
        -1.0 if item.ranking_score is None else -item.ranking_score,
        1.0 if item.fiir_score is None else item.fiir_score,
        item.candidate_id,
    )


def _write_outputs(
    output_dir: Path,
    selected: list[CandidateBundle],
    skipped: list[dict[str, Any]],
    load_issues: list[dict[str, Any]],
    args: argparse.Namespace,
    candidate_paths: list[Path],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_candidates_path = output_dir / "selected_candidates.jsonl"
    candidate_index_path = output_dir / "candidate_index.jsonl"
    selection_table_path = output_dir / "selection_table.jsonl"
    skipped_path = output_dir / "skipped_candidates.jsonl"
    issues_path = output_dir / "load_issues.jsonl"
    summary_path = output_dir / "batch_summary.json"
    report_path = output_dir / "report.md"

    selected_candidates = [
        _candidate_with_batch_metadata(bundle, output_dir, args.candidate_id_prefix) for bundle in selected
    ]
    candidate_index = [_candidate_index_row(bundle, args.candidate_id_prefix) for bundle in selected]
    selection_table = [_selection_row(bundle, args.candidate_id_prefix) for bundle in selected]
    formula_counts = Counter(bundle.formula for bundle in selected)
    skipped_counts = Counter(str(row["reason"]) for row in skipped)
    summary = {
        "workflow": "mace_validation_batch_build",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "candidate_input_count": len(candidate_paths),
        "candidate_input_paths": [str(path) for path in candidate_paths],
        "selected_candidate_count": len(selected),
        "selected_formula_count": len(formula_counts),
        "per_formula_limit": args.per_formula_limit,
        "max_total": args.max_total,
        "sort": args.sort,
        "candidate_id_prefix": args.candidate_id_prefix,
        "filters": {
            "require_audit": bool(args.require_audit),
            "require_dpo_eligible": bool(args.require_dpo_eligible),
            "require_f1_pass": bool(args.require_f1_pass),
            "require_f2_pass": bool(args.require_f2_pass),
        },
        "formula_counts": dict(sorted(formula_counts.items())),
        "skipped_candidate_count": len(skipped),
        "skipped_reason_counts": dict(sorted(skipped_counts.items())),
        "load_issue_count": len(load_issues),
        "output_dir": str(output_dir),
        "selected_candidates_jsonl": str(selected_candidates_path),
        "candidate_index_jsonl": str(candidate_index_path),
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
        "input_hashes": {
            str(path): _sha256(path)
            for path in candidate_paths
        },
    }
    write_jsonl(selected_candidates_path, selected_candidates)
    write_jsonl(candidate_index_path, candidate_index)
    write_jsonl(selection_table_path, selection_table)
    write_jsonl(skipped_path, skipped)
    write_jsonl(issues_path, load_issues)
    write_json(summary_path, summary)
    report_path.write_text(_render_report(summary), encoding="utf-8")
    return {
        "selected_candidates": str(selected_candidates_path),
        "candidate_index": str(candidate_index_path),
        "selection_table": str(selection_table_path),
        "skipped_candidates": str(skipped_path),
        "load_issues": str(issues_path),
        "summary": str(summary_path),
        "report": str(report_path),
    }


def _batch_candidate_id(bundle: CandidateBundle, candidate_id_prefix: str) -> str:
    return f"{candidate_id_prefix}{bundle.candidate_id}" if candidate_id_prefix else bundle.candidate_id


def _candidate_with_batch_metadata(
    bundle: CandidateBundle,
    output_dir: Path,
    candidate_id_prefix: str,
) -> dict[str, Any]:
    row = dict(bundle.candidate)
    row["candidate_id"] = _batch_candidate_id(bundle, candidate_id_prefix)
    metadata = dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {}
    metadata["mace_batch_output_dir"] = str(output_dir)
    metadata["mace_batch_source_candidates_jsonl"] = str(bundle.source_candidates_jsonl)
    metadata["mace_batch_original_candidate_id"] = bundle.candidate_id
    metadata["mace_batch_candidate_id_prefix"] = candidate_id_prefix
    if bundle.source_audit_jsonl is not None:
        metadata["mace_batch_source_audit_jsonl"] = str(bundle.source_audit_jsonl)
    metadata["mace_batch_ranking_score"] = bundle.ranking_score
    metadata["mace_batch_fiir_score"] = bundle.fiir_score
    row["metadata"] = metadata
    return row


def _candidate_index_row(bundle: CandidateBundle, candidate_id_prefix: str) -> dict[str, Any]:
    if bundle.audit is not None:
        row = dict(bundle.audit)
    else:
        row = {
            "candidate_id": bundle.candidate_id,
            "composition": bundle.formula,
            "condition": bundle.candidate.get("condition", {"formula": bundle.formula}),
        }
    row["candidate_id"] = _batch_candidate_id(bundle, candidate_id_prefix)
    row["mace_batch_original_candidate_id"] = bundle.candidate_id
    row["mace_batch_candidate_id_prefix"] = candidate_id_prefix
    row.setdefault("composition", bundle.formula)
    row.setdefault("condition", bundle.candidate.get("condition", {"formula": bundle.formula}))
    row["mace_batch_source_candidates_jsonl"] = str(bundle.source_candidates_jsonl)
    if bundle.source_audit_jsonl is not None:
        row["mace_batch_source_audit_jsonl"] = str(bundle.source_audit_jsonl)
    return row


def _selection_row(bundle: CandidateBundle, candidate_id_prefix: str) -> dict[str, Any]:
    return {
        "candidate_id": _batch_candidate_id(bundle, candidate_id_prefix),
        "original_candidate_id": bundle.candidate_id,
        "formula": bundle.formula,
        "ranking_score": bundle.ranking_score,
        "fiir_score": bundle.fiir_score,
        "f1_label": bundle.f1_label,
        "f2_label": bundle.f2_label,
        "dpo_eligible": bundle.dpo_eligible,
        "source_candidates_jsonl": str(bundle.source_candidates_jsonl),
        "source_audit_jsonl": None if bundle.source_audit_jsonl is None else str(bundle.source_audit_jsonl),
        "selection_warnings": list(bundle.selection_warnings),
    }


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# MACE Validation Batch Report",
        "",
        "## Boundary",
        "- Reads existing CrystalFormer candidate/audit files only.",
        "- Does not run generation, MLIP, DFT, training, downloads, or external APIs.",
        "- Writes a standalone candidate batch for later local MACE execution.",
        "",
        "## Summary",
        f"- selected_candidate_count: {summary['selected_candidate_count']}",
        f"- selected_formula_count: {summary['selected_formula_count']}",
        f"- per_formula_limit: {summary['per_formula_limit']}",
        f"- skipped_candidate_count: {summary['skipped_candidate_count']}",
        f"- skipped_reason_counts: {summary['skipped_reason_counts']}",
        f"- load_issue_count: {summary['load_issue_count']}",
        f"- selected_candidates_jsonl: `{summary['selected_candidates_jsonl']}`",
        f"- candidate_index_jsonl: `{summary['candidate_index_jsonl']}`",
        "",
        "## Formula Counts",
    ]
    for formula, count in sorted(summary["formula_counts"].items()):
        lines.append(f"- {formula}: {count}")
    lines.append("")
    return "\n".join(lines)


def _print_summary(summary: dict[str, Any], files: dict[str, str]) -> None:
    print("MACE validation batch build complete")
    print(f"  selected_candidate_count: {summary['selected_candidate_count']}")
    print(f"  selected_formula_count: {summary['selected_formula_count']}")
    print(f"  skipped_candidate_count: {summary['skipped_candidate_count']}")
    print(f"  load_issue_count: {summary['load_issue_count']}")
    print(f"  selected_candidates: {files['selected_candidates']}")
    print(f"  candidate_index: {files['candidate_index']}")
    print(f"  summary: {files['summary']}")
    print(f"  report: {files['report']}")


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


def _optional_bool(value: Any) -> bool | None:
    if value in (None, "", "null", "None", "none"):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def _optional_str(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
