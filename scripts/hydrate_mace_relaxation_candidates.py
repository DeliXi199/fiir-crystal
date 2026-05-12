#!/usr/bin/env python
"""Hydrate compact MACE relaxation candidate rows into full candidate JSONL.

The MACE analysis step writes a compact ``relaxation_candidates.jsonl`` that is
useful for triage, but not enough for ``run_mace_offline_validation.py --relax``.
This script joins those compact rows back to existing full candidate records by
``candidate_id`` and writes a standalone JSONL batch for relaxation.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
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

from fiir_crystal.io import read_jsonl, write_json, write_jsonl


DEFAULT_OUTPUT_DIR = Path("outputs/mlip_validation_mace_relaxation_input")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Join compact relaxation candidate ids back to full CrystalFormer candidate records."
    )
    parser.add_argument("--relaxation-candidates-jsonl", required=True)
    parser.add_argument("--candidate-jsonl", action="append", default=[])
    parser.add_argument("--candidate-glob", action="append", default=[])
    parser.add_argument("--candidate-index-jsonl", action="append", default=[])
    parser.add_argument("--candidate-index-glob", action="append", default=[])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-jsonl")
    parser.add_argument("--output-index-jsonl")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    output_dir = Path(args.output_dir)
    output_jsonl = Path(args.output_jsonl) if args.output_jsonl else output_dir / "relaxation_candidates_full.jsonl"
    output_index_jsonl = (
        Path(args.output_index_jsonl) if args.output_index_jsonl else output_dir / "candidate_index.jsonl"
    )
    summary_json = output_dir / "hydrate_summary.json"
    missing_jsonl = output_dir / "missing_candidates.jsonl"
    duplicate_jsonl = output_dir / "duplicate_candidates.jsonl"
    report = output_dir / "report.md"

    relaxation_path = Path(args.relaxation_candidates_jsonl)
    candidate_paths = _paths(args.candidate_jsonl, args.candidate_glob)
    candidate_index_paths = _paths(args.candidate_index_jsonl, args.candidate_index_glob)
    if not candidate_paths:
        raise SystemExit("no full candidate JSONL files were provided or matched")

    compact_rows = read_jsonl(relaxation_path)
    candidates_by_id, duplicate_candidates = _load_unique_by_id(candidate_paths)
    index_by_id, duplicate_index_rows = _load_unique_by_id(candidate_index_paths) if candidate_index_paths else ({}, [])

    hydrated: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    seen_relaxation_ids: set[str] = set()
    duplicate_relaxation_rows: list[dict[str, Any]] = []

    for row_index, compact in enumerate(compact_rows, start=1):
        candidate_id = _candidate_id(compact)
        if candidate_id is None:
            missing.append(
                {
                    "row_index": row_index,
                    "reason": "missing_candidate_id",
                    "relaxation_candidate": compact,
                }
            )
            continue
        if candidate_id in seen_relaxation_ids:
            duplicate_relaxation_rows.append(
                {
                    "candidate_id": candidate_id,
                    "row_index": row_index,
                    "reason": "duplicate_relaxation_candidate_id",
                    "relaxation_candidate": compact,
                }
            )
            continue
        seen_relaxation_ids.add(candidate_id)

        full = candidates_by_id.get(candidate_id)
        if full is None:
            missing.append(
                {
                    "candidate_id": candidate_id,
                    "formula": _formula(compact),
                    "row_index": row_index,
                    "reason": "candidate_id_not_found_in_full_sources",
                    "relaxation_candidate": compact,
                }
            )
            continue

        hydrated_row = _hydrate_row(full, compact, relaxation_path, row_index, output_dir)
        hydrated.append(hydrated_row)
        index_rows.append(_index_row(index_by_id.get(candidate_id), hydrated_row, compact))

    formula_counts = Counter(_formula(row) or "unknown" for row in hydrated)
    duplicate_rows = duplicate_candidates + duplicate_index_rows + duplicate_relaxation_rows
    summary = {
        "workflow": "mace_relaxation_candidate_hydration",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "source_relaxation_candidates": str(relaxation_path),
        "candidate_input_paths": [str(path) for path in candidate_paths],
        "candidate_index_input_paths": [str(path) for path in candidate_index_paths],
        "relaxation_candidate_count": len(compact_rows),
        "hydrated_candidate_count": len(hydrated),
        "missing_candidate_count": len(missing),
        "duplicate_row_count": len(duplicate_rows),
        "formula_counts": dict(sorted(formula_counts.items())),
        "output_jsonl": str(output_jsonl),
        "output_index_jsonl": str(output_index_jsonl),
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
        "input_hashes": {
            str(path): _sha256(path)
            for path in [relaxation_path, *candidate_paths, *candidate_index_paths]
            if path.exists()
        },
    }

    write_jsonl(output_jsonl, hydrated)
    write_jsonl(output_index_jsonl, index_rows)
    write_jsonl(missing_jsonl, missing)
    write_jsonl(duplicate_jsonl, duplicate_rows)
    write_json(summary_json, summary)
    report.write_text(_render_report(summary), encoding="utf-8")

    print("MACE relaxation candidate hydration complete")
    print(f"  relaxation_candidate_count: {summary['relaxation_candidate_count']}")
    print(f"  hydrated_candidate_count: {summary['hydrated_candidate_count']}")
    print(f"  missing_candidate_count: {summary['missing_candidate_count']}")
    print(f"  duplicate_row_count: {summary['duplicate_row_count']}")
    print(f"  output_jsonl: {output_jsonl}")
    print(f"  output_index_jsonl: {output_index_jsonl}")
    print(f"  summary: {summary_json}")

    if args.strict and (missing or not hydrated):
        raise SystemExit("strict hydration found missing candidates or emitted no rows")
    return {
        "summary": summary,
        "files": {
            "hydrated_candidates": str(output_jsonl),
            "candidate_index": str(output_index_jsonl),
            "missing_candidates": str(missing_jsonl),
            "duplicate_candidates": str(duplicate_jsonl),
            "summary": str(summary_json),
            "report": str(report),
        },
    }


def _paths(explicit: Iterable[str], patterns: Iterable[str]) -> list[Path]:
    paths = [Path(path) for path in explicit]
    for pattern in patterns:
        paths.extend(Path(path) for path in glob.glob(pattern))
    return sorted({path.resolve() for path in paths if path.exists() and path.is_file()})


def _load_unique_by_id(paths: list[Path]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for path in paths:
        for row_index, row in enumerate(read_jsonl(path), start=1):
            candidate_id = _candidate_id(row)
            if candidate_id is None:
                continue
            if candidate_id in rows_by_id:
                duplicates.append(
                    {
                        "candidate_id": candidate_id,
                        "path": str(path),
                        "row_index": row_index,
                        "reason": "duplicate_candidate_id_in_sources",
                    }
                )
                continue
            copied = dict(row)
            metadata = dict(copied.get("metadata", {})) if isinstance(copied.get("metadata"), dict) else {}
            metadata.setdefault("hydration_source_jsonl", str(path))
            copied["metadata"] = metadata
            rows_by_id[candidate_id] = copied
    return rows_by_id, duplicates


def _hydrate_row(
    full: dict[str, Any],
    compact: dict[str, Any],
    relaxation_path: Path,
    row_index: int,
    output_dir: Path,
) -> dict[str, Any]:
    row = dict(full)
    metadata = dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {}
    metadata["mace_relaxation_input_output_dir"] = str(output_dir)
    metadata["mace_relaxation_selection"] = {
        "source_relaxation_candidates_jsonl": str(relaxation_path),
        "source_relaxation_row_index": row_index,
        "candidate_id": _candidate_id(compact),
        "formula": _formula(compact),
        "force_max": compact.get("force_max"),
        "stress_max": compact.get("stress_max"),
        "mace_total_energy_eV_per_atom": compact.get("mace_total_energy_eV_per_atom"),
        "spacegroup": compact.get("spacegroup"),
        "reasons": list(compact.get("reasons", [])) if isinstance(compact.get("reasons"), list) else [],
        "severity_score": compact.get("severity_score"),
    }
    row["metadata"] = metadata
    return row


def _index_row(index_row: dict[str, Any] | None, full: dict[str, Any], compact: dict[str, Any]) -> dict[str, Any]:
    row = dict(index_row) if index_row is not None else {}
    candidate_id = _candidate_id(full) or _candidate_id(compact)
    formula = _formula(full) or _formula(compact)
    row.setdefault("candidate_id", candidate_id)
    row.setdefault("composition", formula)
    row.setdefault("condition", full.get("condition", compact.get("condition", {"formula": formula})))
    row["mace_relaxation_source_candidate_id"] = candidate_id
    row["mace_relaxation_selection_force_max"] = compact.get("force_max")
    row["mace_relaxation_selection_stress_max"] = compact.get("stress_max")
    return row


def _candidate_id(row: dict[str, Any]) -> str | None:
    value = row.get("candidate_id", row.get("sample_id", row.get("id")))
    return None if value in (None, "") else str(value)


def _formula(row: dict[str, Any]) -> str | None:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    value = row.get("formula", row.get("composition", condition.get("formula")))
    return None if value in (None, "") else str(value)


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# MACE Relaxation Candidate Hydration",
        "",
        "## Boundary",
        "- Reads existing relaxation triage rows and full candidate JSONL files only.",
        "- Does not run generation, MLIP, DFT, training, downloads, or external APIs.",
        "",
        "## Summary",
        f"- relaxation_candidate_count: {summary['relaxation_candidate_count']}",
        f"- hydrated_candidate_count: {summary['hydrated_candidate_count']}",
        f"- missing_candidate_count: {summary['missing_candidate_count']}",
        f"- duplicate_row_count: {summary['duplicate_row_count']}",
        f"- output_jsonl: `{summary['output_jsonl']}`",
        f"- output_index_jsonl: `{summary['output_index_jsonl']}`",
        "",
        "## Formula Counts",
    ]
    for formula, count in sorted(summary["formula_counts"].items()):
        lines.append(f"- {formula}: {count}")
    lines.append("")
    return "\n".join(lines)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
