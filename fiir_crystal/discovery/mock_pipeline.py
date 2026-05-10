"""Mock active discovery loop for lightweight FIIR-v1."""

from __future__ import annotations

from typing import Sequence

from fiir_crystal.discovery.interfaces import (
    DiscoveryPipeline,
    FeedbackSink,
    Ranker,
    ScreeningAdapter,
    ValidationAdapter,
)
from fiir_crystal.discovery.records import (
    AcquisitionScore,
    BudgetTier,
    DiscoveryCandidate,
    DiscoveryRun,
    FeedbackRecord,
    RankedCandidate,
    ScreeningDecision,
    ScreeningStatus,
    ValidationResult,
    ValidationTask,
    ValidationTaskType,
)
from fiir_crystal.failure import CrystalRecord, FailureOracle, FailureVector, StructureLike


def _vector(candidate: DiscoveryCandidate) -> FailureVector | None:
    return candidate.failure_vector


def _normalized_failure(candidate: DiscoveryCandidate) -> float:
    vector = _vector(candidate)
    if vector is None:
        return 1.0
    f3 = vector.f3_stability if vector.f3_stability is not None else 1.0
    return (vector.f1_geometry + vector.f2_chemistry + min(f3, 1.0)) / 3.0


class MockScreeningAdapter(ScreeningAdapter):
    """Pass valid candidates below a simple aggregate failure threshold."""

    def __init__(self, max_failure_score: float = 0.55) -> None:
        self.max_failure_score = max_failure_score

    def screen(self, candidate: DiscoveryCandidate) -> ScreeningDecision:
        vector = _vector(candidate)
        score = _normalized_failure(candidate)
        is_valid = vector.is_valid if vector is not None else False
        status = ScreeningStatus.PASS if is_valid and score <= self.max_failure_score else ScreeningStatus.REJECT
        reason = "valid_low_failure" if status is ScreeningStatus.PASS else "invalid_or_high_failure"
        return ScreeningDecision(
            layer="mock_failure_oracle_screen",
            adapter_name=self.__class__.__name__,
            status=status,
            score=score,
            reason=reason,
            evidence={
                "max_failure_score": self.max_failure_score,
                "is_valid": is_valid,
                "hard_failures": vector.hard_failures if vector else ["missing_failure_vector"],
            },
        )


