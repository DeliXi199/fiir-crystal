"""Shared evidence context for CrystalFormer DPO handoff artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE_CAVEAT = (
    "Preference labels may be MLIP relaxation proxy evidence from FIIR offline "
    "validation imports. They are not DFT evidence and are not self-consistent "
    "hull-confirmed stability unless an explicit downstream validation artifact "
    "says so."
)


@dataclass(slots=True)
class DpoEvidenceContext:
    """Provenance and caveat metadata for a DPO preference artifact."""

    preference_artifact_label: str | None = None
    source_validation_jsonl: Path | None = None
    input_candidate_count: int | None = None
    f3_available_candidate_count: int | None = None
    disagreement_candidate_count: int | None = None
    caveat: str = DEFAULT_EVIDENCE_CAVEAT

    def to_dict(self) -> dict[str, Any]:
        return {
            "preference_artifact_label": self.preference_artifact_label,
            "source_validation_jsonl": (
                str(self.source_validation_jsonl) if self.source_validation_jsonl is not None else None
            ),
            "input_candidate_count": self.input_candidate_count,
            "f3_available_candidate_count": self.f3_available_candidate_count,
            "disagreement_candidate_count": self.disagreement_candidate_count,
            "caveat": self.caveat,
        }
