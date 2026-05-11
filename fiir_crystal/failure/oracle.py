"""Composable lightweight FIIR failure oracle."""

from __future__ import annotations

from dataclasses import dataclass

from fiir_crystal.failure.chemistry import ChemistryFailureLabeler
from fiir_crystal.failure.geometry import GeometryFailureLabeler
from fiir_crystal.failure.mock import StructureLike
from fiir_crystal.failure.stability import StabilityFailureLabeler
from fiir_crystal.failure.taxonomy import (
    CalibrationTier,
    FailureAxis,
    FailureLabel,
    FailureScore,
    FailureSeverity,
    FailureVector,
    TierSource,
)


@dataclass(slots=True)
class FailureOracle:
    """Composable F1/F2/F3 oracle backed by lightweight replaceable labelers."""

    geometry_labeler: GeometryFailureLabeler
    chemistry_labeler: ChemistryFailureLabeler
    stability_labeler: StabilityFailureLabeler

    @classmethod
    def default(cls) -> "FailureOracle":
        """Create the default lightweight oracle."""

        return cls(
            geometry_labeler=GeometryFailureLabeler(),
            chemistry_labeler=ChemistryFailureLabeler(),
            stability_labeler=StabilityFailureLabeler(),
        )

    def vectorize(self, structure: StructureLike) -> FailureVector:
        """Return the unified FIIR failure vector."""

        geometry = self.geometry_labeler.label_structure(structure)
        chemistry = self.chemistry_labeler.label_structure(structure)
        stability = self.stability_labeler.label_structure(structure)
        hard_failures = [*geometry.hard_failures, *chemistry.hard_failures, *stability.hard_failures]
        is_valid = not hard_failures and structure.num_atoms > 0
        tier = self._assign_tier(is_valid, hard_failures, geometry, chemistry, stability)
        confidence = self._confidence_for_tier(tier)

        return FailureVector(
            sample_id=structure.candidate_id,
            structure_ref=structure.structure_ref,
            f1_geometry=geometry.f1_geometry,
            f2_chemistry=chemistry.f2_chemistry,
            f3_stability=stability.f3_stability,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            calibration_tier=tier,
            is_valid=is_valid,
            hard_failures=hard_failures,
            metadata={
                "composition": structure.composition,
                "num_atoms": structure.num_atoms,
                "space_group": structure.space_group,
                "prototype": structure.prototype,
                "is_valid": is_valid,
                "hard_failures": hard_failures,
                "geometry": geometry.evidence,
                "chemistry": chemistry.evidence,
                "stability": stability.evidence,
                "tier_note": self._tier_note(tier),
            },
        )

    def label_structure(self, structure: StructureLike) -> FailureLabel:
        """Return a `FailureLabel` for compatibility with existing modules."""

        vector = self.vectorize(structure)
        return FailureLabel(
            sample_id=vector.sample_id,
            structure_ref=structure.structure_ref,
            f1_geometry=vector.f1_geometry,
            f2_chemistry=vector.f2_chemistry,
            f3_stability=vector.f3_stability,
            f3_normalized=vector.f3_stability,
            axis_scores=[
                self._axis_score(FailureAxis.F1_GEOMETRY, vector.f1_geometry, "unitless", vector),
                self._axis_score(FailureAxis.F2_CHEMISTRY, vector.f2_chemistry, "unitless", vector),
                self._axis_score(FailureAxis.F3_STABILITY, vector.f3_stability, "normalized", vector),
            ],
            uncertainty=vector.uncertainty,
            confidence=vector.confidence,
            calibration_tier=vector.calibration_tier,
            tier_source=self._tier_source(vector.calibration_tier),
            pre_filtered=not vector.is_valid,
            reject_reason=";".join(vector.hard_failures) if vector.hard_failures else None,
            metadata=vector.metadata,
        )

    def _assign_tier(self, is_valid: bool, hard_failures: list[str], *results: object) -> int:
        if not is_valid or hard_failures:
            return int(CalibrationTier.TIER_0)
        sources = [getattr(result, "evidence", {}).get("source") for result in results]
        if any(source in {"missing_placeholder", "unavailable_without_offline_validation"} for source in sources):
            return int(CalibrationTier.TIER_1)
        if sources and all(source == "mock" for source in sources):
            return int(CalibrationTier.TIER_1)
        return int(CalibrationTier.TIER_2)

    def _confidence_for_tier(self, tier: int) -> float:
        return {
            0: 0.0,
            1: 0.5,
            2: 0.7,
            3: 0.85,
            4: 1.0,
        }.get(tier, 0.0)

    def _tier_source(self, tier: int) -> str:
        return {
            0: TierSource.INVALID.value,
            1: TierSource.MOCK_ONLY.value,
            2: TierSource.RULE_BASED.value,
            3: TierSource.MULTI_ADAPTER_AGREEMENT.value,
            4: TierSource.DFT_PROVIDED.value,
        }.get(tier, TierSource.UNKNOWN.value)

    def _tier_note(self, tier: int) -> str:
        if tier == 3:
            return "reserved for future ensemble/calibrated lightweight adapters"
        if tier == 4:
            return "reserved for future DFT-calibrated labels"
        return self._tier_source(tier)

    def _axis_score(
        self,
        axis: FailureAxis,
        value: float | None,
        unit: str,
        vector: FailureVector,
    ) -> FailureScore:
        return FailureScore(
            axis=axis,
            value=value,
            unit=unit,
            severity=self._severity(value),
            confidence=vector.confidence,
            uncertainty=vector.uncertainty,
            evidence={"oracle": self.__class__.__name__},
        )

    def _severity(self, value: float | None) -> FailureSeverity:
        if value is None:
            return FailureSeverity.UNKNOWN
        if value < 0.1:
            return FailureSeverity.PASS
        if value < 0.3:
            return FailureSeverity.MILD
        if value <= 0.7:
            return FailureSeverity.MODERATE
        return FailureSeverity.SEVERE
