#!/usr/bin/env python
"""Import offline validation evidence into audit rows and rebuild DPO pairs."""

from __future__ import annotations

import argparse
import glob
import platform
import socket
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.dpo import (
    PreferenceBuildConfig,
    STABILITY_AWARE_OFFLINE_VALIDATION,
    build_dpo_preferences,
    write_preference_outputs,
)
from fiir_crystal.io import read_jsonl, write_json, write_jsonl
from fiir_crystal.validation import (
    OfflineValidationImportConfig,
    import_offline_validation_to_audit_rows,
    read_offline_validation_jsonl,
    write_offline_validation_import_outputs,
)


DEFAULT_OUTPUT_DIR = Path("outputs/dpo_preferences/offline_validation_rebuild")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import local validation JSONL into CrystalFormer audit rows and rebuild DPO preference pairs."
    )
    parser.add_argument("--validation-jsonl", required=True)
    parser.add_argument("--audit-candidates-jsonl", action="append", default=[])
    parser.add_argument("--audit-glob", action="append", default=[])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--formula")
    parser.add_argument("--spacegroup", type=int)
    parser.add_argument("--allow-condition-mismatch", action="store_true")
    parser.add_argument("--min-preference-margin", type=float, default=1e-6)
    parser.add_argument("--max-pairs", type=int)
    parser.add_argument("--allow-missing-raw-sequence", action="store_true")
    parser.add_argument("--fail-on-zero-pairs", action="store_true")
    parser.add_argument("--fail-on-zero-stability-pairs", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    audit_paths = _paths(args.audit_candidates_jsonl, args.audit_glob)
    if not audit_paths:
        raise SystemExit("no audit candidate JSONL files were provided or matched")
    if args.max_pairs is not None and args.max_pairs < 1:
        raise SystemExit("--max-pairs must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    updated_audit_jsonl = output_dir / "audit_candidates_with_validation.jsonl"
    summary_json = output_dir / "closed_loop_summary.json"
    report = output_dir / "report.md"

    audit_rows = _read_audit_rows(audit_paths)
    validation_records = read_offline_validation_jsonl(args.validation_jsonl)
    updated_rows, import_summary = import_offline_validation_to_audit_rows(
        audit_rows,
        validation_records,
        OfflineValidationImportConfig(
            formula=args.formula,
            spacegroup=args.spacegroup,
            require_same_generation_condition=not args.allow_condition_mismatch,
        ),
    )
    write_jsonl(updated_audit_jsonl, updated_rows)
    import_files = write_offline_validation_import_outputs(output_dir / "validation_import", import_summary)

    pairs, preference_summary = build_dpo_preferences(
        updated_rows,
        PreferenceBuildConfig(
            formula=args.formula,
            spacegroup=args.spacegroup,
            min_preference_margin=args.min_preference_margin,
            max_pairs=args.max_pairs,
            require_raw_sequence=not args.allow_missing_raw_sequence,
        ),
    )
    preference_files = write_preference_outputs(output_dir / "dpo_preferences", pairs, preference_summary)
    preference_type_counts = Counter(pair.preference_type for pair in pairs)
    stability_pair_count = preference_type_counts.get(STABILITY_AWARE_OFFLINE_VALIDATION, 0)
    summary = {
        "workflow": "offline_validation_import_and_dpo_rebuild",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "audit_candidate_input_paths": [str(path) for path in audit_paths],
        "validation_jsonl": str(args.validation_jsonl),
        "updated_audit_jsonl": str(updated_audit_jsonl),
        "validation_import_summary": import_summary.to_dict(),
        "preference_summary": preference_summary.to_dict(),
        "stability_aware_pair_count": stability_pair_count,
        "preference_type_breakdown": dict(sorted(preference_type_counts.items())),
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
    }
    write_json(summary_json, summary)
    report.write_text(_render_report(summary), encoding="utf-8")

    print("Offline validation import and DPO rebuild complete")
    print(f"  audit_candidates: {import_summary.audit_candidate_count}")
    print(f"  validation_records: {import_summary.validation_record_count}")
    print(f"  matched: {import_summary.matched_count}")
    print(f"  f3_available: {import_summary.f3_available_count}")
    print(f"  preference_pairs: {preference_summary.pair_count}")
    print(f"  stability_aware_pair_count: {stability_pair_count}")
    print(f"  updated_audit_jsonl: {updated_audit_jsonl}")
    print(f"  preference_pairs_jsonl: {preference_files['preference_pairs']}")

    if args.fail_on_zero_pairs and preference_summary.pair_count == 0:
        raise SystemExit("no DPO preference pairs were built")
    if args.fail_on_zero_stability_pairs and stability_pair_count == 0:
        raise SystemExit("no stability-aware DPO preference pairs were built")
    return {
        "summary": summary,
        "files": {
            "updated_audit": str(updated_audit_jsonl),
            "closed_loop_summary": str(summary_json),
            "report": str(report),
            "validation_import_summary": import_files["json"],
            "validation_import_report": import_files["markdown"],
            **{f"dpo_{key}": value for key, value in preference_files.items()},
        },
    }


def _paths(explicit: Iterable[str], patterns: Iterable[str]) -> list[Path]:
    paths = [Path(path) for path in explicit]
    for pattern in patterns:
        paths.extend(Path(path) for path in glob.glob(pattern))
    return sorted({path.resolve() for path in paths if path.exists() and path.is_file()})


def _read_audit_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for row in read_jsonl(path):
            copied = dict(row)
            copied.setdefault("audit_source_jsonl", str(path))
            rows.append(copied)
    return rows


def _render_report(summary: dict[str, Any]) -> str:
    validation = summary["validation_import_summary"]
    preferences = summary["preference_summary"]
    return "\n".join(
        [
            "# Offline Validation Import And DPO Rebuild",
            "",
            "## Boundary",
            "- Reads local audit and validation JSONL files only.",
            "- Does not run generation, MLIP, DFT, training, downloads, or external APIs.",
            "",
            "## Validation Import",
            f"- audit_candidate_count: {validation['audit_candidate_count']}",
            f"- validation_record_count: {validation['validation_record_count']}",
            f"- matched_count: {validation['matched_count']}",
            f"- f3_available_count: {validation['f3_available_count']}",
            f"- skip_reasons: {validation['skip_reasons']}",
            "",
            "## DPO Preferences",
            f"- pair_count: {preferences['pair_count']}",
            f"- stability_aware_pair_count: {summary['stability_aware_pair_count']}",
            f"- preference_type_breakdown: {summary['preference_type_breakdown']}",
            f"- updated_audit_jsonl: `{summary['updated_audit_jsonl']}`",
            "",
        ]
    )


if __name__ == "__main__":
    main()
