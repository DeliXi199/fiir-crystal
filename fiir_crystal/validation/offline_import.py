"""Import local offline validation results into CrystalFormer smoke audits.

The functions here only read local JSONL artifacts produced elsewhere. They do
not run DFT, MLIP, Materials Project, or any external validation workflow.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.io import read_jsonl, write_json


OFFLINE_VALIDATION_SOURCE = "offline_validation_imported"
STABILITY_AWARE_OFFLINE_VALIDATION = "stability_aware_offline_validation"


@dataclass(slots=True)
class OfflineValidationImportConfig:
    """Configuration for matching offline validation rows to audit candidates."""

    formula: str | None = None
    spacegroup: int | None = None
    require_same_generation_condition: bool = True
    stable_e_above_hull_threshold: float = 0.05


@dataclass(slots=True)
class OfflineValidationRecord:
    """Schema-first offline validation row."""

    candidate_id: str
    formula: str
    validation_source: str
    validation_status: str
    condition: dict[str, Any] = field(default_factory=dict)
    spacegroup: int | None = None
    is_stable: bool | None = None
    e_above_hull: float | None = None
    relaxed_structure_ref: str | None = None
    error_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "OfflineValidationRecord":
        missing = [
            field
            for field in ("candidate_id", "formula", "validation_source")
            if row.get(field) in (None, "")
        ]
        if missing:
            raise ValueError("missing_required_field:" + ",".join(missing))
        condition = dict(row.get("condition", {})) if isinstance(row.get("condition"), dict) else {}
        formula = str(row.get("formula") or condition.get("formula"))
        spacegroup = row.get("spacegroup", condition.get("spacegroup"))
        return cls(
            candidate_id=str(row["candidate_id"]),
            formula=formula,
            validation_source=str(row["validation_source"]),
            validation_status=str(row.get("validation_status", row.get("status", "unknown"))),
            condition=condition,
            spacegroup=_optional_int(spacegroup),
            is_stable=_optional_bool(row.get("is_stable")),
            e_above_hull=_optional_float(row.get("e_above_hull")),
            relaxed_structure_ref=(
                None if row.get("relaxed_structure_ref") is None else str(row["relaxed_structure_ref"])
            ),
            error_reason=(
                None
                if row.get("error_reason", row.get("error_message")) is None
                else str(row.get("error_reason", row.get("error_message")))
            ),
            metadata=dict(row.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "formula": self.formula,
            "spacegroup": self.spacegroup,
            "condition": dict(self.condition),
            "validation_source": self.validation_source,
            "validation_status": self.validation_status,
            "is_stable": self.is_stable,
            "e_above_hull": self.e_above_hull,
            "relaxed_structure_ref": self.relaxed_structure_ref,
            "error_reason": self.error_reason,
            "metadata": dict(self.metadata),
        }

    @property
    def succeeded(self) -> bool:
        return (
            self.validation_status.lower() in {"completed", "success", "succeeded", "validated"}
            and not self.error_reason
            and (self.is_stable is not None or self.e_above_hull is not None)
        )


@dataclass(slots=True)
class OfflineValidationImportSummary:
    """Summary of an offline validation join."""

    audit_candidate_count: int
    validation_record_count: int
    matched_count: int
    f3_available_count: int
    validation_error_count: int
    skipped_count: int
    skip_reasons: dict[str, int]
    validation_source_breakdown: dict[str, int]
    matched_candidate_ids: list[str] = field(default_factory=list)
    f3_available_candidate_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_candidate_count": self.audit_candidate_count,
            "validation_record_count": self.validation_record_count,
            "matched_count": self.matched_count,
            "f3_available_count": self.f3_available_count,
            "validation_error_count": self.validation_error_count,
            "skipped_count": self.skipped_count,
            "skip_reasons": dict(self.skip_reasons),
            "validation_source_breakdown": dict(self.validation_source_breakdown),
            "matched_candidate_ids": list(self.matched_candidate_ids),
            "f3_available_candidate_ids": list(self.f3_available_candidate_ids),
        }


def read_offline_validation_jsonl(path: str | Path) -> list[OfflineValidationRecord]:
    """Read local offline validation JSONL rows."""

    records = []
    for row in read_jsonl(path):
        records.append(OfflineValidationRecord.from_dict(row))
    return records


def import_offline_validation_to_audit_rows(
    audit_rows: Sequence[dict[str, Any]],
    validation_records: Sequence[OfflineValidationRecord],
    config: OfflineValidationImportConfig | None = None,
) -> tuple[list[dict[str, Any]], OfflineValidationImportSummary]:
    """Return audit rows with matched offline validation evidence applied."""

    cfg = config or OfflineValidationImportConfig()
    rows = [deepcopy(row) for row in audit_rows]
    for row in rows:
        _ensure_validation_defaults(row)

    audit_by_id = {str(row.get("candidate_id")): row for row in rows if row.get("candidate_id")}
    skip_reasons: Counter[str] = Counter()
    source_breakdown: Counter[str] = Counter()
    matched_candidate_ids: list[str] = []
    f3_available_candidate_ids: list[str] = []
    matched_count = 0
    f3_available_count = 0
    validation_error_count = 0
    seen_validation_ids: set[str] = set()

    for record in validation_records:
        source_breakdown[record.validation_source] += 1
        if record.candidate_id in seen_validation_ids:
            skip_reasons["duplicate_validation_candidate_id"] += 1
            continue
        seen_validation_ids.add(record.candidate_id)
        audit_row = audit_by_id.get(record.candidate_id)
        if audit_row is None:
            skip_reasons["candidate_not_found"] += 1
            continue
        mismatch = _condition_mismatch_reason(audit_row, record, cfg)
        if mismatch:
            skip_reasons[mismatch] += 1
            continue

        matched_count += 1
        matched_candidate_ids.append(record.candidate_id)
        if not record.succeeded:
            validation_error_count += 1
            skip_reasons["validation_error"] += 1
            _apply_validation_error(audit_row, record)
            continue

        score, is_stable = _stability_score(record, cfg)
        _apply_validation_success(audit_row, record, score, is_stable)
        f3_available_count += 1
        f3_available_candidate_ids.append(record.candidate_id)

    summary = OfflineValidationImportSummary(
        audit_candidate_count=len(rows),
        validation_record_count=len(validation_records),
        matched_count=matched_count,
        f3_available_count=f3_available_count,
        validation_error_count=validation_error_count,
        skipped_count=sum(skip_reasons.values()),
        skip_reasons=dict(sorted(skip_reasons.items())),
        validation_source_breakdown=dict(sorted(source_breakdown.items())),
        matched_candidate_ids=matched_candidate_ids,
        f3_available_candidate_ids=f3_available_candidate_ids,
    )
    return rows, summary


def write_offline_validation_import_outputs(
    output_dir: str | Path,
    summary: OfflineValidationImportSummary,
) -> dict[str, str]:
    """Write a standalone validation import check summary."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "json": str(destination / "validation_import_summary.json"),
        "markdown": str(destination / "report.md"),
    }
    write_json(files["json"], summary)
    Path(files["markdown"]).write_text(render_offline_validation_import_report(summary), encoding="utf-8")
    return files


