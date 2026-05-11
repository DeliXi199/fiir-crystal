"""Generation model wrapper interfaces."""

from fiir_crystal.generation.crystalformer_adapter import CrystalFormerAdapter
from fiir_crystal.generation.crystalformer_bulk import (
    BulkFormulaConfig,
    CrystalFormerBulkConfig,
    build_bulk_plan,
    bulk_config_from_dict,
    load_bulk_config,
    run_crystalformer_bulk_generation,
    validate_bulk_generation_config,
)
from fiir_crystal.generation.crystalformer_smoke_pipeline import (
    CrystalFormerSmokePipelineConfig,
    run_crystalformer_smoke_pipeline,
)
from fiir_crystal.generation.crystalformer_workspace import (
    CrystalFormerWorkspaceCheckConfig,
    check_crystalformer_workspace,
)
from fiir_crystal.generation.external import ExternalGeneratorAdapter
from fiir_crystal.generation.interfaces import (
    GenerationRequest,
    GenerationResult,
    GeneratorWrapper,
)

__all__ = [
    "ExternalGeneratorAdapter",
    "GenerationRequest",
    "GenerationResult",
    "GeneratorWrapper",
    "CrystalFormerAdapter",
    "BulkFormulaConfig",
    "CrystalFormerBulkConfig",
    "build_bulk_plan",
    "bulk_config_from_dict",
    "load_bulk_config",
    "run_crystalformer_bulk_generation",
    "validate_bulk_generation_config",
    "CrystalFormerSmokePipelineConfig",
    "run_crystalformer_smoke_pipeline",
    "CrystalFormerWorkspaceCheckConfig",
    "check_crystalformer_workspace",
]
