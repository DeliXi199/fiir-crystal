"""Abstract interface for learned or mock failure predictors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from fiir_crystal.failure import CandidateRecord, FailureLabel


@dataclass(slots=True)
class FailurePrediction:
    """Predicted failure vector and uncertainty."""

    sample_id: str
    pred_f1: float | None = None
    pred_f2: float | None = None
    pred_f3: float | None = None
    uncertainty: float = 0.0
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class FailurePredictor(ABC):
    """Predictor contract; no concrete GNN is implemented here."""

    @abstractmethod
    def predict(self, candidate: CandidateRecord) -> FailurePrediction:
        """Predict a failure vector for one candidate."""

    def predict_many(self, candidates: Sequence[CandidateRecord]) -> list[FailurePrediction]:
        """Predict a batch with a simple default loop."""

        return [self.predict(candidate) for candidate in candidates]

    def fit(self, labels: Sequence[FailureLabel]) -> None:
        """Optional hook for future training implementations."""

        raise NotImplementedError("FailurePredictor.fit is an adapter hook.")