def render_offline_validation_import_report(summary: OfflineValidationImportSummary) -> str:
    data = summary.to_dict()
    lines = [
        "# Offline Validation Import Check",
        "",
        "## Boundary",
        "- This check reads local validation results only.",
        "- It does not run DFT, MLIP, Materials Project, or any external API.",
        "",
        "## Summary",
        f"- audit_candidate_count: {data['audit_candidate_count']}",
        f"- validation_record_count: {data['validation_record_count']}",
        f"- matched_count: {data['matched_count']}",
        f"- f3_available_count: {data['f3_available_count']}",
        f"- validation_error_count: {data['validation_error_count']}",
        f"- skipped_count: {data['skipped_count']}",
        f"- skip_reasons: {data['skip_reasons']}",
        f"- validation_source_breakdown: {data['validation_source_breakdown']}",
        "",
    ]
    return "\n".join(lines)


def _ensure_validation_defaults(row: dict[str, Any]) -> None:
    row.setdefault("offline_validation", None)
    row.setdefault("validation_status", "not_provided")
    row.setdefault("f3_source", "unavailable_without_offline_validation")
    row.setdefault("f3_validation_available", False)


def _condition_mismatch_reason(
    audit_row: dict[str, Any],
    record: OfflineValidationRecord,
    cfg: OfflineValidationImportConfig,
) -> str | None:
    audit_condition = dict(audit_row.get("condition", {}))
    audit_formula = audit_condition.get("formula") or audit_row.get("composition")
    expected_formula = cfg.formula or audit_formula
    if record.formula != expected_formula or record.formula != audit_formula:
        return "formula_mismatch"

    audit_spacegroup = _optional_int(audit_condition.get("spacegroup"))
    record_spacegroup = record.spacegroup
    if cfg.spacegroup is not None and record_spacegroup != cfg.spacegroup:
        return "spacegroup_mismatch"
    if record_spacegroup is not None and audit_spacegroup is not None and record_spacegroup != audit_spacegroup:
        return "spacegroup_mismatch"

    if cfg.require_same_generation_condition:
        audit_generation = _normalized_generation(audit_condition.get("generation"))
        validation_generation = _normalized_generation(record.condition.get("generation"))
        if audit_generation != validation_generation:
            return "condition_mismatch"
    return None


