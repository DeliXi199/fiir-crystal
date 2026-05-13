"""Import externally computed F4 novelty/leakage audit evidence.

This module only consumes local JSONL artifacts produced by an external audit
workflow. It does not run StructureMatcher, pymatgen, database queries, or any
external API.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median
from typing import Any, Sequence

from fiir_crystal.io import read_jsonl, write_json, write_jsonl


F4_AUDIT_SCHEMA_VERSION = "f4-audit-v1"
F4_IMPORTED_SOURCE = "f4_novelty_audit_imported"
F4_MISSING_SOURCE = "unavailable_without_f4_novelty_audit"


class F4NoveltyAuditError(ValueError):
    """Raised when F4 audit rows cannot be imported safely."""


@dataclass(slots=True)
class F4NoveltyAuditRecord:
    """Schema-first external F4 audit row.

    `f4_novelty_leakage` is a leakage or near-duplicate risk score in [0, 1].
    Lower values are better; higher values indicate greater leakage risk.
    """

    candidate_id: str
    f4_novelty_leakage: float
    reference_source: str
    match_type: str
    confidence: float
    nearest_reference_id: str | None = None
    fingerprint_distance: float | None = None
    schema_version: str = F4_AUDIT_SCHEMA_VERSION
    reference_pool_id: str | None = None
    audit_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "F4NoveltyAuditRecord":
        missing = [
            field
            for field in (
                "candidate_id",
                "f4_novelty_leakage",
                "reference_source",
                "match_type",
                "confidence",
            )
            if row.get(field) in (None, "")
        ]
        if missing:
            raise F4NoveltyAuditError("missing_required_field:" + ",".join(missing))

        fingerprint_distance = _optional_float(row.get("fingerprint_distance"))
        if fingerprint_distance is not None and fingerprint_distance < 0:
            raise F4NoveltyAuditError("fingerprint_distance_out_of_range")

        metadata = row.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise F4NoveltyAuditError("metadata_must_be_object")

        return cls(
            candidate_id=str(row["candidate_id"]),
            f4_novelty_leakage=_bounded_float(row["f4_novelty_leakage"], "f4_novelty_leakage"),
            reference_source=str(row["reference_source"]),
            match_type=str(row["match_type"]),
            confidence=_bounded_float(row["confidence"], "confidence"),
            nearest_reference_id=(
                None if row.get("nearest_reference_id") in (None, "") else str(row["nearest_reference_id"])
            ),
            fingerprint_distance=fingerprint_distance,
            schema_version=str(row.get("schema_version", F4_AUDIT_SCHEMA_VERSION)),
            reference_pool_id=None if row.get("reference_pool_id") in (None, "") else str(row["reference_pool_id"]),
            audit_run_id=None if row.get("audit_run_id") in (None, "") else str(row["audit_run_id"]),
            metadata=dict(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "f4_novelty_leakage": self.f4_novelty_leakage,
            "nearest_reference_id": self.nearest_reference_id,
            "reference_source": self.reference_source,
            "match_type": self.match_type,
            "fingerprint_distance": self.fingerprint_distance,
            "confidence": self.confidence,
            "reference_pool_id": self.reference_pool_id,
            "audit_run_id": self.audit_run_id,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class F4NoveltyImportConfig:
    """Configuration for joining external F4 rows to candidate rows."""

    allow_duplicate_results: bool = False
    high_leakage_threshold: float = 0.8


@dataclass(slots=True)
class F4NoveltyImportSummary:
    """Summary of an F4 novelty/leakage join."""

    candidate_count: int
    f4_record_count: int
    matched_count: int
    missing_count: int
    orphan_count: int
    duplicate_result_count: int
    high_leakage_count: int
    score_stats: dict[str, Any]
    score_bins: dict[str, int]
    reference_source_breakdown: dict[str, int]
    match_type_breakdown: dict[str, int]
    matched_candidate_ids: list[str] = field(default_factory=list)
    missing_candidate_ids: list[str] = field(default_factory=list)
    orphan_candidate_ids: list[str] = field(default_factory=list)
    high_leakage_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "f4_record_count": self.f4_record_count,
            "matched_count": self.matched_count,
            "missing_count": self.missing_count,
            "orphan_count": self.orphan_count,
            "duplicate_result_count": self.duplicate_result_count,
            "high_leakage_count": self.high_leakage_count,
            "score_stats": dict(self.score_stats),
            "score_bins": dict(self.score_bins),
            "reference_source_breakdown": dict(self.reference_source_breakdown),
            "match_type_breakdown": dict(self.match_type_breakdown),
            "matched_candidate_ids": list(self.matched_candidate_ids),
            "missing_candidate_ids": list(self.missing_candidate_ids),
            "orphan_candidate_ids": list(self.orphan_candidate_ids),
            "high_leakage_candidates": [dict(row) for row in self.high_leakage_candidates],
        }


def read_f4_novelty_audit_jsonl(path: str | Path) -> list[F4NoveltyAuditRecord]:
    """Read local external F4 audit JSONL rows."""

    return [F4NoveltyAuditRecord.from_dict(row) for row in read_jsonl(path)]


def import_f4_novelty_audit_to_candidates(
    candidate_rows: Sequence[dict[str, Any]],
    f4_records: Sequence[F4NoveltyAuditRecord],
    config: F4NoveltyImportConfig | None = None,
) -> tuple[list[dict[str, Any]], F4NoveltyImportSummary]:
    """Return candidate rows annotated with imported F4 evidence."""

    cfg = config or F4NoveltyImportConfig()
    rows = [deepcopy(row) for row in candidate_rows]
    candidate_ids: list[str] = []
    for index, row in enumerate(rows, start=1):
        if row.get("candidate_id") in (None, ""):
            raise F4NoveltyAuditError(f"candidate_missing_candidate_id:row_{index}")
        candidate_ids.append(str(row["candidate_id"]))
    duplicate_candidate_ids = sorted(_duplicates(candidate_ids))
    if duplicate_candidate_ids:
        raise F4NoveltyAuditError("duplicate_candidate_id:" + ",".join(duplicate_candidate_ids))

    candidate_id_set = set(candidate_ids)
    f4_by_id: dict[str, F4NoveltyAuditRecord] = {}
    duplicate_result_count = 0
    for record in f4_records:
        if record.candidate_id in f4_by_id:
            duplicate_result_count += 1
            if not cfg.allow_duplicate_results:
                raise F4NoveltyAuditError(f"duplicate_f4_candidate_id:{record.candidate_id}")
            continue
        f4_by_id[record.candidate_id] = record

    orphan_ids = sorted(set(f4_by_id) - candidate_id_set)
    matched_candidate_ids: list[str] = []
    missing_candidate_ids: list[str] = []
    matched_records: list[F4NoveltyAuditRecord] = []

    for row in rows:
        _ensure_f4_defaults(row)
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            missing_candidate_ids.append("")
            continue
        record = f4_by_id.get(str(candidate_id))
        if record is None:
            missing_candidate_ids.append(str(candidate_id))
            continue
        _apply_f4_record(row, record)
        matched_candidate_ids.append(record.candidate_id)
        matched_records.append(record)

    scores = [record.f4_novelty_leakage for record in matched_records]
    high_leakage_candidates = [
        {
            "candidate_id": record.candidate_id,
            "f4_novelty_leakage": record.f4_novelty_leakage,
            "nearest_reference_id": record.nearest_reference_id,
            "reference_source": record.reference_source,
        }
        for record in sorted(matched_records, key=lambda item: item.f4_novelty_leakage, reverse=True)
        if record.f4_novelty_leakage >= cfg.high_leakage_threshold
    ][:10]

    summary = F4NoveltyImportSummary(
        candidate_count=len(rows),
        f4_record_count=len(f4_records),
        matched_count=len(matched_records),
        missing_count=len(missing_candidate_ids),
        orphan_count=len(orphan_ids),
        duplicate_result_count=duplicate_result_count,
        high_leakage_count=sum(score >= cfg.high_leakage_threshold for score in scores),
        score_stats=_score_stats(scores),
        score_bins=_score_bins(scores),
        reference_source_breakdown=dict(sorted(Counter(record.reference_source for record in matched_records).items())),
        match_type_breakdown=dict(sorted(Counter(record.match_type for record in matched_records).items())),
        matched_candidate_ids=matched_candidate_ids,
        missing_candidate_ids=missing_candidate_ids,
        orphan_candidate_ids=orphan_ids,
        high_leakage_candidates=high_leakage_candidates,
    )
    return rows, summary


def write_f4_novelty_import_outputs(
    output_dir: str | Path,
    candidate_rows: Sequence[dict[str, Any]],
    summary: F4NoveltyImportSummary | dict[str, Any],
) -> dict[str, str]:
    """Write imported candidates, JSON summary, and Markdown report."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "candidates_with_f4": str(destination / "candidates_with_f4.jsonl"),
        "summary": str(destination / "f4_import_summary.json"),
        "report": str(destination / "f4_import_report.md"),
    }
    summary_data = summary.to_dict() if hasattr(summary, "to_dict") else dict(summary)
    summary_data.setdefault("output_files", files)
    write_jsonl(files["candidates_with_f4"], candidate_rows)
    write_json(files["summary"], summary_data)
    Path(files["report"]).write_text(render_f4_novelty_import_report(summary_data), encoding="utf-8")
    return files