class MockRanker(Ranker):
    """Utility-style ranking over failure, confidence, validity, novelty, and diversity."""

    def __init__(
        self,
        mode: str = "utility",
        weights: dict[str, float] | None = None,
        allow_invalid: bool = False,
    ) -> None:
        self.mode = mode
        self.weights = weights or {
            "success": 0.4,
            "confidence": 0.2,
            "validity": 0.15,
            "novelty": 0.15,
            "diversity": 0.1,
            "cost": 0.05,
        }
        self.allow_invalid = allow_invalid

    def rank(self, candidates: Sequence[DiscoveryCandidate]) -> list[RankedCandidate]:
        candidates_to_rank = list(candidates if self.allow_invalid else [candidate for candidate in candidates if (_vector(candidate) and _vector(candidate).is_valid)])
        ranked: list[RankedCandidate] = []
        for candidate in candidates_to_rank:
            vector = _vector(candidate)
            failure = _normalized_failure(candidate)
            success = max(0.0, 1.0 - failure)
            confidence = vector.confidence if vector is not None else 0.0
            validity = 1.0 if vector is not None and vector.is_valid else 0.0
            novelty = float(candidate.metadata.get("mock_novelty", 0.5))
            diversity = float(candidate.metadata.get("mock_diversity", 0.5))
            cost = float(candidate.metadata.get("num_atoms", 10)) / 100.0
            utility = self._utility(success, confidence, validity, novelty, diversity, cost)
            ranked.append(
                RankedCandidate(
                    candidate_id=candidate.candidate_id,
                    acquisition=AcquisitionScore(
                        utility=utility,
                        success_score=success,
                        novelty_score=novelty,
                        diversity_score=diversity,
                        uncertainty_bonus=1.0 - confidence,
                        cost_score=cost,
                        pred_f1=vector.f1_geometry if vector else None,
                        pred_f2=vector.f2_chemistry if vector else None,
                        pred_f3=vector.f3_stability if vector else None,
                    ),
                    pareto_layer=0,
                    rank=0,
                    selection_reason=f"mock_fiir_{self.mode}",
                    objectives={
                        "success": success,
                        "confidence": confidence,
                        "validity": validity,
                        "novelty": novelty,
                        "diversity": diversity,
                        "cost": cost,
                    },
                )
            )

        if self.mode == "pareto":
            ranked = self._pareto_rank(ranked)
        else:
            ranked.sort(key=lambda item: item.acquisition.utility, reverse=True)
        for index, item in enumerate(ranked, start=1):
            item.rank = index
        return ranked

    def _utility(
        self,
        success: float,
        confidence: float,
        validity: float,
        novelty: float,
        diversity: float,
        cost: float,
    ) -> float:
        return (
            self.weights.get("success", 0.4) * success
            + self.weights.get("confidence", 0.2) * confidence
            + self.weights.get("validity", 0.15) * validity
            + self.weights.get("novelty", 0.15) * novelty
            + self.weights.get("diversity", 0.1) * diversity
            - self.weights.get("cost", 0.05) * cost
        )

    def _pareto_rank(self, ranked: list[RankedCandidate]) -> list[RankedCandidate]:
        remaining = list(ranked)
        layered: list[RankedCandidate] = []
        layer = 0
        while remaining:
            front: list[RankedCandidate] = []
            for candidate in remaining:
                if not any(self._dominates(other, candidate) for other in remaining if other is not candidate):
                    front.append(candidate)
            for candidate in front:
                candidate.pareto_layer = layer
            front.sort(key=lambda item: item.acquisition.utility, reverse=True)
            layered.extend(front)
            remaining = [candidate for candidate in remaining if candidate not in front]
            layer += 1
        return layered

    def _dominates(self, left: RankedCandidate, right: RankedCandidate) -> bool:
        objective_keys = ["success", "confidence", "validity", "novelty", "diversity"]
        ge_all = all(left.objectives.get(key, 0.0) >= right.objectives.get(key, 0.0) for key in objective_keys)
        gt_any = any(left.objectives.get(key, 0.0) > right.objectives.get(key, 0.0) for key in objective_keys)
        cost_le = left.objectives.get("cost", 1.0) <= right.objectives.get("cost", 1.0)
        cost_lt = left.objectives.get("cost", 1.0) < right.objectives.get("cost", 1.0)
        return ge_all and cost_le and (gt_any or cost_lt)


class MockValidationAdapter(ValidationAdapter):
    """Create validation task metadata without running external validation."""

    def __init__(self, top_k: int = 3) -> None:
        self.top_k = top_k

    def create_tasks(self, candidates: Sequence[RankedCandidate]) -> list[ValidationTask]:
        return [
            ValidationTask(
                task_id=f"mock-validation-{candidate.candidate_id}",
                candidate_id=candidate.candidate_id,
                task_type=ValidationTaskType.NOVELTY_CHECK,
                priority=index,
                budget_tier=BudgetTier.CHEAP,
                requested_inputs={"rank": candidate.rank, "utility": candidate.acquisition.utility},
                metadata={"decision": "selected_for_mock_feedback"},
            )
            for index, candidate in enumerate(candidates[: self.top_k], start=1)
        ]


class MockFeedbackSink(FeedbackSink):
    """Convert mock validation results to feedback records."""

    def record(self, results: Sequence[ValidationResult]) -> list[FeedbackRecord]:
        records: list[FeedbackRecord] = []
        for result in results:
            records.append(
                FeedbackRecord(
                    feedback_id=f"feedback-{result.candidate_id}",
                    candidate_id=result.candidate_id,
                    validation_results=[result],
                    use_for_predictor=True,
                    use_for_fsal=True,
                    notes="mock feedback",
                    selected_rank=result.provenance.get("selected_rank"),
                    failure_vector=result.provenance.get("failure_vector"),
                    decision=str(result.provenance.get("decision", "selected")),
                    reason=str(result.provenance.get("reason", "top_k_mock_ranking")),
                    metadata=dict(result.provenance),
                )
            )
        return records


