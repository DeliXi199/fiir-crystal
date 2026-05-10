"""Evaluation metric data contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