def render_f4_novelty_import_report(summary: F4NoveltyImportSummary | dict[str, Any]) -> str:
    data = summary.to_dict() if hasattr(summary, "to_dict") else dict(summary)
    lines = [
        "# F4 Novelty Leakage Audit Import",
        "",
        "## Boundary",
        "- Reads local candidate and external F4 audit JSONL files only.",
        "- Does not run StructureMatcher, pymatgen, database queries, downloads, or external APIs.",
        "- `f4_novelty_leakage` is a leakage or near-duplicate risk score in `[0, 1]`; lower is better.",
        "",
        "## Summary",
        f"- candidate_count: {data['candidate_count']}",
        f"- f4_record_count: {data['f4_record_count']}",
        f"- matched_count: {data['matched_count']}",
        f"- missing_count: {data['missing_count']}",
        f"- orphan_count: {data['orphan_count']}",
        f"- duplicate_result_count: {data['duplicate_result_count']}",
        f"- high_leakage_count: {data['high_leakage_count']}",
        f"- score_stats: {data['score_stats']}",
        f"- score_bins: {data['score_bins']}",
        f"- reference_source_breakdown: {data['reference_source_breakdown']}",
        f"- match_type_breakdown: {data['match_type_breakdown']}",
        "",
        "## Highest Leakage Risk Candidates",
    ]
    high_leakage = data.get("high_leakage_candidates", [])
    if high_leakage:
        for item in high_leakage:
            lines.append(
                "- "
                f"{item['candidate_id']}: "
                f"f4_novelty_leakage={item['f4_novelty_leakage']}, "
                f"nearest_reference_id={item.get('nearest_reference_id')}, "
                f"reference_source={item.get('reference_source')}"
            )
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _ensure_f4_defaults(row: dict[str, Any]) -> None:
    row["f4_novelty_audit"] = None
    row["f4_status"] = "missing"
    row["f4_source"] = F4_MISSING_SOURCE
    row["f4_novelty_available"] = False
    row["f4_novelty_leakage"] = None


