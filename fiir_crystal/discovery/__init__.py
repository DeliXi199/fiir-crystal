"""Discovery pipeline skeleton."""

from fiir_crystal.discovery.interfaces import (
    DiscoveryPipeline,
    FeedbackSink,
    Ranker,
    ScreeningAdapter,
    ValidationAdapter,
)
from fiir_crystal.discovery.records import (
    AcquisitionScore,
    BudgetTier,
    DiscoveryCandidate,
    DiscoveryRun,
    FeedbackRecord,
    RankedCandidate,
    ScreeningDecision,
    ScreeningStatus,
    ValidationResult,
    ValidationTask,
    ValidationTaskStatus,
    ValidationTaskType,
)

__all__ = [
    "AcquisitionScore",
    "BudgetTier",
    "DiscoveryCandidate",
    "DiscoveryPipeline",
    "DiscoveryRun",
    "FeedbackRecord",
    "FeedbackSink",
    "RankedCandidate",
    "Ranker",
    "ScreeningAdapter",
    "ScreeningDecision",
    "ScreeningStatus",
    "ValidationAdapter",
    "ValidationResult",
    "ValidationTask",
    "ValidationTaskStatus",
    "ValidationTaskType",
]
