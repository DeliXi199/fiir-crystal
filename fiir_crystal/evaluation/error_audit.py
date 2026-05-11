"""Smoke error audit for CrystalFormer candidates entering FIIR."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.failure import FailureOracle
from fiir_crystal.failure.taxonomy import FailureVector
from fiir_crystal.io import write_json, write_jsonl
from fiir_crystal.structures import (
    CrystalStructureRecord,
    crystalformer_sequence_status,
)
from fiir_crystal.structures.serialization import write_jsonl as write_structure_jsonl


F3_UNAVAILABLE_MODE = "unavailable_without_offline_validation"


@dataclass(slots=True)
class AuditCandidateResult:
    """Per-candidate CrystalFormer smoke audit record."""

    candidate_id: str
    composition: str | None
    source_format: str
    parse_status: str
    raw_sequence_status: str
    f1_label: str
    f2_label: str
    f3_label: str
    failure_vector: dict[str, Any]
    evidence: dict[str, Any]
    fiir_score: float | None
    ranking_score: float | None
    dpo_eligible: bool
    dpo_ineligible_reasons: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    preference_type: str | None = None
    condition: dict[str, Any] = field(default_factory=dict)
    raw_sequence_fields: dict[str, Any] = field(default_factory=dict)
    offline_validation: dict[str, Any] | None = None
    validation_status: str = "not_provided"
    f3_source: str = F3_UNAVAILABLE_MODE
    f3_validation_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "composition": self.composition,
            "source_format": self.source_format,
            "parse_status": self.parse_status,
            "raw_sequence_status": self.raw_sequence_status,
            "f1_label": self.f1_label,
            "f2_label": self.f2_label,
            "f3_label": self.f3_label,
            "failure_vector": dict(self.failure_vector),
            "evidence": dict(self.evidence),
            "fiir_score": self.fiir_score,
            "ranking_score": self.ranking_score,
            "dpo_eligible": self.dpo_eligible,
            "dpo_ineligible_reasons": list(self.dpo_ineligible_reasons),
            "failure_reasons": list(self.failure_reasons),
            "preference_type": self.preference_type,
            "condition": dict(self.condition),
            "raw_sequence_fields": dict(self.raw_sequence_fields),
            "offline_validation": (
                None if self.offline_validation is None else dict(self.offline_validation)
            ),
            "validation_status": self.validation_status,
            "f3_source": self.f3_source,
            "f3_validation_available": self.f3_validation_available,
        }


@dataclass(slots=True)
class AuditSummary:
    """Aggregate smoke audit statistics."""

    total_candidates: int
    parsed_full_structure_count: int
    partial_sequence_count: int
    missing_raw_sequence_count: int
    unparsed_cif_count: int
    parse_error_count: int
    f1_pass_count: int
    f1_fail_count: int
    f1_fail_rate: float
    f2_pass_count: int
    f2_fail_count: int
    f2_fail_rate: float
    f3_available_count: int
    f3_unknown_count: int
    f3_unknown_rate: float
    duplicate_composition_count: int
    duplicate_structure_ref_count: int
    source_format_breakdown: dict[str, int]
    top_failure_reasons: list[dict[str, Any]]
    top_parse_errors: list[dict[str, Any]]
    dpo_eligible_count: int = 0
    dpo_ineligible_count: int = 0
    offline_validation_available_count: int = 0
    offline_validation_error_count: int = 0
    f3_validated_stable_count: int = 0
    condition: dict[str, Any] = field(default_factory=dict)
    stability_mode: str = F3_UNAVAILABLE_MODE

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "parsed_full_structure_count": self.parsed_full_structure_count,
            "partial_sequence_count": self.partial_sequence_count,
            "missing_raw_sequence_count": self.missing_raw_sequence_count,
            "unparsed_cif_count": self.unparsed_cif_count,
            "parse_error_count": self.parse_error_count,
            "f1_pass_count": self.f1_pass_count,
            "f1_fail_count": self.f1_fail_count,
            "f1_fail_rate": self.f1_fail_rate,
            "f2_pass_count": self.f2_pass_count,
            "f2_fail_count": self.f2_fail_count,
            "f2_fail_rate": self.f2_fail_rate,
            "f3_available_count": self.f3_available_count,
            "f3_unknown_count": self.f3_unknown_count,
            "f3_unknown_rate": self.f3_unknown_rate,
            "duplicate_composition_count": self.duplicate_composition_count,
            "duplicate_structure_ref_count": self.duplicate_structure_ref_count,
            "source_format_breakdown": dict(self.source_format_breakdown),
            "top_failure_reasons": [dict(item) for item in self.top_failure_reasons],
            "top_parse_errors": [dict(item) for item in self.top_parse_errors],
            "dpo_eligible_count": self.dpo_eligible_count,
            "dpo_ineligible_count": self.dpo_ineligible_count,
            "offline_validation_available_count": self.offline_validation_available_count,
            "offline_validation_error_count": self.offline_validation_error_count,
            "f3_validated_stable_count": self.f3_validated_stable_count,
            "condition": dict(self.condition),
            "stability_mode": self.stability_mode,
        }


def audit_candidates(
    candidates: Sequence[CrystalStructureRecord],
    *,
    formula: str | None = None,
    spacegroup: int | None = None,
    oracle: FailureOracle | None = None,
    stability_mode: str = F3_UNAVAILABLE_MODE,
) -> list[AuditCandidateResult]:
    """Audit candidates with FIIR F1/F2 and explicit F3-unavailable handling."""

    oracle = oracle or FailureOracle.default()
    results: list[AuditCandidateResult] = []
    for record in candidates:
        metadata = record.metadata
        parse_status = _parse_status(record)
        raw_sequence_status, missing_sequence_fields = crystalformer_sequence_status(metadata)
        condition = _condition_for(record, formula=formula, spacegroup=spacegroup)
        vector_dict, oracle_error = _failure_vector_dict(record, oracle, stability_mode)
        f1_value = _as_float_or_none(vector_dict.get("f1_geometry"))
        f2_value = _as_float_or_none(vector_dict.get("f2_chemistry"))
        f3_value = _as_float_or_none(vector_dict.get("f3_stability"))
        f3_unknown = _f3_is_unknown(stability_mode, f3_value)
        if f3_unknown:
            vector_dict["f3_stability"] = None
            vector_dict.setdefault("metadata", {})["f3_status"] = "unknown_unavailable"
        f1_label = _pass_fail_label(f1_value)
        f2_label = _pass_fail_label(f2_value)
        f3_label = "unknown" if f3_unknown else _pass_fail_label(f3_value)
        fiir_score = _fiir_score(f1_value, f2_value, None if f3_unknown else f3_value)
        ranking_score = None if fiir_score is None else round(1.0 - fiir_score, 6)
        failure_reasons = _failure_reasons(vector_dict, parse_status, oracle_error)
        dpo_eligible, dpo_reasons = _dpo_eligibility(
            record=record,
            parse_status=parse_status,
            condition=condition,
            fiir_score=fiir_score,
        )
        evidence = {
            "condition": condition,
            "missing_sequence_fields": missing_sequence_fields,
            "source_checkpoint": metadata.get("source_checkpoint"),
            "original_row_index": metadata.get("original_row_index"),
            "parse_error": _parse_error(metadata, oracle_error),
            "f3_status": "unknown_unavailable" if f3_unknown else "available",
            "stability_mode": stability_mode,
        }
        results.append(
            AuditCandidateResult(
                candidate_id=str(record.candidate_id),
                composition=record.composition,
                source_format=str(metadata.get("source_format", "unknown")),
                parse_status=parse_status,
                raw_sequence_status=raw_sequence_status,
                f1_label=f1_label,
                f2_label=f2_label,
                f3_label=f3_label,
                failure_vector=vector_dict,
                evidence=evidence,
                fiir_score=fiir_score,
                ranking_score=ranking_score,
                dpo_eligible=dpo_eligible,
                dpo_ineligible_reasons=dpo_reasons,
                failure_reasons=failure_reasons,
                preference_type="geometry_chemistry_only" if dpo_eligible and f3_unknown else None,
                condition=condition,
                raw_sequence_fields=_raw_sequence_fields(metadata),
                offline_validation=None,
                validation_status="not_provided",
                f3_source="unavailable_without_offline_validation" if f3_unknown else "fiir_oracle",
                f3_validation_available=False,
            )
        )
    return results


def audit_candidate_result_from_dict(row: dict[str, Any]) -> AuditCandidateResult:
    """Rebuild an `AuditCandidateResult` from a JSON-compatible row."""

    return AuditCandidateResult(
        candidate_id=str(row["candidate_id"]),
        composition=row.get("composition"),
        source_format=str(row.get("source_format", "unknown")),
        parse_status=str(row.get("parse_status", "unknown")),
        raw_sequence_status=str(row.get("raw_sequence_status", "missing")),
        f1_label=str(row.get("f1_label", "unknown")),
        f2_label=str(row.get("f2_label", "unknown")),
        f3_label=str(row.get("f3_label", "unknown")),
        failure_vector=dict(row.get("failure_vector", {})),
        evidence=dict(row.get("evidence", {})),
        fiir_score=_as_float_or_none(row.get("fiir_score")),
        ranking_score=_as_float_or_none(row.get("ranking_score")),
        dpo_eligible=bool(row.get("dpo_eligible")),
        dpo_ineligible_reasons=[str(item) for item in row.get("dpo_ineligible_reasons", [])],
        failure_reasons=[str(item) for item in row.get("failure_reasons", [])],
        preference_type=row.get("preference_type"),
        condition=dict(row.get("condition", {})),
        raw_sequence_fields=dict(row.get("raw_sequence_fields", {})),
        offline_validation=(
            dict(row["offline_validation"])
            if isinstance(row.get("offline_validation"), dict)
            else None
        ),
        validation_status=str(row.get("validation_status", "not_provided")),
        f3_source=str(row.get("f3_source", F3_UNAVAILABLE_MODE)),
        f3_validation_available=bool(row.get("f3_validation_available", False)),
    )


def summarize_audit(
    results: Sequence[AuditCandidateResult],
    *,
    candidates: Sequence[CrystalStructureRecord] | None = None,
    formula: str | None = None,
    spacegroup: int | None = None,
    stability_mode: str = F3_UNAVAILABLE_MODE,
) -> AuditSummary:
    """Summarize per-candidate audit records."""

    total = len(results)
    f1_fail = sum(result.f1_label == "fail" for result in results)
    f2_fail = sum(result.f2_label == "fail" for result in results)
    f3_unknown = sum(result.f3_label in {"unknown", "unavailable"} for result in results)
    source_formats = Counter(result.source_format for result in results)
    failure_reasons: Counter[str] = Counter()
    parse_errors: Counter[str] = Counter()
    for result in results:
        failure_reasons.update(result.failure_reasons)
        parse_error = result.evidence.get("parse_error")
        if parse_error:
            parse_errors[str(parse_error)] += 1

    compositions = Counter(
        record.composition
        for record in candidates or []
        if record.composition
    )
    structure_refs = Counter(
        record.structure_ref
        for record in candidates or []
        if record.structure_ref
    )

    return AuditSummary(
        total_candidates=total,
        parsed_full_structure_count=sum(result.parse_status == "parsed_full_structure" for result in results),
        partial_sequence_count=sum(result.raw_sequence_status == "partial" for result in results),
        missing_raw_sequence_count=sum(result.raw_sequence_status == "missing" for result in results),
        unparsed_cif_count=sum(result.parse_status == "unparsed_cif" for result in results),
        parse_error_count=sum(result.parse_status == "parse_error" for result in results),
        f1_pass_count=sum(result.f1_label == "pass" for result in results),
        f1_fail_count=f1_fail,
        f1_fail_rate=_rate(f1_fail, total),
        f2_pass_count=sum(result.f2_label == "pass" for result in results),
        f2_fail_count=f2_fail,
        f2_fail_rate=_rate(f2_fail, total),
        f3_available_count=sum(result.f3_label not in {"unknown", "unavailable"} for result in results),
        f3_unknown_count=f3_unknown,
        f3_unknown_rate=_rate(f3_unknown, total),
        duplicate_composition_count=_duplicate_extra_count(compositions),
        duplicate_structure_ref_count=_duplicate_extra_count(structure_refs),
        source_format_breakdown=dict(sorted(source_formats.items())),
        top_failure_reasons=_top_items(failure_reasons),
        top_parse_errors=_top_items(parse_errors),
        dpo_eligible_count=sum(result.dpo_eligible for result in results),
        dpo_ineligible_count=sum(not result.dpo_eligible for result in results),
        offline_validation_available_count=sum(result.f3_validation_available for result in results),
        offline_validation_error_count=sum(
            result.validation_status in {"error", "failed", "validation_error"} for result in results
        ),
        f3_validated_stable_count=sum(
            result.f3_validation_available
            and isinstance(result.offline_validation, dict)
            and result.offline_validation.get("is_stable") is True
            for result in results
        ),
        condition={"mode": "csp", "formula": formula, "spacegroup": spacegroup},
        stability_mode=stability_mode,
    )


def write_audit_outputs(
    output_dir: str | Path,
    candidates: Sequence[CrystalStructureRecord],
    audit_results: Sequence[AuditCandidateResult],
    summary: AuditSummary,
) -> dict[str, str]:
    """Write the standard CrystalFormer smoke audit artifact set."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "candidates": str(destination / "candidates.jsonl"),
        "audit_candidates": str(destination / "audit_candidates.jsonl"),
        "audit_summary": str(destination / "audit_summary.json"),
        "failure_vectors": str(destination / "failure_vectors.jsonl"),
        "error_audit_table": str(destination / "error_audit_table.md"),
        "report": str(destination / "report.md"),
    }
    write_structure_jsonl(files["candidates"], candidates)
    write_jsonl(files["audit_candidates"], audit_results)
    write_json(files["audit_summary"], summary)
    write_jsonl(files["failure_vectors"], (result.failure_vector for result in audit_results))
    Path(files["error_audit_table"]).write_text(_render_table(audit_results), encoding="utf-8")
    Path(files["report"]).write_text(_render_report(summary), encoding="utf-8")
    return files


