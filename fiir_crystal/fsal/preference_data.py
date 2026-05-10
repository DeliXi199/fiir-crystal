"""Dataclasses for FSAL preference data."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fiir_crystal.failure import FailureLabel, FailureVector


class PreferenceAxis(str, Enum):
    """Preference pair axis."""

    F1_GEOMETRY = "F1_GEOMETRY"
    F2_CHEMISTRY = "F2_CHEMISTRY"
    F3_STABILITY = "F3_STABILITY"
    MIXED = "MIXED"


class FailureBucket(str, Enum):
    """Failure severity bucket used for preference sampling."""

    NEAR_MISS = "near_miss"
    MODERATE = "moderate"
    CATASTROPHIC = "catastrophic"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class LabeledCandidate:
    """Candidate plus the failure label needed for pair mining."""

    sample_id: str
    structure_ref: str
    failure_label: FailureLabel
    chemical_bucket: str
    atom_count: int
    space_group: int | None = None
    prototype: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    failure_vector: FailureVector | None = None


@dataclass(slots=True)
class MatchedPairConfig:
    """Configuration for matched axis-aligned pair mining."""

    main_axis_threshold: float = 0.3
    other_axis_threshold: float = 0.15
    atom_count_tolerance: float = 0.2
    require_prototype_match: bool = True
    require_space_group_match: bool = False
    require_composition_family_match: bool = False
    min_structure_match_score: float = 0.0
    min_pair_quality: float = 0.3
    max_pairs_per_axis: int | None = None
    tier_weights: dict[int, float] = field(
        default_factory=lambda: {1: 1.0, 2: 0.8, 3: 0.5, 4: 0.2}
    )
    failure_bucket_quota: dict[str, float] = field(
        default_factory=lambda: {"near": 0.6, "moderate": 0.3, "catastrophic": 0.1}
    )
    axis_batch_ratio: dict[str, float] = field(
        default_factory=lambda: {"F1": 0.3, "F2": 0.3, "F3": 0.3, "mixed": 0.1}
    )


@dataclass(slots=True)
class PreferencePair:
    """Winner/loser pair for DPO-style alignment."""

    pair_id: str
    winner_id: str
    loser_id: str
    axis: PreferenceAxis
    winner_failure: dict[str, float | None] = field(default_factory=dict)
    loser_failure: dict[str, float | None] = field(default_factory=dict)
    main_axis_gap: float = 0.0
    other_axis_delta: dict[str, float] = field(default_factory=dict)
    other_axis_similarity: float = 0.0
    structure_match_score: float = 0.0
    label_confidence: float = 0.0
    pair_quality: float = 0.0
    margin: float = 0.0
    weight: float = 0.0
    failure_bucket: FailureBucket = FailureBucket.UNKNOWN
    match_metadata: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        """Alias used by the mock demo output."""

        return self.label_confidence

    def to_dict(self) -> dict[str, Any]:
        """Serialize the preference pair to a JSON-compatible dict."""

        return {
            "pair_id": self.pair_id,
            "winner_id": self.winner_id,
            "loser_id": self.loser_id,
            "axis": self.axis.value,
            "winner_failure": dict(self.winner_failure),
            "loser_failure": dict(self.loser_failure),
            "main_axis_gap": self.main_axis_gap,
            "other_axis_delta": dict(self.other_axis_delta),
            "other_axis_similarity": self.other_axis_similarity,
            "structure_match_score": self.structure_match_score,
            "label_confidence": self.label_confidence,
            "confidence": self.confidence,
            "pair_quality": self.pair_quality,
            "margin": self.margin,
            "weight": self.weight,
            "failure_bucket": self.failure_bucket.value,
            "match_metadata": dict(self.match_metadata),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PreferencePair":
        """Deserialize a preference pair from a JSON-compatible dict."""

        return cls(
            pair_id=str(data["pair_id"]),
            winner_id=str(data["winner_id"]),
            loser_id=str(data["loser_id"]),
            axis=PreferenceAxis(data["axis"]),
            winner_failure=dict(data.get("winner_failure", {})),
            loser_failure=dict(data.get("loser_failure", {})),
            main_axis_gap=float(data.get("main_axis_gap", 0.0)),
            other_axis_delta=dict(data.get("other_axis_delta", {})),
            other_axis_similarity=float(data.get("other_axis_similarity", 0.0)),
            structure_match_score=float(data.get("structure_match_score", 0.0)),
            label_confidence=float(data.get("label_confidence", data.get("confidence", 0.0))),
            pair_quality=float(data.get("pair_quality", 0.0)),
            margin=float(data.get("margin", 0.0)),
            weight=float(data.get("weight", data.get("label_confidence", data.get("confidence", 0.0)))),
            failure_bucket=FailureBucket(data.get("failure_bucket", FailureBucket.UNKNOWN.value)),
            match_metadata=dict(data.get("match_metadata", {})),
            reason=str(data.get("reason", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class PreferenceDataset:
    """Collection of preference pairs and their candidate index."""

    dataset_id: str
    pairs: list[PreferencePair] = field(default_factory=list)
    pairs_by_axis: dict[PreferenceAxis, list[PreferencePair]] = field(default_factory=dict)
    candidate_index: dict[str, LabeledCandidate] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    source_round_id: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
