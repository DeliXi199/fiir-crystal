"""Lightweight F3 stability placeholder labeling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from fiir_crystal.failure.interfaces import StabilityScorer
from fiir_crystal.failure.mock import StructureLike
from fiir_crystal.failure.taxonomy import CandidateRecord, FailureAxis, FailureScore, FailureSeverity


class StabilityAdapter(Protocol):
    """Future extension point for MLIP, E_above_hull, or DFT calibration."""

    def score(self, structure: StructureLike) -> float:
        """Return a normalized stability failure score."""


@dataclass(slots=True)
class StabilityFailureResult:
    """Result of a lightweight stability check."""

    f3_stability: float
    hard_failed: bool = False
    hard_failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


class StabilityFailureLabeler(StabilityScorer):
    """Mock stability scorer; no MLIP, E_hull, or DFT is invoked."""

    def __init__(self, adapter: StabilityAdapter | None = None, missing_score: float = 0.5) -> None:
        self.adapter = adapter
        self.missing_score = missing_score

    def label_structure(self, structure: StructureLike) -> StabilityFailureResult:
        if self.adapter is not None:
            score = max(0.0, min(1.0, self.adapter.score(structure)))
            return StabilityFailureResult(score, False, [], {"source": "adapter_placeholder"})

        raw_score = structure.metadata.get("mock_stability_score", structure.mock_stability_score)
        if raw_score is None:
            return StabilityFailureResult(
                self.missing_score,
                False,
                [],
                {"source": "missing_placeholder", "missing_score": self.missing_score},
            )
        score = max(0.0, min(1.0, float(raw_score)))
        return StabilityFailureResult(score, False, [], {"source": "mock", "mock_stability_score": score})

    def score(
        self,
        candidate: CandidateRecord,
        stability_results: dict[str, Any] | None = None,
    ) -> FailureScore:
        if not isinstance(candidate.structure, StructureLike):
            raise TypeError("StabilityFailureLabeler expects a StructureLike candidate structure.")
        result = self.label_structure(candidate.structure)
        return FailureScore(
            axis=FailureAxis.F3_STABILITY,
            value=result.f3_stability,
            unit="normalized",
            severity=self._severity(result.f3_stability),
            confidence=0.6,
            evidence={
                **result.evidence,
                "hard_failed": result.hard_failed,
                "hard_failures": result.hard_failures,
                "stability_results": stability_results or {},
            },
        )

    def _severity(self, score: float) -> FailureSeverity:
        if score < 0.1:
            return FailureSeverity.PASS
        if score < 0.3:
            return FailureSeverity.MILD
        if score <= 0.7:
            return FailureSeverity.MODERATE
        return FailureSeverity.SEVERE
