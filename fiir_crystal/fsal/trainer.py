"""Training adapter interfaces for FSAL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from fiir_crystal.evaluation import MetricReport
from fiir_crystal.fsal.preference_data import PreferenceDataset


class DPOObjective(str, Enum):
    """Supported DPO objective names."""

    STANDARD_DPO = "standard_dpo"
    CONFIDENCE_WEIGHTED_DPO = "confidence_weighted_dpo"
    MARGIN_DPO = "margin_dpo"
    CW_MARGIN_DPO = "cw_margin_dpo"


@dataclass(slots=True)
class DPOTrainingConfig:
    """Lightweight training configuration placeholder."""

    objective: DPOObjective = DPOObjective.CW_MARGIN_DPO
    beta: float = 0.1
    batch_size: int = 32
    max_epochs: int = 0
    learning_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrainingRunSummary:
    """Summary returned by FSAL trainer adapters."""

    run_id: str
    status: str
    objective: DPOObjective
    pair_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class ModelLogProbAdapter(ABC):
    """Adapter for model log-probability scoring."""

    @abstractmethod
    def score(self, structure_refs: Sequence[str]) -> list[float]:
        """Return sequence-level log probabilities for structures."""


class FSALTrainer(ABC):
    """Skeleton for DPO-style trainers."""

    @abstractmethod
    def fit(
        self,
        dataset: PreferenceDataset,
        policy: ModelLogProbAdapter,
        reference: ModelLogProbAdapter,
        config: DPOTrainingConfig | None = None,
    ) -> TrainingRunSummary:
        """Run or delegate an FSAL training job."""

    def evaluate(self, subject_id: str) -> MetricReport:
        """Optional metric hook for future trainer implementations."""

        return MetricReport(report_id=f"{subject_id}:fsal", scope="fsal", subject_id=subject_id)
