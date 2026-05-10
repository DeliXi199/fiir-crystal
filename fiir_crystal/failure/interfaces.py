"""Abstract interfaces for failure labeling components."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

from fiir_crystal.failure.taxonomy import (
    CandidateRecord,
    FailureLabel,
    FailureLabelBatch,
    FailureScore,
    PreFilterResult,
)


class PreFilter(ABC):
    """Interface for trivial invalid-structure filtering."""

    @abstractmethod
    def check(self, candidate: CandidateRecord) -> PreFilterResult:
        """Return whether a candidate should continue into labeling."""


class GeometryScorer(ABC):
    """Interface for F1 geometry scoring."""

    @abstractmethod
    def score(self, candidate: CandidateRecord) -> FailureScore:
        """Score F1 geometry validity."""


class ChemistryScorer(ABC):
    """Interface for F2 chemistry scoring."""

    @abstractmethod
    def score(self, candidate: CandidateRecord) -> FailureScore:
        """Score F2 chemistry validity."""


class StabilityScorer(ABC):
    """Interface for F3 stability scoring.

    Implementations should consume already available offline or adapter results.
    They must not directly invoke DFT, MLIP, or remote databases.
    """

    @abstractmethod
    def score(
        self,
        candidate: CandidateRecord,
        stability_results: dict[str, Any] | None = None,
    ) -> FailureScore:
        """Score F3 thermodynamic stability."""


class FailureLabeler(ABC):
    """Interface for full FIIR failure labeling."""

    @abstractmethod
    def label(self, candidate: CandidateRecord) -> FailureLabel:
        """Create a complete failure label for one candidate."""

    def label_many(self, candidates: Sequence[CandidateRecord]) -> FailureLabelBatch:
        """Label a sequence of candidates with a simple default loop."""

        labels = [self.label(candidate) for candidate in candidates]
        return FailureLabelBatch(labels=labels, summary={"count": len(labels)})