def _failure_vector_dict(
    record: CrystalStructureRecord,
    oracle: FailureOracle,
    stability_mode: str,
) -> tuple[dict[str, Any], str | None]:
    try:
        structure = record.to_structure_like()
        structure.metadata["stability_mode"] = stability_mode
        vector = oracle.vectorize(structure)
        return vector.to_dict(), None
    except Exception as exc:
        vector = FailureVector(
            sample_id=str(record.candidate_id or "unknown"),
            structure_ref=record.structure_ref,
            f1_geometry=1.0,
            f2_chemistry=1.0,
            f3_stability=None,
            confidence=0.0,
            uncertainty=1.0,
            calibration_tier=0,
            is_valid=False,
            hard_failures=["oracle_error"],
            metadata={
                "composition": record.composition,
                "oracle_error_type": exc.__class__.__name__,
                "oracle_error_message": str(exc),
            },
        )
        return vector.to_dict(), f"{exc.__class__.__name__}: {exc}"


def _parse_status(record: CrystalStructureRecord) -> str:
    status = record.metadata.get("parse_status")
    if status:
        return str(status)
    if record.species and record.frac_coords and record.lattice_matrix:
        return "parsed_full_structure"
    if record.metadata.get("parse_error_message"):
        return "parse_error"
    if record.structure_ref and not (record.species and record.frac_coords and record.lattice_matrix):
        return "unparsed_cif"
    if record.metadata.get("partial_record"):
        return "partial_structure"
    return "partial_structure"


