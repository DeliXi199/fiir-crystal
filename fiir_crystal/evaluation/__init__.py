"""Evaluation metric dataclasses and interfaces."""

from fiir_crystal.evaluation.error_audit import (
    AuditCandidateResult,
    AuditSummary,
    audit_candidates,
    summarize_audit,
    write_audit_outputs,
)
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
    "AuditCandidateResult",
    "AuditSummary",
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
    "audit_candidates",
    "evaluate_mock_fiir_loop",
    "summarize_audit",
    "write_audit_outputs",
]
