"""Unified local smoke pipeline for CrystalFormer outputs.

The pipeline is an integration layer only. It can optionally run a user-supplied
CrystalFormer command, then loads local outputs, audits them, and builds the
schema-first DPO preference artifact. It does not train, validate stability,
download checkpoints, or import CrystalFormer runtime dependencies.
"""

from __future__ import annotations

import shlex
import subprocess
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from fiir_crystal.dpo import PreferenceBuildConfig, build_dpo_preferences, write_preference_outputs
from fiir_crystal.evaluation.error_audit import (
    F3_UNAVAILABLE_MODE,
    audit_candidate_result_from_dict,
    audit_candidates,
    summarize_audit,
    write_audit_outputs,
)
from fiir_crystal.generation.crystalformer_adapter import CrystalFormerAdapter
from fiir_crystal.io import write_json
from fiir_crystal.structures import CrystalStructureRecord
from fiir_crystal.structures.parsers import parse_cif_file_optional, parse_cif_text_optional
from fiir_crystal.validation import (
    OfflineValidationImportConfig,
    import_offline_validation_to_audit_rows,
    read_offline_validation_jsonl,
)


@dataclass(slots=True)
class CrystalFormerSmokePipelineConfig:
    """Configuration for the local CrystalFormer smoke pipeline."""

    input_dir: Path
    formula: str
    output_root: Path = Path("outputs")
    parser_backend: str = "auto"
    stability_mode: str = F3_UNAVAILABLE_MODE
    spacegroup: int | None = None
    source_format: str = "auto"
    max_candidates: int | None = None
    min_preference_margin: float = 1e-6
    max_pairs: int | None = None
    crystalformer_command: str | None = None
    crystalformer_work_dir: Path | None = None
    run_generation: bool = False
    offline_validation_jsonl: Path | None = None


def run_crystalformer_smoke_pipeline(
    config: CrystalFormerSmokePipelineConfig,
) -> dict[str, Any]:
    """Run generation provenance, load-only audit, and DPO artifact construction."""

    _validate_config(config)
    output_dirs = _output_dirs(config.output_root, config.formula)
    output_dirs["run"].mkdir(parents=True, exist_ok=True)

    provenance = _initial_provenance(config)
    if config.run_generation:
        provenance["generation"] = _run_generation(config)
        write_json(output_dirs["provenance"], provenance)
        if provenance["generation"]["returncode"] != 0:
            raise RuntimeError(
                "CrystalFormer generation command failed with returncode "
                f"{provenance['generation']['returncode']}; provenance was written to {output_dirs['provenance']}"
            )
    else:
        provenance["generation"] = {
            "executed": False,
            "reason": "run_generation_not_requested",
            "command_present": bool(config.crystalformer_command),
        }
        write_json(output_dirs["provenance"], provenance)

    records = _load_records(config)
    if config.max_candidates is not None:
        records = records[: config.max_candidates]
    records = _apply_optional_parsing(records, config.parser_backend)

    audit_results = audit_candidates(
        records,
        formula=config.formula,
        spacegroup=config.spacegroup,
        stability_mode=config.stability_mode,
    )
    validation_summary: dict[str, Any] | None = None
    if config.offline_validation_jsonl is not None:
        validation_records = read_offline_validation_jsonl(config.offline_validation_jsonl)
        updated_rows, validation_import_summary = import_offline_validation_to_audit_rows(
            [result.to_dict() for result in audit_results],
            validation_records,
            OfflineValidationImportConfig(formula=config.formula, spacegroup=config.spacegroup),
        )
        audit_results = [audit_candidate_result_from_dict(row) for row in updated_rows]
        validation_summary = validation_import_summary.to_dict()
        write_json(output_dirs["validation_summary"], validation_import_summary)
        provenance["offline_validation"] = _validation_file_provenance(
            config.offline_validation_jsonl,
            len(validation_records),
        )
        write_json(output_dirs["provenance"], provenance)

    audit_summary = summarize_audit(
        audit_results,
        candidates=records,
        formula=config.formula,
        spacegroup=config.spacegroup,
        stability_mode=config.stability_mode,
    )
    audit_files = write_audit_outputs(output_dirs["audit"], records, audit_results, audit_summary)

    dpo_config = PreferenceBuildConfig(
        formula=config.formula,
        spacegroup=config.spacegroup,
        min_preference_margin=config.min_preference_margin,
        max_pairs=config.max_pairs,
    )
    pairs, preference_summary = build_dpo_preferences(
        [result.to_dict() for result in audit_results],
        dpo_config,
    )
    preference_files = write_preference_outputs(output_dirs["preferences"], pairs, preference_summary)

    summary = _pipeline_summary(
        config=config,
        records=records,
        audit_results=[result.to_dict() for result in audit_results],
        audit_summary=audit_summary.to_dict(),
        preference_summary=preference_summary.to_dict(),
        validation_summary=validation_summary,
        output_dirs=output_dirs,
    )
    write_json(output_dirs["summary"], summary)
    output_dirs["report"].write_text(_render_report(summary), encoding="utf-8")

    return {
        "summary": summary,
        "files": {
            "provenance": str(output_dirs["provenance"]),
            "pipeline_summary": str(output_dirs["summary"]),
            "pipeline_report": str(output_dirs["report"]),
            "validation_import_summary": (
                None if validation_summary is None else str(output_dirs["validation_summary"])
            ),
            "audit": audit_files,
            "preferences": preference_files,
        },
    }


