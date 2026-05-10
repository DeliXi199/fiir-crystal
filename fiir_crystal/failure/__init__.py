"""Failure taxonomy dataclasses and labeling interfaces."""

from fiir_crystal.failure.interfaces import (
    ChemistryScorer,
    FailureLabeler,
    GeometryScorer,
    PreFilter,
    StabilityScorer,
)
from fiir_crystal.failure.chemistry import ChemistryFailureLabeler, ChemistryFailureResult, ChemistryRule
from fiir_crystal.failure.geometry import GeometryFailureLabeler, GeometryFailureResult
from fiir_crystal.failure.oracle import FailureOracle
from fiir_crystal.failure.stability import StabilityAdapter, StabilityFailureLabeler, StabilityFailureResult
from fiir_crystal.failure.taxonomy import (
    CalibrationTier,
    CandidateRecord,
    FailureAxis,
    FailureLabel,
    FailureLabelBatch,
    FailureScore,
    FailureSeverity,
    FailureVector,
    PreFilterResult,
    TierSource,
    tier_weight,
)
from fiir_crystal.failure.mock import (
    CrystalRecord,
    MockFailureLabeler,
    StructureLike,
    demo_mock_crystals,
    records_to_candidates,
)

__all__ = [
    "CalibrationTier",
    "CandidateRecord",
    "ChemistryScorer",
    "ChemistryFailureLabeler",
    "ChemistryFailureResult",
    "ChemistryRule",
    "CrystalRecord",
    "FailureAxis",
    "FailureLabel",
    "FailureLabelBatch",
    "FailureLabeler",
    "FailureScore",
    "FailureSeverity",
    "FailureVector",
    "FailureOracle",
    "GeometryScorer",
    "GeometryFailureLabeler",
    "GeometryFailureResult",
    "MockFailureLabeler",
    "PreFilter",
    "PreFilterResult",
    "StabilityScorer",
    "StabilityAdapter",
    "StabilityFailureLabeler",
    "StabilityFailureResult",
    "StructureLike",
    "TierSource",
    "demo_mock_crystals",
    "records_to_candidates",
    "tier_weight",
]
