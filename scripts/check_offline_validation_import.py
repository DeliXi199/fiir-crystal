"""CLI for dry-checking offline validation import joins."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import read_jsonl
from fiir_crystal.validation import (
    OfflineValidationImportConfig,
    import_offline_validation_to_audit_rows,
    read_offline_validation_jsonl,
    write_offline_validation_import_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check local offline validation JSONL against audit candidates without modifying audit files."
    )
    parser.add_argument("--audit-candidates-jsonl", required=True)
    parser.add_argument("--validation-jsonl", required=True)
    parser.add_argument("--output-dir", default="outputs/validation_import_check")
    parser.add_argument("--formula")
    parser.add_argument("--spacegroup", type=int)
    parser.add_argument("--allow-condition-mismatch", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    audit_rows = read_jsonl(args.audit_candidates_jsonl)
    validation_records = read_offline_validation_jsonl(args.validation_jsonl)
    _, summary = import_offline_validation_to_audit_rows(
        audit_rows,
        validation_records,
        OfflineValidationImportConfig(
            formula=args.formula,
            spacegroup=args.spacegroup,
            require_same_generation_condition=not args.allow_condition_mismatch,
        ),
    )
    files = write_offline_validation_import_outputs(args.output_dir, summary)

    print("Offline validation import check complete")
    print(f"  audit_candidates: {summary.audit_candidate_count}")
    print(f"  validation_records: {summary.validation_record_count}")
    print(f"  matched: {summary.matched_count}")
    print(f"  f3_available: {summary.f3_available_count}")
    print(f"  validation_errors: {summary.validation_error_count}")
    print(f"  skipped: {summary.skipped_count}")
    print(f"  skip_reasons: {summary.skip_reasons}")
    print(f"  json: {files['json']}")
    print(f"  report: {files['markdown']}")
    return {"summary": summary.to_dict(), "files": files}


if __name__ == "__main__":
    main()
