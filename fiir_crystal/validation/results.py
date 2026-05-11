"""Offline validation result records.

This module imports validation results that were produced elsewhere. It never
submits MLIP, DFT, database, or API jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.io import read_jsonl, write_jsonl


@dataclass(slots=True)
class ValidationResult:
    """Offline validation result joined by `candidate_id`."""

    candidate_id: str
    validation_source: str
    status: str
    validated: bool = False
    is_stable: bool | None = None
    e_above_hull: float | None = None
    band_gap: float | None = None
    relaxed: bool | None = None
    novelty_label: str | None = None
    synthesizability_score: float | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL output."""

        return {
            "candidate_id": self.candidate_id,
            "validation_source": self.validation_source,
            "status": self.status,
            "validated": self.validated,
            "is_stable": self.is_stable,
            "e_above_hull": self.e_above_hull,
            "band_gap": self.band_gap,
            "relaxed": self.relaxed,
            "novelty_label": self.novelty_label,
            "synthesizability_score": self.synthesizability_score,
            "error_message": self.error_message,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationResult":
        """Deserialize a validation result from a JSON object."""

        if not data.get("candidate_id"):
            raise ValueError("ValidationResult requires candidate_id")
        return cls(
            candidate_id=str(data["candidate_id"]),
            validation_source=str(data.get("validation_source", "offline_mock")),
            status=str(data.get("status", "unknown")),
            validated=bool(data.get("validated", False)),
            is_stable=_optional_bool(data.get("is_stable")),
            e_above_hull=_optional_float(data.get("e_above_hull")),
            band_gap=_optional_float(data.get("band_gap")),
            relaxed=_optional_bool(data.get("relaxed")),
            novelty_label=None if data.get("novelty_label") is None else str(data["novelty_label"]),
            synthesizability_score=_optional_float(data.get("synthesizability_score")),
            error_message=None if data.get("error_message") is None else str(data["error_message"]),
            metadata=dict(data.get("metadata", {})),
        )

    @property
    def succeeded(self) -> bool:
        """Whether the offline validation completed successfully."""

        return self.validated and self.status.lower() not in {"failed", "error"} and not self.error_message

    @property
    def novelty_passed(self) -> bool:
        """Whether novelty metadata represents a pass."""

        if self.novelty_label is None:
            return False
        return self.novelty_label.lower() in {"novel", "pass", "passed", "new", "true"}


def read_validation_results_jsonl(path: str | Path) -> list[ValidationResult]:
    """Read offline validation results from JSONL."""

    return [ValidationResult.from_dict(row) for row in read_jsonl(path)]


def write_validation_results_jsonl(path: str | Path, results: Sequence[ValidationResult]) -> None:
    """Write offline validation results to JSONL."""

    write_jsonl(path, results)


def validation_by_candidate_id(results: Sequence[ValidationResult]) -> dict[str, ValidationResult]:
    """Return the latest validation result for each candidate id."""

    index: dict[str, ValidationResult] = {}
    for result in results:
        index[result.candidate_id] = result
    return index


def join_validation_to_rankings(
    ranked_candidates: Sequence[Any],
    validation_results: Sequence[ValidationResult],
) -> list[dict[str, Any]]:
    """Join validation results to ranking rows by candidate id."""

    validation_index = validation_by_candidate_id(validation_results)
    rows: list[dict[str, Any]] = []
    for ranked in ranked_candidates:
        candidate_id = str(getattr(ranked, "candidate_id", ""))
        ranked_row = ranked.to_dict() if hasattr(ranked, "to_dict") else dict(ranked)
        result = validation_index.get(candidate_id)
        ranked_row["validation_result"] = result.to_dict() if result else None
        rows.append(ranked_row)
    return rows


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
