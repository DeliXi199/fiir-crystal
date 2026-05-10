"""Abstract discovery pipeline interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from fiir_crystal.discovery.records import (
    DiscoveryCandidate,
    DiscoveryRun,
    FeedbackRecord,
    RankedCandidate,
    ScreeningDecision,
    ValidationResult,
    ValidationTask,
)


class ScreeningAdapter(ABC):
    """Interface for a discovery screening layer."""

    @abstractmethod
    def screen(self, candidate: DiscoveryCandidate) -> ScreeningDecision:
        """Return a screening decision for one candidate."""


class Ranker(ABC):
    """Interface for multi-objective candidate ranking."""

    @abstractmethod
    def rank(self, candidates: Sequence[DiscoveryCandidate]) -> list[RankedCandidate]:
        """Rank candidates without requiring external services."""


class ValidationAdapter(ABC):
    """Interface for validation task creation."""

    @abstractmethod
    def create_tasks(self, candidates: Sequence[RankedCandidate]) -> list[ValidationTask]:
        """Create validation task metadata only."""


class FeedbackSink(ABC):
    """Interface for importing validation results as feedback."""

    @abstractmethod
    def record(self, results: Sequence[ValidationResult]) -> list[FeedbackRecord]:
        """Convert offline validation results into feedback records."""


class DiscoveryPipeline(ABC):
    """End-to-end discovery pipeline contract."""

    @abstractmethod
    def run(self, candidates: Sequence[DiscoveryCandidate]) -> DiscoveryRun:
        """Run the lightweight discovery orchestration."""