def _validate_config(config: CrystalFormerSmokePipelineConfig) -> None:
    if not config.formula:
        raise ValueError("CrystalFormer smoke pipeline requires --formula.")
    if config.stability_mode != F3_UNAVAILABLE_MODE:
        raise ValueError(f"unsupported stability_mode: {config.stability_mode}")
    if config.parser_backend not in {"auto", "none", "pymatgen"}:
        raise ValueError(f"unsupported parser_backend: {config.parser_backend}")
    if config.max_candidates is not None and config.max_candidates < 1:
        raise ValueError("max_candidates must be positive.")
    if config.run_generation:
        if not config.crystalformer_command:
            raise ValueError("--run-generation requires --crystalformer-command.")
        if config.crystalformer_work_dir is None:
            raise ValueError("--run-generation requires --crystalformer-work-dir.")
        if not config.crystalformer_work_dir.exists():
            raise FileNotFoundError(f"CrystalFormer work dir does not exist: {config.crystalformer_work_dir}")
    if config.offline_validation_jsonl is not None and not config.offline_validation_jsonl.exists():
        raise FileNotFoundError(f"offline validation JSONL does not exist: {config.offline_validation_jsonl}")


def _run_generation(config: CrystalFormerSmokePipelineConfig) -> dict[str, Any]:
    command = str(config.crystalformer_command)
    args = shlex.split(command)
    cwd = config.crystalformer_work_dir
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "executed": True,
        "command": command,
        "args": args,
        "cwd": str(cwd) if cwd is not None else None,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _load_records(config: CrystalFormerSmokePipelineConfig) -> list[CrystalStructureRecord]:
    adapter = CrystalFormerAdapter(
        {
            "source_format": config.source_format,
            "formula": config.formula,
            "spacegroup": config.spacegroup,
            "stability_mode": config.stability_mode,
        }
    )
    return adapter.load_outputs(config.input_dir)


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


