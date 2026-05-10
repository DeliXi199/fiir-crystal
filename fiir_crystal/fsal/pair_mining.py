"""Pair-mining interfaces for FSAL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from fiir_crystal.fsal.preference_data import (
    LabeledCandidate,
    MatchedPairConfig,
    PreferenceDataset,
)


@dataclass(slots=True)
class PairMiningSummary:
    """Audit summary for a pair-mining run."""

    candidate_count: int = 0
    accepted_pair_count: int = 0
    rejected_pair_count: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


class MatchedAxisAlignedPairMiner(ABC):
    """Contract for matched axis-aligned preference-pair mining."""

    @abstractmethod
    def mine(
        self,
        candidates: Sequence[LabeledCandidate],
        config: MatchedPairConfig | None = None,
    ) -> PreferenceDataset:
        """Build a preference dataset from labeled candidates."""
