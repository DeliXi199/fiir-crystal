"""Evaluation metric data contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class MetricDirection(str, Enum):
    """Optimization direction or interpretation of a metric."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    TARGET_RANGE = "target_range"
    DIAGNOSTIC = "diagnostic"


class EvaluationMetric(str, Enum):
    """Common FIIR metric names."""

    VALIDITY = "validity"
    STABILITY = "stability"
    NOVELTY = "novelty"
    DIVERSITY = "diversity"
    FAILURE_RATE = "failure_rate"
    PRE_FILTER_RATE = "pre_filter_rate"
    PAIR_QUALITY = "pair_quality"


@dataclass(slots=True)
class MetricValue:
    """Single scalar metric value."""

    name: str
    value: int | float | str | None
    unit: str | None = None
    direction: MetricDirection = MetricDirection.DIAGNOSTIC
    n: int | None = None
    confidence_interval: tuple[float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetricReport:
    """Serializable report for a metric computation."""

    report_id: str
    scope: str
    subject_id: str
    metrics: list[MetricValue] = field(default_factory=list)
    tables: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ComparisonReport:
    """Comparison between a baseline and a method run."""

    baseline_id: str
    method_id: str
    delta_metrics: list[MetricValue] = field(default_factory=list)
    pareto_summary: dict[str, Any] = field(default_factory=dict)
    significance: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvaluationReport:
    """Compact JSON-serializable report for lightweight FIIR experiments."""

    average_f1: float
    average_f2: float
    average_f3: float | None
    max_f1: float
    max_f2: float
    max_f3: float | None
    valid_rate: float
    failure_rate: float
    hard_failure_count: int
    calibration_tier_distribution: dict[int, int] = field(default_factory=dict)
    pair_count: int = 0
    pairs_by_axis: dict[str, int] = field(default_factory=dict)
    pairs_by_mode: dict[str, int] = field(default_factory=dict)
    average_pair_margin: float = 0.0
    average_pair_confidence: float = 0.0
    valid_pair_ratio: float = 0.0
    top_k_average_failure: float | None = None
    top_k_valid_rate: float | None = None
    ranking_utility_stats: dict[str, float] = field(default_factory=dict)
    candidate_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a plain dictionary for scripts and tests."""

        return {
            "average_f1": self.average_f1,
            "average_f2": self.average_f2,
            "average_f3": self.average_f3,
            "max_f1": self.max_f1,
            "max_f2": self.max_f2,
            "max_f3": self.max_f3,
            "valid_rate": self.valid_rate,
            "failure_rate": self.failure_rate,
            "hard_failure_count": self.hard_failure_count,
            "calibration_tier_distribution": dict(self.calibration_tier_distribution),
            "pair_count": self.pair_count,
            "pairs_by_axis": dict(self.pairs_by_axis),
            "pairs_by_mode": dict(self.pairs_by_mode),
            "average_pair_margin": self.average_pair_margin,
            "average_pair_confidence": self.average_pair_confidence,
            "valid_pair_ratio": self.valid_pair_ratio,
            "top_k_average_failure": self.top_k_average_failure,
            "top_k_valid_rate": self.top_k_valid_rate,
            "ranking_utility_stats": dict(self.ranking_utility_stats),
            "candidate_count": self.candidate_count,
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        """Alias for JSON I/O helpers."""

        return self.as_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationReport":
        """Deserialize an evaluation report from JSON-compatible data."""

        return cls(
            average_f1=float(data.get("average_f1", 0.0)),
            average_f2=float(data.get("average_f2", 0.0)),
            average_f3=None if data.get("average_f3") is None else float(data["average_f3"]),
            max_f1=float(data.get("max_f1", 0.0)),
            max_f2=float(data.get("max_f2", 0.0)),
            max_f3=None if data.get("max_f3") is None else float(data["max_f3"]),
            valid_rate=float(data.get("valid_rate", 0.0)),
            failure_rate=float(data.get("failure_rate", 0.0)),
            hard_failure_count=int(data.get("hard_failure_count", 0)),
            calibration_tier_distribution={
                int(key): int(value)
                for key, value in dict(data.get("calibration_tier_distribution", {})).items()
            },
            pair_count=int(data.get("pair_count", 0)),
            pairs_by_axis={str(key): int(value) for key, value in dict(data.get("pairs_by_axis", {})).items()},
            pairs_by_mode={str(key): int(value) for key, value in dict(data.get("pairs_by_mode", {})).items()},
            average_pair_margin=float(data.get("average_pair_margin", 0.0)),
            average_pair_confidence=float(data.get("average_pair_confidence", 0.0)),
            valid_pair_ratio=float(data.get("valid_pair_ratio", 0.0)),
            top_k_average_failure=(
                None if data.get("top_k_average_failure") is None else float(data["top_k_average_failure"])
            ),
            top_k_valid_rate=None if data.get("top_k_valid_rate") is None else float(data["top_k_valid_rate"]),
            ranking_utility_stats={
                str(key): float(value)
                for key, value in dict(data.get("ranking_utility_stats", {})).items()
            },
            candidate_count=int(data.get("candidate_count", 0)),
            metadata=dict(data.get("metadata", {})),
        )


SimpleEvaluationReport = EvaluationReport


def evaluate_mock_fiir_loop(
    labels: Sequence[Any],
    pairs: Sequence[Any],
    ranked_candidates: Sequence[Any] | None = None,
    top_k: int | None = None,
    failure_threshold: float = 0.1,
) -> EvaluationReport:
    """Compute minimal metrics for the mock FIIR data flow."""

    label_count = len(labels)
    f1_values = [float(label.f1_geometry) for label in labels]
    f2_values = [float(label.f2_chemistry) for label in labels]
    f3_values = [float(label.f3_stability) for label in labels if label.f3_stability is not None]
    failed = [
        label
        for label in labels
        if label.pre_filtered
        or label.f1_geometry >= failure_threshold
        or label.f2_chemistry >= failure_threshold
        or (label.f3_stability is not None and label.f3_stability >= failure_threshold)
    ]
    pairs_by_axis: dict[str, int] = {}
    pairs_by_mode: dict[str, int] = {}
    pair_margins: list[float] = []
    pair_confidences: list[float] = []
    for pair in pairs:
        axis = getattr(pair.axis, "value", str(pair.axis))
        pairs_by_axis[axis] = pairs_by_axis.get(axis, 0) + 1
        mode = str(getattr(pair, "metadata", {}).get("mode", "axis_aligned"))
        pairs_by_mode[mode] = pairs_by_mode.get(mode, 0) + 1
        pair_margins.append(float(getattr(pair, "margin", 0.0)))
        pair_confidences.append(float(getattr(pair, "confidence", getattr(pair, "label_confidence", 0.0))))

    hard_failure_count = sum(
        bool(getattr(label, "pre_filtered", False))
        or bool(getattr(label, "metadata", {}).get("hard_failures"))
        for label in labels
    )
    valid_count = sum(
        not bool(getattr(label, "pre_filtered", False))
        and not bool(getattr(label, "metadata", {}).get("hard_failures"))
        for label in labels
    )
    tier_distribution: dict[int, int] = {}
    for label in labels:
        tier = int(getattr(label, "calibration_tier", -1))
        tier_distribution[tier] = tier_distribution.get(tier, 0) + 1
    valid_pair_count = sum(
        bool(getattr(pair, "winner_id", None)) and bool(getattr(pair, "loser_id", None))
        for pair in pairs
    )
    top_k_average_failure, top_k_valid_rate, utility_stats = _ranking_metrics(
        ranked_candidates or [],
        top_k=top_k,
    )

    return EvaluationReport(
        average_f1=sum(f1_values) / label_count if label_count else 0.0,
        average_f2=sum(f2_values) / label_count if label_count else 0.0,
        average_f3=(sum(f3_values) / len(f3_values)) if f3_values else None,
        max_f1=max(f1_values) if f1_values else 0.0,
        max_f2=max(f2_values) if f2_values else 0.0,
        max_f3=max(f3_values) if f3_values else None,
        valid_rate=(valid_count / label_count) if label_count else 0.0,
        failure_rate=(len(failed) / label_count) if label_count else 0.0,
        hard_failure_count=hard_failure_count,
        calibration_tier_distribution=tier_distribution,
        pair_count=len(pairs),
        pairs_by_axis=pairs_by_axis,
        pairs_by_mode=pairs_by_mode,
        average_pair_margin=(sum(pair_margins) / len(pair_margins)) if pair_margins else 0.0,
        average_pair_confidence=(sum(pair_confidences) / len(pair_confidences)) if pair_confidences else 0.0,
        valid_pair_ratio=(valid_pair_count / len(pairs)) if pairs else 0.0,
        top_k_average_failure=top_k_average_failure,
        top_k_valid_rate=top_k_valid_rate,
        ranking_utility_stats=utility_stats,
        candidate_count=label_count,
        metadata={"failure_threshold": failure_threshold},
    )


def _ranking_metrics(
    ranked_candidates: Sequence[Any],
    top_k: int | None,
) -> tuple[float | None, float | None, dict[str, float]]:
    if not ranked_candidates:
        return None, None, {}
    utilities = [float(candidate.acquisition.utility) for candidate in ranked_candidates]
    limit = top_k or len(ranked_candidates)
    top = list(ranked_candidates[:limit])
    failures: list[float] = []
    valid_count = 0
    for candidate in top:
        pred_f1 = candidate.acquisition.pred_f1 or 0.0
        pred_f2 = candidate.acquisition.pred_f2 or 0.0
        pred_f3 = candidate.acquisition.pred_f3 or 0.0
        failures.append((pred_f1 + pred_f2 + pred_f3) / 3.0)
        if candidate.objectives.get("validity", 1.0) > 0:
            valid_count += 1
    return (
        (sum(failures) / len(failures)) if failures else None,
        (valid_count / len(top)) if top else None,
        {
            "min": min(utilities),
            "max": max(utilities),
            "mean": sum(utilities) / len(utilities),
        },
    )


class FailureMetricComputer(ABC):
    """Interface for failure-label metric computation."""

    @abstractmethod
    def compute(self, data: Any) -> MetricReport:
        """Compute failure metrics."""


class PreferenceMetricComputer(ABC):
    """Interface for preference-dataset metric computation."""

    @abstractmethod
    def compute(self, data: Any) -> MetricReport:
        """Compute preference metrics."""


class GenerationMetricComputer(ABC):
    """Interface for generation metric computation."""

    @abstractmethod
    def compute(self, data: Any) -> MetricReport:
        """Compute generation metrics."""


class DiscoveryMetricComputer(ABC):
    """Interface for discovery pipeline metric computation."""

    @abstractmethod
    def compute(self, data: Any) -> MetricReport:
        """Compute discovery metrics."""
