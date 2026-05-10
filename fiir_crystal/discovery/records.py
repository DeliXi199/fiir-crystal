"""Dataclasses for the discovery pipeline skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fiir_crystal.evaluation import MetricReport
from fiir_crystal.failure import FailureLabel, FailureVector


class ScreeningStatus(str, Enum):
    """Screening decision status."""

    PASS = "pass"
    REJECT = "reject"
    DEFER = "defer"
    UNAVAILABLE = "unavailable"


class ValidationTaskType(str, Enum):
    """Validation task categories."""

    MLIP_VALIDATION = "mlip_validation"
    DFT_VALIDATION = "dft_validation"
    NOVELTY_CHECK = "novelty_check"
    SYNTHESIZABILITY_CHECK = "synthesizability_check"


class ValidationTaskStatus(str, Enum):
    """Lifecycle status for validation tasks."""

    PLANNED = "planned"
    EXPORTED = "exported"
    COMPLETED_OFFLINE = "completed_offline"
    FAILED_OFFLINE = "failed_offline"


class BudgetTier(str, Enum):
    """Coarse validation cost tier."""

    CHEAP = "cheap"
    MEDIUM = "medium"
    EXPENSIVE = "expensive"


@dataclass(slots=True)
class AcquisitionScore:
    """Acquisition score used for active discovery."""

    utility: float
    success_score: float = 0.0
    novelty_score: float = 0.0
    diversity_score: float = 0.0
    uncertainty_bonus: float = 0.0
    cost_score: float = 0.0
    pred_f1: float | None = None
    pred_f2: float | None = None
    pred_f3: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScreeningDecision:
    """Decision from a screening adapter."""

    layer: str
    adapter_name: str
    status: ScreeningStatus
    score: float | None = None
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DiscoveryCandidate:
    """Candidate record inside the discovery pipeline."""

    candidate_id: str
    sample_id: str
    structure_ref: str
    source_model: str | None = None
    round_id: str | None = None
    failure_label: FailureLabel | None = None
    failure_vector: FailureVector | None = None
    predicted_failure: dict[str, Any] | None = None
    screening_records: list[ScreeningDecision] = field(default_factory=list)
    ranking_record: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RankedCandidate:
    """Candidate with multi-objective ranking metadata."""

    candidate_id: str
    acquisition: AcquisitionScore
    pareto_layer: int
    rank: int
    selection_reason: str
    objectives: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationTask:
    """Planned validation task metadata; this does not run validation."""

    task_id: str
    candidate_id: str
    task_type: ValidationTaskType
    priority: int
    requested_inputs: dict[str, Any] = field(default_factory=dict)
    budget_tier: BudgetTier = BudgetTier.CHEAP
    status: ValidationTaskStatus = ValidationTaskStatus.PLANNED
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationResult:
    """Offline validation result imported into FIIR."""

    task_id: str
    candidate_id: str
    result_type: str
    value: Any
    unit: str | None = None
    confidence: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FeedbackRecord:
    """Feedback record for predictor or FSAL refresh."""

    feedback_id: str
    candidate_id: str
    validation_results: list[ValidationResult] = field(default_factory=list)
    updated_failure_label: FailureLabel | None = None
    use_for_predictor: bool = False
    use_for_fsal: bool = False
    notes: str = ""
    selected_rank: int | None = None
    failure_vector: FailureVector | None = None
    decision: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DiscoveryRun:
    """Complete discovery run record."""

    run_id: str
    candidates: list[DiscoveryCandidate] = field(default_factory=list)
    ranked_candidates: list[RankedCandidate] = field(default_factory=list)
    validation_tasks: list[ValidationTask] = field(default_factory=list)
    feedback_records: list[FeedbackRecord] = field(default_factory=list)
    metric_reports: list[MetricReport] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
