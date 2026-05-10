"""Abstract generation model wrapper."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from fiir_crystal.failure import CandidateRecord


@dataclass(slots=True)
class GenerationRequest:
    """Request to generate candidate structures."""

    num_samples: int
    seed: int | None = None
    conditions: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GenerationResult:
    """Generated candidates plus provenance."""

    candidates: list[CandidateRecord]
    model_id: str
    request: GenerationRequest
    metadata: dict[str, Any] = field(default_factory=dict)


class GeneratorWrapper(ABC):
    """Interface for crystal generation models."""

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate candidates without assuming any specific model backend."""
