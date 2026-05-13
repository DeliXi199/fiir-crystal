#!/usr/bin/env python
"""Import external F4 novelty/leakage audit rows into candidate rows."""

from __future__ import annotations

import argparse
import hashlib
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import read_jsonl
from fiir_crystal.validation import (
    F4_AUDIT_SCHEMA_VERSION,
    F4NoveltyImportConfig,
    import_f4_novelty_audit_to_candidates,
    read_f4_novelty_audit_jsonl,
    write_f4_novelty_import_outputs,
)


DEFAULT_CANDIDATE_INDEX = Path("outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl")
DEFAULT_F4_RESULTS_JSONL = Path("outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import externally computed F4 novelty/leakage audit results into candidate JSONL rows. "
            "This script only reads local files and does not run StructureMatcher."
        )
    )
    parser.add_argument("--candidate-index", default=str(DEFAULT_CANDIDATE_INDEX))
    parser.add_argument("--f4-results-jsonl", default=str(DEFAULT_F4_RESULTS_JSONL))
    parser.add_argument("--output-dir", default=_default_output_dir())
    parser.add_argument("--allow-duplicate-results", action="store_true")
    parser.add_argument("--high-leakage-threshold", type=float, default=0.8)
    parser.add_argument("--fail-on-missing", action="store_true")
    parser.add_argument("--fail-on-orphans", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.high_leakage_threshold < 0.0 or args.high_leakage_threshold > 1.0:
        raise SystemExit("--high-leakage-threshold must be in [0, 1]")

    candidate_index = Path(args.candidate_index)
    f4_results_jsonl = Path(args.f4_results_jsonl)
    candidate_rows = read_jsonl(candidate_index)
    f4_records = read_f4_novelty_audit_jsonl(f4_results_jsonl)
    updated_rows, import_summary = import_f4_novelty_audit_to_candidates(
        candidate_rows,
        f4_records,
        F4NoveltyImportConfig(
            allow_duplicate_results=args.allow_duplicate_results,
            high_leakage_threshold=args.high_leakage_threshold,
        ),
    )

    summary = {
        "workflow": "f4_novelty_audit_import",
        "schema_version": F4_AUDIT_SCHEMA_VERSION,
        "local_only": True,
        "runs_structure_matcher": False,
        "runs_pymatgen": False,
        "runs_database_query": False,
        "calls_external_apis": False,
        "downloads": False,
        "candidate_index": str(candidate_index),
        "f4_results_jsonl": str(f4_results_jsonl),
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
        "input_provenance": {
            "candidate_index": {
                "path": str(candidate_index),
                "record_count": len(candidate_rows),
                "sha256": _sha256(candidate_index),
            },
            "f4_results_jsonl": {
                "path": str(f4_results_jsonl),
                "record_count": len(f4_records),
                "sha256": _sha256(f4_results_jsonl),
            },
        },
        **import_summary.to_dict(),
    }
    files = write_f4_novelty_import_outputs(args.output_dir, updated_rows, summary)
    summary["output_files"] = files

    print("F4 novelty/leakage audit import complete")
    print(f"  candidates: {summary['candidate_count']}")
    print(f"  f4_records: {summary['f4_record_count']}")
    print(f"  matched: {summary['matched_count']}")
    print(f"  missing: {summary['missing_count']}")
    print(f"  orphans: {summary['orphan_count']}")
    print(f"  high_leakage: {summary['high_leakage_count']}")
    print(f"  candidates_with_f4: {files['candidates_with_f4']}")
    print(f"  summary: {files['summary']}")
    print(f"  report: {files['report']}")

    if args.fail_on_missing and summary["missing_count"]:
        raise SystemExit("some candidates are missing F4 audit rows")
    if args.fail_on_orphans and summary["orphan_count"]:
        raise SystemExit("some F4 audit rows do not match candidate ids")
    return {"summary": summary, "files": files}


def _default_output_dir() -> str:
    return f"outputs/f4_novelty_import_1024_{datetime.now().strftime('%Y%m%d')}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
