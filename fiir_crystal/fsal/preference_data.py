"""Dataclasses for FSAL preference data."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fiir_crystal.failure import FailureLabel


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


@dataclass(slots=True)
class MatchedPairConfig:
    """Configuration for matched axis-aligned pair mining."""

    main_axis_threshold: float = 0.3
    other_axis_threshold: float = 0.15
    atom_count_tolerance: float = 0.2
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
    metadata: dict[str, Any] = field(default_factory=dict)


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
