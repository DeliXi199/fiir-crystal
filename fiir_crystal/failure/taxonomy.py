"""Core failure taxonomy dataclasses.

The objects in this module are deliberately lightweight. They describe data
contracts and do not run MLIP, DFT, database queries, or heavy structure
analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class FailureAxis(str, Enum):
    """Supported FIIR failure axes."""

    F1_GEOMETRY = "F1_GEOMETRY"
    F2_CHEMISTRY = "F2_CHEMISTRY"
    F3_STABILITY = "F3_STABILITY"


class FailureSeverity(str, Enum):
    """Severity buckets for a single failure score."""

    PASS = "pass"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    UNKNOWN = "unknown"


class CalibrationTier(IntEnum):
    """Calibration tier used to propagate label confidence."""

    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


class TierSource(str, Enum):
    """Provenance for a calibration tier."""

    INVALID = "invalid"
    MOCK_ONLY = "mock_only"
    RULE_BASED = "rule_based"
    DFT_PROVIDED = "dft_provided"
    MULTI_ADAPTER_AGREEMENT = "multi_adapter_agreement"
    SINGLE_ADAPTER = "single_adapter"
    RULES_ONLY = "rules_only"
    DISAGREEMENT = "disagreement"
    UNKNOWN = "unknown"


def tier_weight(tier: int | CalibrationTier) -> float:
    """Return the default confidence weight for a calibration tier."""

    return {
        0: 0.0,
        1: 0.5,
        2: 0.7,
        3: 0.85,
        4: 1.0,
    }.get(int(tier), 0.0)


@dataclass(slots=True)
class CandidateRecord:
    """Minimal candidate structure record consumed by FIIR modules."""

    sample_id: str
    structure: Any
    structure_ref: str | None = None
    source_model: str | None = None
    round_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PreFilterResult:
    """Decision from a lightweight pre-filter."""

    is_valid: bool
    reject_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FailureScore:
    """Auditable score for one failure axis."""

    axis: FailureAxis
    value: float | None
    unit: str
    severity: FailureSeverity = FailureSeverity.UNKNOWN
    confidence: float = 0.0
    uncertainty: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None


@dataclass(slots=True)
class FailureVector:
    """Compact F1/F2/F3 vector used by mock demos and lightweight adapters."""

    sample_id: str
    f1_geometry: float
    f2_chemistry: float
    f3_stability: float | None
    confidence: float = 0.0
    uncertainty: float = 0.0
    calibration_tier: int = int(CalibrationTier.TIER_4)
    is_valid: bool = True
    hard_failures: list[str] = field(default_factory=list)
    structure_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        """Alias used by discovery code."""

        return self.sample_id

    @property
    def is_stable(self) -> bool | None:
        """Return the default FIIR stability decision when F3 is available."""

        if self.f3_stability is None:
            return None
        return self.f3_stability < 0.1

    def to_dict(self) -> dict[str, Any]:
        """Serialize the failure vector to a JSON-compatible dict."""

        return {
            "sample_id": self.sample_id,
            "candidate_id": self.candidate_id,
            "structure_ref": self.structure_ref,
            "f1_geometry": self.f1_geometry,
            "f2_chemistry": self.f2_chemistry,
            "f3_stability": self.f3_stability,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "calibration_tier": self.calibration_tier,
            "is_valid": self.is_valid,
            "hard_failures": list(self.hard_failures),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureVector":
        """Deserialize a failure vector from a JSON-compatible dict."""

        sample_id = data.get("sample_id", data.get("candidate_id"))
        if not sample_id:
            raise ValueError("FailureVector requires sample_id or candidate_id.")
        return cls(
            sample_id=str(sample_id),
            structure_ref=data.get("structure_ref"),
            f1_geometry=float(data["f1_geometry"]),
            f2_chemistry=float(data["f2_chemistry"]),
            f3_stability=None if data.get("f3_stability") is None else float(data["f3_stability"]),
            confidence=float(data.get("confidence", 0.0)),
            uncertainty=float(data.get("uncertainty", 0.0)),
            calibration_tier=int(data.get("calibration_tier", 0)),
            is_valid=bool(data.get("is_valid", True)),
            hard_failures=list(data.get("hard_failures", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class FailureLabel:
    """Complete FIIR failure label for a candidate structure."""

    sample_id: str
    structure_ref: str
    f1_geometry: float
    f2_chemistry: float
    f3_stability: float | None
    f3_normalized: float | None = None
    axis_scores: list[FailureScore] = field(default_factory=list)
    uncertainty: float = 0.0
    confidence: float = 0.0
    calibration_tier: int = int(CalibrationTier.TIER_4)
    tier_source: str = TierSource.UNKNOWN.value
    pre_filtered: bool = False
    reject_reason: str | None = None
    is_stable: bool | None = None
    is_near_miss: bool = False
    is_moderate: bool = False
    is_catastrophic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.is_stable is None and self.f3_stability is not None:
            self.is_stable = self.f3_stability < 0.1
        if self.f3_stability is not None:
            self.is_near_miss = 0.1 <= self.f3_stability <= 0.2
            self.is_moderate = 0.2 < self.f3_stability <= 0.5
            self.is_catastrophic = self.f3_stability > 0.5 or self.pre_filtered
        elif self.pre_filtered:
            self.is_catastrophic = True


@dataclass(slots=True)
class FailureLabelBatch:
    """Batch of failure labels plus summary metadata."""

    labels: list[FailureLabel]
    summary: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
