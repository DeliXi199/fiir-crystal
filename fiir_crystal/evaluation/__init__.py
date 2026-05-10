"""Evaluation metric dataclasses and interfaces."""

from fiir_crystal.evaluation.metrics import (
    ComparisonReport,
    DiscoveryMetricComputer,
    EvaluationMetric,
    FailureMetricComputer,
    GenerationMetricComputer,
    MetricDirection,
    MetricReport,
    MetricValue,
    PreferenceMetricComputer,
)

__all__ = [
    "ComparisonReport",
    "DiscoveryMetricComputer",
    "EvaluationMetric",
    "FailureMetricComputer",
    "GenerationMetricComputer",
    "MetricDirection",
    "MetricReport",
    "MetricValue",
    "PreferenceMetricComputer",
]