class MockDiscoveryPipeline(DiscoveryPipeline):
    """Discovery skeleton: oracle labeling -> screening -> ranking -> feedback."""

    def __init__(
        self,
        oracle: FailureOracle | None = None,
        screener: ScreeningAdapter | None = None,
        ranker: Ranker | None = None,
        validator: ValidationAdapter | None = None,
        feedback_sink: FeedbackSink | None = None,
        top_k: int = 3,
        ranking_mode: str = "utility",
        ranking_weights: dict[str, float] | None = None,
        allow_invalid: bool = False,
    ) -> None:
        self.oracle = oracle or FailureOracle.default()
        self.screener = screener or MockScreeningAdapter()
        self.ranker = ranker or MockRanker(mode=ranking_mode, weights=ranking_weights, allow_invalid=allow_invalid)
        self.validator = validator or MockValidationAdapter(top_k=top_k)
        self.feedback_sink = feedback_sink or MockFeedbackSink()
        self.top_k = top_k
        self.ranking_mode = ranking_mode

    def run_structures(self, structures: Sequence[StructureLike]) -> DiscoveryRun:
        """Run the mock pipeline directly from lightweight structures."""

        candidates = [self._candidate_from_structure(structure) for structure in structures]
        return self.run(candidates)

    def run_crystals(self, crystals: Sequence[CrystalRecord]) -> DiscoveryRun:
        """Backward-compatible alias for older demo code."""

        return self.run_structures(crystals)

    def run(self, candidates: Sequence[DiscoveryCandidate]) -> DiscoveryRun:
        """Run the mock discovery flow without external services."""

        prepared = [self._ensure_labeled(candidate) for candidate in candidates]
        screened: list[DiscoveryCandidate] = []
        for candidate in prepared:
            decision = self.screener.screen(candidate)
            candidate.screening_records.append(decision)
            if decision.status is ScreeningStatus.PASS:
                screened.append(candidate)

        ranked = self.ranker.rank(screened)
        top_ranked = ranked[: self.top_k]
        tasks = self.validator.create_tasks(top_ranked)
        candidate_index = {candidate.candidate_id: candidate for candidate in prepared}
        rank_index = {candidate.candidate_id: candidate for candidate in top_ranked}
        results = [
            ValidationResult(
                task_id=task.task_id,
                candidate_id=task.candidate_id,
                result_type="mock_selected",
                value=True,
                confidence=1.0,
                provenance={
                    "pipeline": self.__class__.__name__,
                    "selected_rank": rank_index[task.candidate_id].rank,
                    "failure_vector": candidate_index[task.candidate_id].failure_vector,
                    "decision": "selected",
                    "reason": "top_k_mock_ranking",
                    "ranking_mode": self.ranking_mode,
                    "utility": rank_index[task.candidate_id].acquisition.utility,
                },
            )
            for task in tasks
        ]
        feedback = self.feedback_sink.record(results)

        return DiscoveryRun(
            run_id="mock-discovery",
            candidates=prepared,
            ranked_candidates=ranked,
            validation_tasks=tasks,
            feedback_records=feedback,
            metadata={
                "input_count": len(prepared),
                "screened_count": len(screened),
                "top_k": self.top_k,
                "ranking_mode": self.ranking_mode,
            },
        )

    def _candidate_from_structure(self, structure: StructureLike) -> DiscoveryCandidate:
        vector = self.oracle.vectorize(structure)
        label = self.oracle.label_structure(structure)
        return DiscoveryCandidate(
            candidate_id=structure.candidate_id,
            sample_id=structure.sample_id,
            structure_ref=structure.structure_ref,
            source_model="mock",
            failure_label=label,
            failure_vector=vector,
            predicted_failure={
                "f1": vector.f1_geometry,
                "f2": vector.f2_chemistry,
                "f3": vector.f3_stability,
            },
            metadata={
                "structure": structure,
                "composition": structure.composition,
                "num_atoms": structure.num_atoms,
                "space_group": structure.space_group,
                "prototype": structure.prototype,
                "mock_novelty": structure.metadata.get("mock_novelty", 0.5),
                "mock_diversity": structure.metadata.get("mock_diversity", 0.5),
            },
        )

    def _ensure_labeled(self, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        if candidate.failure_vector is None and "structure" in candidate.metadata:
            structure = candidate.metadata["structure"]
            candidate.failure_vector = self.oracle.vectorize(structure)
            candidate.failure_label = self.oracle.label_structure(structure)
        return candidate
