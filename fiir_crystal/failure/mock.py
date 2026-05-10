"""Mock failure-labeling demo components.

These classes intentionally operate on plain metadata rather than crystal
toolkits. They are useful for exercising the FIIR data flow without pymatgen,
MLIP, DFT, remote APIs, or downloaded datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from fiir_crystal.failure.interfaces import FailureLabeler
from fiir_crystal.failure.taxonomy import (
    CandidateRecord,
    CalibrationTier,
    FailureAxis,
    FailureLabel,
    FailureLabelBatch,
    FailureScore,
    FailureSeverity,
    FailureVector,
    TierSource,
    tier_weight,
)


@dataclass(slots=True)
class StructureLike:
    """Lightweight structure-like record with no crystal toolkit dependency."""

    candidate_id: str
    composition: str
    num_atoms: int
    space_group: int | None = None
    prototype: str | None = None
    mock_geometry_score: float = 0.0
    mock_chemistry_score: float = 0.0
    mock_stability_score: float | None = None
    lattice_lengths: tuple[float, float, float] | None = None
    lattice_angles: tuple[float, float, float] | None = None
    frac_coords: tuple[tuple[float, float, float], ...] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sample_id(self) -> str:
        """Backward-compatible alias for earlier mock demos."""

        return self.candidate_id

    @property
    def structure_ref(self) -> str:
        """Stable mock structure reference."""

        return f"mock://{self.candidate_id}"

    @property
    def chemical_bucket(self) -> str:
        """Simple bucket for pair mining."""

        return self.prototype or self.composition

    def to_candidate_record(self, source_model: str = "mock") -> CandidateRecord:
        """Wrap this record as a generic FIIR candidate."""

        return CandidateRecord(
            sample_id=self.sample_id,
            structure=self,
            structure_ref=self.structure_ref,
            source_model=source_model,
            metadata={
                "composition": self.composition,
                "num_atoms": self.num_atoms,
                "space_group": self.space_group,
                "prototype": self.prototype,
                **self.metadata,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the lightweight structure to a JSON-compatible dict."""

        return {
            "candidate_id": self.candidate_id,
            "composition": self.composition,
            "num_atoms": self.num_atoms,
            "space_group": self.space_group,
            "prototype": self.prototype,
            "mock_geometry_score": self.mock_geometry_score,
            "mock_chemistry_score": self.mock_chemistry_score,
            "mock_stability_score": self.mock_stability_score,
            "lattice_lengths": list(self.lattice_lengths) if self.lattice_lengths is not None else None,
            "lattice_angles": list(self.lattice_angles) if self.lattice_angles is not None else None,
            "frac_coords": [list(coord) for coord in self.frac_coords] if self.frac_coords is not None else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructureLike":
        """Deserialize a `StructureLike` from a JSON-compatible dict."""

        candidate_id = data.get("candidate_id", data.get("sample_id"))
        if not candidate_id:
            raise ValueError("StructureLike requires candidate_id.")
        return cls(
            candidate_id=str(candidate_id),
            composition=str(data.get("composition", "")),
            num_atoms=int(data.get("num_atoms", 0)),
            space_group=data.get("space_group"),
            prototype=data.get("prototype"),
            mock_geometry_score=float(data.get("mock_geometry_score", data.get("metadata", {}).get("mock_geometry_score", 0.0))),
            mock_chemistry_score=float(data.get("mock_chemistry_score", data.get("metadata", {}).get("mock_chemistry_score", 0.0))),
            mock_stability_score=(
                None
                if data.get("mock_stability_score", data.get("metadata", {}).get("mock_stability_score")) is None
                else float(data.get("mock_stability_score", data.get("metadata", {}).get("mock_stability_score")))
            ),
            lattice_lengths=_tuple3_or_none(data.get("lattice_lengths")),
            lattice_angles=_tuple3_or_none(data.get("lattice_angles")),
            frac_coords=_coords_or_none(data.get("frac_coords")),
            metadata=dict(data.get("metadata", {})),
        )


class CrystalRecord(StructureLike):
    """Backward-compatible name for the lightweight mock structure record."""


def _tuple3_or_none(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if len(value) != 3:
        raise ValueError("Expected a length-3 numeric sequence.")
    return (float(value[0]), float(value[1]), float(value[2]))


def _coords_or_none(value: Any) -> tuple[tuple[float, float, float], ...] | None:
    if value is None:
        return None
    return tuple(_tuple3_or_none(coord) for coord in value)


def _severity_for_unit_interval(value: float | None) -> FailureSeverity:
    if value is None:
        return FailureSeverity.UNKNOWN
    if value < 0.1:
        return FailureSeverity.PASS
    if value < 0.3:
        return FailureSeverity.MILD
    if value <= 0.7:
        return FailureSeverity.MODERATE
    return FailureSeverity.SEVERE


def _severity_for_stability(value: float | None) -> FailureSeverity:
    if value is None:
        return FailureSeverity.UNKNOWN
    if value < 0.1:
        return FailureSeverity.PASS
    if value <= 0.2:
        return FailureSeverity.MILD
    if value <= 0.5:
        return FailureSeverity.MODERATE
    return FailureSeverity.SEVERE


class MockFailureLabeler(FailureLabeler):
    """Failure labeler backed entirely by mock scores on `CrystalRecord`."""

    def __init__(
        self,
        calibration_tier: int = int(CalibrationTier.TIER_1),
        tier_source: str = TierSource.MOCK_ONLY.value,
    ) -> None:
        self.calibration_tier = calibration_tier
        self.tier_source = tier_source

    def vectorize(self, crystal: CrystalRecord) -> FailureVector:
        """Create the compact failure vector from mock scores."""

        confidence = tier_weight(self.calibration_tier)
        return FailureVector(
            sample_id=crystal.sample_id,
            f1_geometry=crystal.mock_geometry_score,
            f2_chemistry=crystal.mock_chemistry_score,
            f3_stability=crystal.mock_stability_score,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            calibration_tier=self.calibration_tier,
            is_valid=crystal.num_atoms > 0,
            hard_failures=[] if crystal.num_atoms > 0 else ["empty_structure"],
            structure_ref=crystal.structure_ref,
            metadata={
                "composition": crystal.composition,
                "num_atoms": crystal.num_atoms,
                "space_group": crystal.space_group,
                "prototype": crystal.prototype,
            },
        )

    def label_crystal(self, crystal: CrystalRecord) -> FailureLabel:
        """Create a full `FailureLabel` from a mock crystal."""

        vector = self.vectorize(crystal)
        confidence = vector.confidence
        pre_filtered = crystal.num_atoms <= 0
        reject_reason = "empty_structure" if pre_filtered else None
        f1 = 1.0 if pre_filtered else vector.f1_geometry
        f2 = 1.0 if pre_filtered else vector.f2_chemistry
        f3 = 1.0 if pre_filtered else vector.f3_stability

        axis_scores = [
            FailureScore(
                axis=FailureAxis.F1_GEOMETRY,
                value=f1,
                unit="unitless",
                severity=_severity_for_unit_interval(f1),
                confidence=confidence,
                evidence={"mock_field": "mock_geometry_score"},
            ),
            FailureScore(
                axis=FailureAxis.F2_CHEMISTRY,
                value=f2,
                unit="unitless",
                severity=_severity_for_unit_interval(f2),
                confidence=confidence,
                evidence={"mock_field": "mock_chemistry_score"},
            ),
            FailureScore(
                axis=FailureAxis.F3_STABILITY,
                value=f3,
                unit="eV/atom",
                severity=_severity_for_stability(f3),
                confidence=confidence,
                evidence={"mock_field": "mock_stability_score"},
            ),
        ]

        return FailureLabel(
            sample_id=crystal.sample_id,
            structure_ref=crystal.structure_ref,
            f1_geometry=f1,
            f2_chemistry=f2,
            f3_stability=f3,
            f3_normalized=f3,
            axis_scores=axis_scores,
            uncertainty=vector.uncertainty,
            confidence=confidence,
            calibration_tier=self.calibration_tier,
            tier_source=self.tier_source,
            pre_filtered=pre_filtered,
            reject_reason=reject_reason,
            metadata=vector.metadata,
        )

    def label(self, candidate: CandidateRecord) -> FailureLabel:
        """Label a generic candidate whose structure is a `CrystalRecord`."""

        if not isinstance(candidate.structure, CrystalRecord):
            raise TypeError("MockFailureLabeler expects CandidateRecord.structure to be CrystalRecord.")
        return self.label_crystal(candidate.structure)

    def label_crystals(self, crystals: Sequence[CrystalRecord]) -> FailureLabelBatch:
        """Label a sequence of mock crystals."""

        labels = [self.label_crystal(crystal) for crystal in crystals]
        return FailureLabelBatch(
            labels=labels,
            summary={
                "count": len(labels),
                "pre_filtered": sum(label.pre_filtered for label in labels),
            },
            config={
                "labeler": self.__class__.__name__,
                "calibration_tier": self.calibration_tier,
            },
        )


def demo_mock_crystals() -> list[CrystalRecord]:
    """Return a deterministic toy crystal set that exercises all FIIR axes."""

    return [
        CrystalRecord(
            "geo_good",
            "CaTiO3",
            5,
            221,
            "perovskite",
            0.02,
            0.05,
            0.08,
            (3.8, 3.8, 3.8),
            (90.0, 90.0, 90.0),
            ((0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5)),
        ),
        CrystalRecord(
            "geo_bad",
            "SrTiO3",
            5,
            221,
            "perovskite",
            0.55,
            0.06,
            0.09,
            (3.9, 3.9, 3.9),
            (90.0, 90.0, 90.0),
            ((0.0, 0.0, 0.0), (0.02, 0.02, 0.02), (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5)),
        ),
        CrystalRecord(
            "chem_good",
            "BaZrO3",
            5,
            221,
            "perovskite",
            0.04,
            0.03,
            0.12,
            (4.1, 4.1, 4.1),
            (90.0, 90.0, 90.0),
            ((0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5)),
        ),
        CrystalRecord(
            "chem_bad",
            "BaSnO3",
            5,
            221,
            "perovskite",
            0.05,
            0.48,
            0.13,
            (4.1, 4.1, 4.1),
            (90.0, 90.0, 90.0),
            ((0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5)),
        ),
        CrystalRecord(
            "stable_good",
            "MgAl2O4",
            7,
            227,
            "spinel",
            0.03,
            0.04,
            0.06,
            (8.1, 8.1, 8.1),
            (90.0, 90.0, 90.0),
            ((0.0, 0.0, 0.0), (0.25, 0.25, 0.25), (0.5, 0.5, 0.5), (0.75, 0.75, 0.75), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, 0.0, 0.5)),
        ),
        CrystalRecord(
            "stable_bad",
            "ZnAl2O4",
            7,
            227,
            "spinel",
            0.04,
            0.05,
            0.42,
            (8.0, 8.0, 8.0),
            (90.0, 90.0, 90.0),
            ((0.0, 0.0, 0.0), (0.25, 0.25, 0.25), (0.5, 0.5, 0.5), (0.75, 0.75, 0.75), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, 0.0, 0.5)),
        ),
        CrystalRecord(
            "stable_worse",
            "CdAl2O4",
            7,
            227,
            "spinel",
            0.05,
            0.06,
            0.72,
            (8.2, 8.2, 8.2),
            (90.0, 90.0, 90.0),
            ((0.0, 0.0, 0.0), (0.25, 0.25, 0.25), (0.5, 0.5, 0.5), (0.75, 0.75, 0.75), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, 0.0, 0.5)),
        ),
    ]


def records_to_candidates(crystals: Iterable[CrystalRecord]) -> list[CandidateRecord]:
    """Convert mock crystals to generic candidate records."""

    return [crystal.to_candidate_record() for crystal in crystals]