def _condition_for(
    record: CrystalStructureRecord,
    *,
    formula: str | None,
    spacegroup: int | None,
) -> dict[str, Any]:
    metadata = record.metadata
    raw_spacegroup = metadata.get("spacegroup_condition", spacegroup)
    generation = _generation_condition(metadata)
    return {
        "mode": metadata.get("condition_mode", "csp"),
        "formula": metadata.get("formula_condition") or formula or record.composition,
        "spacegroup": _optional_int(raw_spacegroup),
        "generation": generation,
    }


def _dpo_eligibility(
    *,
    record: CrystalStructureRecord,
    parse_status: str,
    condition: dict[str, Any],
    fiir_score: float | None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    raw_sequence_status, missing_sequence_fields = crystalformer_sequence_status(record.metadata)
    if not record.candidate_id:
        reasons.append("missing_candidate_id")
    if not condition.get("formula"):
        reasons.append("missing_condition")
    if raw_sequence_status == "missing":
        reasons.append("missing_raw_sequence")
    elif raw_sequence_status == "partial":
        reasons.append("partial_raw_sequence")
        if missing_sequence_fields:
            reasons.append("missing_sequence_fields:" + ",".join(missing_sequence_fields))
    if fiir_score is None:
        reasons.append("missing_comparable_fiir_score")
    if parse_status == "parse_error":
        reasons.append("parse_error")
    return not reasons, reasons


def _generation_condition(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return reproducibility fields that define the same generation condition."""

    fields = {
        "source_model": metadata.get("source_model"),
        "source_checkpoint": metadata.get("source_checkpoint"),
        "temperature": metadata.get("temperature"),
        "top_k": metadata.get("top_k"),
        "K": metadata.get("K"),
    }
    sampling = metadata.get("sampling_metadata")
    if isinstance(sampling, dict):
        for key in ("temperature", "sample_temperature", "sampling_temperature", "top_k", "K"):
            fields.setdefault(key, sampling.get(key))
            if fields.get(key) in (None, "") and sampling.get(key) not in (None, ""):
                fields[key] = sampling[key]
    return {key: value for key, value in fields.items() if value not in (None, "")}


def _f3_is_unknown(stability_mode: str, f3_value: float | None) -> bool:
    return stability_mode == F3_UNAVAILABLE_MODE or f3_value is None


def _pass_fail_label(value: float | None) -> str:
    if value is None:
        return "unknown"
    return "pass" if value < 0.1 else "fail"


def _fiir_score(f1: float | None, f2: float | None, f3: float | None) -> float | None:
    values = [value for value in (f1, f2, f3) if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _failure_reasons(
    vector_dict: dict[str, Any],
    parse_status: str,
    oracle_error: str | None,
) -> list[str]:
    reasons = list(vector_dict.get("hard_failures", []))
    if parse_status in {"unparsed_cif", "parse_error", "partial_structure"}:
        reasons.append(parse_status)
    if oracle_error:
        reasons.append("oracle_error")
    return sorted(set(str(reason) for reason in reasons if reason))


def _parse_error(metadata: dict[str, Any], oracle_error: str | None) -> str | None:
    if oracle_error:
        return oracle_error
    if metadata.get("parse_error_message"):
        return str(metadata["parse_error_message"])
    if metadata.get("parse_error_type"):
        return str(metadata["parse_error_type"])
    return None


def _raw_sequence_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    fields = metadata.get("raw_sequence_fields")
    if isinstance(fields, dict):
        return dict(fields)
    return {
        "g": metadata.get("raw_g"),
        "W": metadata.get("raw_W"),
        "A": metadata.get("raw_A"),
        "X": metadata.get("raw_X"),
        "L": metadata.get("raw_L"),
    }


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return int(float(str(value)))


def _rate(count: int, total: int) -> float:
    return 0.0 if total == 0 else round(count / total, 6)


def _duplicate_extra_count(values: Counter[Any]) -> int:
    return sum(count - 1 for count in values.values() if count > 1)


def _top_items(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"reason": reason, "count": count}
        for reason, count in counter.most_common(limit)
    ]


def _render_table(audit_results: Sequence[AuditCandidateResult]) -> str:
    lines = [
        "| candidate_id | composition | parse_status | raw_sequence_status | F1 | F2 | F3 | fiir_score | dpo_eligible |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in audit_results:
        lines.append(
            "| {candidate_id} | {composition} | {parse_status} | {raw_sequence_status} | "
            "{f1_label} | {f2_label} | {f3_label} | {fiir_score} | {dpo_eligible} |".format(
                candidate_id=result.candidate_id,
                composition=result.composition or "",
                parse_status=result.parse_status,
                raw_sequence_status=result.raw_sequence_status,
                f1_label=result.f1_label,
                f2_label=result.f2_label,
                f3_label=result.f3_label,
                fiir_score="" if result.fiir_score is None else result.fiir_score,
                dpo_eligible=result.dpo_eligible,
            )
        )
    lines.append("")
    return "\n".join(lines)


def _render_report(summary: AuditSummary) -> str:
    data = summary.to_dict()
    lines = [
        "# CrystalFormer Smoke Audit Report",
        "",
        "## Scope",
        "- This is a smoke audit for CrystalFormer outputs entering FIIR.",
        "- This is not DPO training and not stability validation.",
        "- No DFT, MLFF relaxation, Materials Project calls, or external API calls are run.",
        "- With `unavailable_without_offline_validation`, F3 is unknown/unavailable and no candidate is reported as stable.",
        "",
        "## Summary",
        f"- total_candidates: {data['total_candidates']}",
        f"- parsed_full_structure_count: {data['parsed_full_structure_count']}",
        f"- unparsed_cif_count: {data['unparsed_cif_count']}",
        f"- parse_error_count: {data['parse_error_count']}",
        f"- partial_sequence_count: {data['partial_sequence_count']}",
        f"- missing_raw_sequence_count: {data['missing_raw_sequence_count']}",
        f"- f1_fail_rate: {data['f1_fail_rate']}",
        f"- f2_fail_rate: {data['f2_fail_rate']}",
        f"- f3_unknown_rate: {data['f3_unknown_rate']}",
        f"- offline_validation_available_count: {data['offline_validation_available_count']}",
        f"- offline_validation_error_count: {data['offline_validation_error_count']}",
        f"- f3_validated_stable_count: {data['f3_validated_stable_count']}",
        f"- dpo_eligible_count: {data['dpo_eligible_count']}",
        f"- dpo_ineligible_count: {data['dpo_ineligible_count']}",
        "",
        "## Source Formats",
        f"- {data['source_format_breakdown']}",
        "",
        "## DPO Boundary",
        "- `dpo_eligible` only means the candidate has enough audit metadata for future pair construction.",
        "- Future DPO pairs must use candidates from the same formula and condition.",
        "- Without F3 validation, future preferences are limited to `geometry_chemistry_only`.",
        "",
    ]
    return "\n".join(lines)
