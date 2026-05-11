"""Adapter boundary for external generation backends."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from fiir_crystal.structures import CrystalStructureRecord


class ExternalGeneratorAdapter(Protocol):
    """Protocol for stdlib-only wrappers around external generators."""

    name: str

    def generate(self, config: dict[str, Any]) -> list[CrystalStructureRecord]:
        """Generate or load normalized candidate structures."""

    def load_outputs(self, output_dir: str | Path) -> list[CrystalStructureRecord]:
        """Load already-produced external generator outputs."""