def _apply_f4_record(row: dict[str, Any], record: F4NoveltyAuditRecord) -> None:
    audit = record.to_dict()
    row["f4_novelty_audit"] = audit
    row["f4_status"] = "imported"
    row["f4_source"] = F4_IMPORTED_SOURCE
    row["f4_novelty_available"] = True
    row["f4_novelty_leakage"] = record.f4_novelty_leakage
    row["f4_leakage_risk_label"] = _risk_label(record.f4_novelty_leakage)

    failure_vector = dict(row.get("failure_vector", {}))
    failure_vector["f4_novelty_leakage"] = record.f4_novelty_leakage
    metadata = dict(failure_vector.get("metadata", {}))
    metadata["f4_status"] = F4_IMPORTED_SOURCE
    metadata["f4_novelty_audit"] = audit
    failure_vector["metadata"] = metadata
    row["failure_vector"] = failure_vector

    evidence = dict(row.get("evidence", {}))
    evidence["f4_status"] = F4_IMPORTED_SOURCE
    evidence["f4_novelty_audit"] = audit
    row["evidence"] = evidence


def _score_stats(scores: Sequence[float]) -> dict[str, Any]:
    if not scores:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(scores),
        "min": round(min(scores), 6),
        "median": round(median(scores), 6),
        "mean": round(mean(scores), 6),
        "max": round(max(scores), 6),
    }


def _score_bins(scores: Sequence[float]) -> dict[str, int]:
    bins = {
        "0.00-0.20": 0,
        "0.20-0.50": 0,
        "0.50-0.80": 0,
        "0.80-1.00": 0,
    }
    for score in scores:
        if score < 0.2:
            bins["0.00-0.20"] += 1
        elif score < 0.5:
            bins["0.20-0.50"] += 1
        elif score < 0.8:
            bins["0.50-0.80"] += 1
        else:
            bins["0.80-1.00"] += 1
    return bins


def _risk_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.2:
        return "low"
    return "very_low"


def _duplicates(values: Sequence[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _bounded_float(value: Any, field_name: str) -> float:
    parsed = float(value)
    if parsed < 0.0 or parsed > 1.0:
        raise F4NoveltyAuditError(f"{field_name}_out_of_range")
    return parsed


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return float(value)
