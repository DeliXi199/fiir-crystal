"""DPO data preparation helpers for CrystalFormer outputs."""

from fiir_crystal.dpo.evidence import DpoEvidenceContext
from fiir_crystal.dpo.preference_builder import (
    DPOPreferencePair,
    GEOMETRY_CHEMISTRY_ONLY,
    PreferenceBuildConfig,
    PreferenceBuildSummary,
    STABILITY_AWARE_OFFLINE_VALIDATION,
    build_dpo_preferences,
    read_audit_candidates,
    write_preference_outputs,
)
from fiir_crystal.dpo.smoke_run import (
    CrystalFormerDpoSmokeRunConfig,
    prepare_crystalformer_dpo_smoke_run,
    render_dpo_smoke_run_report,
)
from fiir_crystal.dpo.training_boundary import (
    TRAINING_BOUNDARY_NAME,
    PairValidationSummary,
    TrainingBoundaryConfig,
    TrainingBoundarySummary,
    prepare_crystalformer_dpo_training_boundary,
    render_training_boundary_report,
    validate_preference_pairs_for_training,
)

__all__ = [
    "DPOPreferencePair",
    "DpoEvidenceContext",
    "GEOMETRY_CHEMISTRY_ONLY",
    "PreferenceBuildConfig",
    "PreferenceBuildSummary",
    "STABILITY_AWARE_OFFLINE_VALIDATION",
    "build_dpo_preferences",
    "CrystalFormerDpoSmokeRunConfig",
    "TRAINING_BOUNDARY_NAME",
    "PairValidationSummary",
    "prepare_crystalformer_dpo_smoke_run",
    "TrainingBoundaryConfig",
    "TrainingBoundarySummary",
    "prepare_crystalformer_dpo_training_boundary",
    "read_audit_candidates",
    "render_dpo_smoke_run_report",
    "render_training_boundary_report",
    "validate_preference_pairs_for_training",
    "write_preference_outputs",
]
