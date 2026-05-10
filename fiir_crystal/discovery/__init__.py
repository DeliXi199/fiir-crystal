"""Discovery pipeline skeleton."""

from fiir_crystal.discovery.interfaces import (
    DiscoveryPipeline,
    FeedbackSink,
    Ranker,
    ScreeningAdapter,
    ValidationAdapter,
)
from fiir_crystal.discovery.mock_pipeline import (
    MockDiscoveryPipeline,
    MockFeedbackSink,
    MockRanker,
    MockScreeningAdapter,
    MockValidationAdapter,
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
    "MockDiscoveryPipeline",
    "MockFeedbackSink",
    "MockRanker",
    "MockScreeningAdapter",
    "MockValidationAdapter",
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