def _apply_validation_error(row: dict[str, Any], record: OfflineValidationRecord) -> None:
    row["offline_validation"] = record.to_dict()
    row["validation_status"] = "validation_error"
    row["f3_source"] = "offline_validation_error"
    row["f3_validation_available"] = False
    row["f3_label"] = "unknown"
    row["preference_type"] = "geometry_chemistry_only" if row.get("dpo_eligible") else None
    evidence = dict(row.get("evidence", {}))
    evidence["offline_validation"] = record.to_dict()
    evidence["f3_status"] = "validation_error"
    row["evidence"] = evidence


def _apply_validation_success(
    row: dict[str, Any],
    record: OfflineValidationRecord,
    score: float,
    is_stable: bool,
) -> None:
    validation = record.to_dict()
    validation["is_stable"] = is_stable
    row["offline_validation"] = validation
    row["validation_status"] = "validated_success"
    row["f3_source"] = OFFLINE_VALIDATION_SOURCE
    row["f3_validation_available"] = True
    row["f3_label"] = "pass" if score < 0.1 else "fail"
    row["preference_type"] = STABILITY_AWARE_OFFLINE_VALIDATION if row.get("dpo_eligible") else None

    failure_vector = dict(row.get("failure_vector", {}))
    failure_vector["f3_stability"] = score
    metadata = dict(failure_vector.get("metadata", {}))
    metadata["f3_status"] = OFFLINE_VALIDATION_SOURCE
    metadata["stability"] = {
        "source": record.validation_source,
        "validation_status": record.validation_status,
        "is_stable": is_stable,
        "e_above_hull": record.e_above_hull,
        "relaxed_structure_ref": record.relaxed_structure_ref,
    }
    failure_vector["metadata"] = metadata
    row["failure_vector"] = failure_vector

    evidence = dict(row.get("evidence", {}))
    evidence["offline_validation"] = validation
    evidence["f3_status"] = OFFLINE_VALIDATION_SOURCE
    row["evidence"] = evidence

    f1 = _optional_float(failure_vector.get("f1_geometry"))
    f2 = _optional_float(failure_vector.get("f2_chemistry"))
    row["fiir_score"] = _fiir_score(f1, f2, score)
    row["ranking_score"] = None if row["fiir_score"] is None else round(1.0 - row["fiir_score"], 6)


def _stability_score(
    record: OfflineValidationRecord,
    cfg: OfflineValidationImportConfig,
) -> tuple[float, bool]:
    is_stable = record.is_stable
    if is_stable is None and record.e_above_hull is not None:
        is_stable = record.e_above_hull <= cfg.stable_e_above_hull_threshold
    is_stable = bool(is_stable)
    if is_stable:
        return 0.0, True
    if record.e_above_hull is None:
        return 1.0, False
    return max(0.3, min(1.0, float(record.e_above_hull))), False


def _normalized_generation(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(value[key])
        for key in sorted(value)
        if value[key] not in (None, "")
    }


def _fiir_score(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 6)


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return int(float(str(value)))


def _optional_bool(value: Any) -> bool | None:
    if value in (None, "", "null", "None", "none"):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "yes", "1", "stable"}:
            return True
        if lowered in {"false", "no", "0", "unstable"}:
            return False
    return bool(value)
