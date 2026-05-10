"""Evaluation metric dataclasses and interfaces."""

from fiir_crystal.evaluation.metrics import (
    ComparisonReport,
    DiscoveryMetricComputer,
    EvaluationMetric,
    EvaluationReport,
    FailureMetricComputer,
    GenerationMetricComputer,
    MetricDirection,
    MetricReport,
    MetricValue,
    PreferenceMetricComputer,
    SimpleEvaluationReport,
    evaluate_mock_fiir_loop,
)

__all__ = [
    "ComparisonReport",
    "DiscoveryMetricComputer",
    "EvaluationMetric",
    "EvaluationReport",
    "FailureMetricComputer",
    "GenerationMetricComputer",
    "MetricDirection",
    "MetricReport",
    "MetricValue",
    "PreferenceMetricComputer",
    "SimpleEvaluationReport",
    "evaluate_mock_fiir_loop",
]