def _pipeline_summary(
    *,
    config: CrystalFormerSmokePipelineConfig,
    records: list[CrystalStructureRecord],
    audit_results: list[dict[str, Any]],
    audit_summary: dict[str, Any],
    preference_summary: dict[str, Any],
    validation_summary: dict[str, Any] | None,
    output_dirs: dict[str, Path],
) -> dict[str, Any]:
    parse_status_counts = Counter(row.get("parse_status", "unknown") for row in audit_results)
    f1_counts = Counter(row.get("f1_label", "unknown") for row in audit_results)
    f2_counts = Counter(row.get("f2_label", "unknown") for row in audit_results)
    f3_counts = Counter(row.get("f3_label", "unknown") for row in audit_results)
    return {
        "pipeline": "crystalformer_real_smoke",
        "train_dpo": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_materials_project": False,
        "downloads_checkpoints": False,
        "input_dir": str(config.input_dir),
        "formula": config.formula,
        "spacegroup": config.spacegroup,
        "parser_backend": config.parser_backend,
        "stability_mode": config.stability_mode,
        "candidate_count": len(records),
        "parse_status_counts": dict(sorted(parse_status_counts.items())),
        "f1_status_counts": dict(sorted(f1_counts.items())),
        "f2_status_counts": dict(sorted(f2_counts.items())),
        "f3_status_counts": dict(sorted(f3_counts.items())),
        "f3_validation": "imported_offline_results" if validation_summary is not None else "unavailable",
        "offline_validation_jsonl": (
            None if config.offline_validation_jsonl is None else str(config.offline_validation_jsonl)
        ),
        "offline_validation_imported": validation_summary is not None,
        "validation_import_summary": validation_summary,
        "dpo_eligible_count": audit_summary.get("dpo_eligible_count", 0),
        "preference_pair_count": preference_summary.get("pair_count", 0),
        "preference_skip_reasons": preference_summary.get("skip_reasons", {}),
        "no_comparable_margin_count": preference_summary.get("skip_reasons", {}).get("no_comparable_margin", 0),
        "no_comparable_candidates_count": preference_summary.get("skip_reasons", {}).get("no_comparable_candidates", 0),
        "audit_summary": audit_summary,
        "preference_summary": preference_summary,
        "output_dirs": {
            "run": str(output_dirs["run"]),
            "audit": str(output_dirs["audit"]),
            "preferences": str(output_dirs["preferences"]),
        },
    }


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# CrystalFormer Smoke Pipeline Report",
        "",
        "## Boundary",
        "- This is a local smoke integration pipeline, not DPO training.",
        "- It does not run DFT, MLIP, Materials Project, checkpoint download, or dataset download.",
        "- Without offline validation, F3 is unavailable/unknown and no candidate is reported as stable.",
        "",
        "## Summary",
        f"- formula: {summary['formula']}",
        f"- candidate_count: {summary['candidate_count']}",
        f"- parse_status_counts: {summary['parse_status_counts']}",
        f"- f1_status_counts: {summary['f1_status_counts']}",
        f"- f2_status_counts: {summary['f2_status_counts']}",
        f"- f3_status_counts: {summary['f3_status_counts']}",
        f"- f3_validation: {'imported_offline_results' if summary['offline_validation_imported'] else summary['f3_validation']}",
        f"- offline_validation_imported: {summary['offline_validation_imported']}",
        f"- dpo_eligible_count: {summary['dpo_eligible_count']}",
        f"- preference_pair_count: {summary['preference_pair_count']}",
        f"- preference_skip_reasons: {summary['preference_skip_reasons']}",
        "",
        "## Artifacts",
        f"- audit_dir: `{summary['output_dirs']['audit']}`",
        f"- dpo_preferences_dir: `{summary['output_dirs']['preferences']}`",
        "",
    ]
    return "\n".join(lines)


def _output_dirs(output_root: Path, formula: str) -> dict[str, Path]:
    root = Path(output_root)
    run_dir = root / "crystalformer_smoke_pipeline" / formula
    return {
        "root": root,
        "run": run_dir,
        "audit": root / "crystalformer_audit" / formula,
        "preferences": root / "dpo_preferences" / formula,
        "provenance": run_dir / "provenance.json",
        "validation_summary": run_dir / "validation_import_summary.json",
        "summary": run_dir / "pipeline_summary.json",
        "report": run_dir / "report.md",
    }


def _initial_provenance(config: CrystalFormerSmokePipelineConfig) -> dict[str, Any]:
    return {
        "pipeline": "crystalformer_real_smoke",
        "input_dir": str(config.input_dir),
        "formula": config.formula,
        "spacegroup": config.spacegroup,
        "parser_backend": config.parser_backend,
        "stability_mode": config.stability_mode,
        "run_generation_requested": config.run_generation,
        "crystalformer_command": config.crystalformer_command,
        "crystalformer_work_dir": (
            None if config.crystalformer_work_dir is None else str(config.crystalformer_work_dir)
        ),
        "offline_validation_jsonl": (
            None if config.offline_validation_jsonl is None else str(config.offline_validation_jsonl)
        ),
    }


def _validation_file_provenance(path: Path, record_count: int) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "size_bytes": len(data),
        "sha256": sha256(data).hexdigest(),
        "record_count": record_count,
        "mode": "imported_offline_results",
    }


def _is_full_structure(record: CrystalStructureRecord) -> bool:
    return bool(record.species and record.frac_coords and record.lattice_matrix)


def _looks_like_cif_text(value: str) -> bool:
    return "\n" in value and "data_" in value[:100]
