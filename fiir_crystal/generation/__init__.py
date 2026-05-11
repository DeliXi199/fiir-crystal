"""Generation model wrapper interfaces."""

from fiir_crystal.generation.crystalformer_adapter import CrystalFormerAdapter
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
]
