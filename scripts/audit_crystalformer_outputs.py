"""CLI for smoke-auditing CrystalFormer outputs before DPO data prep."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.evaluation.error_audit import (
    F3_UNAVAILABLE_MODE,
    audit_candidates,
    summarize_audit,
    write_audit_outputs,
)
from fiir_crystal.generation.crystalformer_adapter import CrystalFormerAdapter
from fiir_crystal.structures import CrystalStructureRecord, read_jsonl
from fiir_crystal.structures.parsers import parse_cif_file_optional, parse_cif_text_optional


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke audit deepmodeling/CrystalFormer outputs with FIIR failure labels."
    )
    parser.add_argument("--input-dir", help="CrystalFormer raw output directory or file.")
    parser.add_argument("--candidates-jsonl", help="Already normalized CrystalStructureRecord JSONL.")
    parser.add_argument("--formula")
    parser.add_argument("--spacegroup", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--parser-backend", choices=["auto", "none", "pymatgen"], default="auto")
    parser.add_argument(
        "--stability-mode",
        choices=[F3_UNAVAILABLE_MODE],
        default=F3_UNAVAILABLE_MODE,
    )
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--fail-on-zero-parsed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any] | None:
    args = parse_args(argv)
    _validate_args(args)
    output_dir = _resolve_output_dir(args.output_dir, args.formula)

    if args.dry_run:
        summary = {
            "dry_run": True,
            "input_dir": args.input_dir,
            "candidates_jsonl": args.candidates_jsonl,
            "formula": args.formula,
            "spacegroup": args.spacegroup,
            "output_dir": str(output_dir),
            "parser_backend": args.parser_backend,
            "stability_mode": args.stability_mode,
        }
        print("CrystalFormer smoke audit dry run")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        return summary

    records = _load_records(args)
    if args.max_candidates is not None:
        records = records[: args.max_candidates]
    records = _apply_optional_parsing(records, args.parser_backend)
    results = audit_candidates(
        records,
        formula=args.formula,
        spacegroup=args.spacegroup,
        stability_mode=args.stability_mode,
    )
    summary = summarize_audit(
        results,
        candidates=records,
        formula=args.formula,
        spacegroup=args.spacegroup,
        stability_mode=args.stability_mode,
    )
    files = write_audit_outputs(output_dir, records, results, summary)

    print("CrystalFormer smoke audit complete")
    print(f"  candidates: {summary.total_candidates}")
    print(f"  parsed_full_structure_count: {summary.parsed_full_structure_count}")
    print(f"  f3_unknown_count: {summary.f3_unknown_count}")
    print(f"  output_dir: {output_dir}")
    print(f"  report: {files['report']}")

    if args.fail_on_zero_parsed and summary.parsed_full_structure_count == 0:
        raise SystemExit("no fully parsed structures were found")
    return {"summary": summary.to_dict(), "files": files}


def _validate_args(args: argparse.Namespace) -> None:
    if bool(args.input_dir) == bool(args.candidates_jsonl):
        raise SystemExit("provide exactly one of --input-dir or --candidates-jsonl")
    if args.max_candidates is not None and args.max_candidates < 1:
        raise SystemExit("--max-candidates must be positive")


def _resolve_output_dir(output_dir: str | None, formula: str | None) -> Path:
    if output_dir:
        return Path(output_dir)
    return Path("outputs") / "crystalformer_audit" / (formula or "unknown_formula")


def _load_records(args: argparse.Namespace) -> list[CrystalStructureRecord]:
    if args.candidates_jsonl:
        return read_jsonl(args.candidates_jsonl)
    adapter = CrystalFormerAdapter(
        {
            "source_format": "auto",
            "formula": args.formula,
            "spacegroup": args.spacegroup,
            "stability_mode": args.stability_mode,
        }
    )
    return adapter.load_outputs(args.input_dir)


def _apply_optional_parsing(
    records: list[CrystalStructureRecord],
    parser_backend: str,
) -> list[CrystalStructureRecord]:
    if parser_backend == "none":
        for record in records:
            if not _is_full_structure(record) and record.structure_ref:
                record.metadata.setdefault("parse_status", "unparsed_cif")
                record.metadata.setdefault("parser_backend", "none")
        return records

    parsed_records: list[CrystalStructureRecord] = []
    for record in records:
        if _is_full_structure(record):
            record.metadata.setdefault("parse_status", "parsed_full_structure")
            parsed_records.append(record)
            continue
        parsed = _parse_record_ref(record, parser_backend)
        parsed_records.append(_merge_parsed_record(record, parsed) if parsed else record)
    return parsed_records


def _parse_record_ref(
    record: CrystalStructureRecord,
    parser_backend: str,
) -> CrystalStructureRecord | None:
    ref = record.structure_ref
    if not ref:
        return None
    if _looks_like_cif_text(ref):
        return parse_cif_text_optional(ref, parser_backend=parser_backend, candidate_id=record.candidate_id)
    try:
        path = Path(ref)
        if path.exists():
            return parse_cif_file_optional(path, parser_backend=parser_backend)
    except OSError as exc:
        parsed = parse_cif_text_optional("", parser_backend="none", candidate_id=record.candidate_id)
        parsed.metadata["parse_status"] = "parse_error"
        parsed.metadata["parse_error_type"] = exc.__class__.__name__
        parsed.metadata["parse_error_message"] = str(exc)
        return parsed
    record.metadata.setdefault("parse_status", "unparsed_cif")
    record.metadata.setdefault("parser_backend", parser_backend)
    return None


def _merge_parsed_record(
    original: CrystalStructureRecord,
    parsed: CrystalStructureRecord,
) -> CrystalStructureRecord:
    metadata = dict(original.metadata)
    original_source_format = metadata.get("source_format", "unknown")
    metadata.update(parsed.metadata)
    metadata["source_format"] = original_source_format
    return CrystalStructureRecord(
        candidate_id=original.candidate_id,
        species=parsed.species or original.species,
        frac_coords=parsed.frac_coords or original.frac_coords,
        lattice_matrix=parsed.lattice_matrix or original.lattice_matrix,
        pbc=original.pbc,
        composition=parsed.composition or original.composition,
        num_sites=parsed.num_sites or original.num_sites,
        space_group=parsed.space_group if parsed.space_group is not None else original.space_group,
        wyckoff_letters=original.wyckoff_letters,
        prototype=original.prototype,
        structure_ref=original.structure_ref or parsed.structure_ref,
        source=original.source,
        metadata=metadata,
    )


def _is_full_structure(record: CrystalStructureRecord) -> bool:
    return bool(record.species and record.frac_coords and record.lattice_matrix)


def _looks_like_cif_text(value: str) -> bool:
    return "\n" in value and "data_" in value[:100]


if __name__ == "__main__":
    main()
