"""Lightweight F1 geometry failure labeling."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from fiir_crystal.failure.interfaces import GeometryScorer
from fiir_crystal.failure.mock import StructureLike
from fiir_crystal.failure.taxonomy import (
    CandidateRecord,
    FailureAxis,
    FailureScore,
    FailureSeverity,
)


@dataclass(slots=True)
class GeometryFailureResult:
    """Result of a lightweight geometry check."""

    f1_geometry: float
    hard_failed: bool
    hard_failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


class GeometryFailureLabeler(GeometryScorer):
    """Rule-based geometry checker with no pymatgen dependency."""

    def __init__(
        self,
        min_distance: float = 0.6,
        min_lattice_length: float = 1.0,
        max_lattice_length: float = 80.0,
        min_angle: float = 20.0,
        max_angle: float = 160.0,
    ) -> None:
        self.min_distance = min_distance
        self.min_lattice_length = min_lattice_length
        self.max_lattice_length = max_lattice_length
        self.min_angle = min_angle
        self.max_angle = max_angle

    def label_structure(self, structure: StructureLike) -> GeometryFailureResult:
        """Return a normalized F1 geometry score and hard-constraint flags."""

        hard_failures: list[str] = []
        soft_scores: list[float] = []
        evidence: dict[str, Any] = {}

        if structure.num_atoms <= 0:
            hard_failures.append("empty_structure")

        if not structure.lattice_lengths or len(structure.lattice_lengths) != 3:
            hard_failures.append("missing_lattice_lengths")
        else:
            length_score = self._lattice_length_score(structure.lattice_lengths)
            soft_scores.append(length_score)
            evidence["lattice_length_score"] = length_score

        if not structure.lattice_angles or len(structure.lattice_angles) != 3:
            hard_failures.append("missing_lattice_angles")
        else:
            angle_score = self._angle_score(structure.lattice_angles)
            soft_scores.append(angle_score)
            evidence["lattice_angle_score"] = angle_score
            if any(angle <= 0 or angle >= 180 for angle in structure.lattice_angles):
                hard_failures.append("impossible_lattice_angle")

        if not structure.frac_coords:
            hard_failures.append("missing_frac_coords")
        elif len(structure.frac_coords) != structure.num_atoms:
            hard_failures.append("coord_count_mismatch")
        elif structure.lattice_lengths:
            min_dist = self._minimum_mock_distance(structure.frac_coords, structure.lattice_lengths)
            distance_score = max(0.0, min(1.0, (self.min_distance - min_dist) / self.min_distance))
            soft_scores.append(distance_score)
            evidence["min_distance"] = min_dist
            evidence["distance_score"] = distance_score

        if hard_failures:
            return GeometryFailureResult(
                f1_geometry=1.0,
                hard_failed=True,
                hard_failures=hard_failures,
                evidence=evidence,
            )

        mock_score = structure.metadata.get("mock_geometry_score", structure.mock_geometry_score)
        soft_scores.append(float(mock_score))
        f1 = max(0.0, min(1.0, max(soft_scores) if soft_scores else 0.0))
        return GeometryFailureResult(
            f1_geometry=f1,
            hard_failed=False,
            hard_failures=[],
            evidence={**evidence, "mock_geometry_score": mock_score, "source": "rule_based"},
        )

    def score(self, candidate: CandidateRecord) -> FailureScore:
        """Score F1 geometry for a `CandidateRecord`."""

        if not isinstance(candidate.structure, StructureLike):
            raise TypeError("GeometryFailureLabeler expects a StructureLike candidate structure.")
        result = self.label_structure(candidate.structure)
        return FailureScore(
            axis=FailureAxis.F1_GEOMETRY,
            value=result.f1_geometry,
            unit="unitless",
            severity=self._severity(result.f1_geometry),
            confidence=0.8 if not result.hard_failed else 1.0,
            evidence={
                **result.evidence,
                "hard_failed": result.hard_failed,
                "hard_failures": result.hard_failures,
            },
        )

    def _lattice_length_score(self, lengths: tuple[float, float, float]) -> float:
        scores: list[float] = []
        for length in lengths:
            if length <= 0:
                scores.append(1.0)
            elif length < self.min_lattice_length:
                scores.append((self.min_lattice_length - length) / self.min_lattice_length)
            elif length > self.max_lattice_length:
                scores.append(min(1.0, (length - self.max_lattice_length) / self.max_lattice_length))
            else:
                scores.append(0.0)
        return max(scores)

    def _angle_score(self, angles: tuple[float, float, float]) -> float:
        scores: list[float] = []
        for angle in angles:
            if angle < self.min_angle:
                scores.append(min(1.0, (self.min_angle - angle) / self.min_angle))
            elif angle > self.max_angle:
                scores.append(min(1.0, (angle - self.max_angle) / (180.0 - self.max_angle)))
            else:
                scores.append(0.0)
        return max(scores)

    def _minimum_mock_distance(
        self,
        frac_coords: tuple[tuple[float, float, float], ...],
        lattice_lengths: tuple[float, float, float],
    ) -> float:
        if len(frac_coords) < 2:
            return self.min_distance
        min_dist = float("inf")
        for left_index, left in enumerate(frac_coords):
            for right in frac_coords[left_index + 1 :]:
                dist = sqrt(
                    sum(((left[axis] - right[axis]) * lattice_lengths[axis]) ** 2 for axis in range(3))
                )
                min_dist = min(min_dist, dist)
        return min_dist if min_dist != float("inf") else self.min_distance

    def _severity(self, score: float) -> FailureSeverity:
        if score < 0.1:
            return FailureSeverity.PASS
        if score < 0.3:
            return FailureSeverity.MILD
        if score <= 0.7:
            return FailureSeverity.MODERATE
        return FailureSeverity.SEVERE
