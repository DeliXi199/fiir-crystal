"""Lightweight F2 chemistry failure labeling."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from fiir_crystal.failure.interfaces import ChemistryScorer
from fiir_crystal.failure.mock import StructureLike
from fiir_crystal.failure.taxonomy import CandidateRecord, FailureAxis, FailureScore, FailureSeverity


class ChemistryRule(Protocol):
    """Future extension point for oxidation, charge, or coordination checks."""

    def score(self, structure: StructureLike) -> float:
        """Return a normalized chemistry failure score."""


@dataclass(slots=True)
class ChemistryFailureResult:
    """Result of a lightweight chemistry check."""

    f2_chemistry: float
    hard_failed: bool = False
    hard_failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


class ChemistryFailureLabeler(ChemistryScorer):
    """Rule/mock chemistry checker with no SMACT/BVS/CrystalNN dependency."""

    _TOKEN_RE = re.compile(r"([A-Z][a-z]?)(\d*)")

    def __init__(self, rules: list[ChemistryRule] | None = None) -> None:
        self.rules = rules or []

    def label_structure(self, structure: StructureLike) -> ChemistryFailureResult:
        hard_failures: list[str] = []
        evidence: dict[str, Any] = {}
        composition = structure.composition.strip() if structure.composition else ""

        if not composition:
            hard_failures.append("empty_composition")
            return ChemistryFailureResult(1.0, True, hard_failures, {"source": "rule_based"})

        tokens = self._TOKEN_RE.findall(composition)
        reconstructed = "".join(element + count for element, count in tokens)
        if not tokens or reconstructed != composition:
            hard_failures.append("composition_parse_failed")
            return ChemistryFailureResult(
                0.9,
                True,
                hard_failures,
                {"composition": composition, "source": "rule_based"},
            )

        mock_score = float(structure.metadata.get("mock_chemistry_score", structure.mock_chemistry_score))
        rule_scores = [max(0.0, min(1.0, rule.score(structure))) for rule in self.rules]
        score = max([mock_score, *rule_scores]) if rule_scores else mock_score
        score = max(0.0, min(1.0, score))
        evidence.update(
            {
                "composition": composition,
                "parsed_elements": [element for element, _ in tokens],
                "mock_chemistry_score": mock_score,
                "rule_count": len(self.rules),
                "source": "mock" if not self.rules else "rule_based",
            }
        )
        return ChemistryFailureResult(score, False, [], evidence)

    def score(self, candidate: CandidateRecord) -> FailureScore:
        if not isinstance(candidate.structure, StructureLike):
            raise TypeError("ChemistryFailureLabeler expects a StructureLike candidate structure.")
        result = self.label_structure(candidate.structure)
        return FailureScore(
            axis=FailureAxis.F2_CHEMISTRY,
            value=result.f2_chemistry,
            unit="unitless",
            severity=self._severity(result.f2_chemistry),
            confidence=0.7 if not result.hard_failed else 1.0,
            evidence={
                **result.evidence,
                "hard_failed": result.hard_failed,
                "hard_failures": result.hard_failures,
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
