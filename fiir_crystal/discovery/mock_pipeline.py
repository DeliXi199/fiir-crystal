"""Mock discovery pipeline for the first FIIR minimum-loop demo."""

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
from fiir_crystal.failure import CrystalRecord, MockFailureLabeler


def _normalized_failure(candidate: DiscoveryCandidate) -> float:
    label = candidate.failure_label
    if label is None:
        return 1.0
    f3 = label.f3_stability if label.f3_stability is not None else 1.0
    return (label.f1_geometry + label.f2_chemistry + min(f3, 1.0)) / 3.0


class MockScreeningAdapter(ScreeningAdapter):
    """Pass candidates below a simple aggregate failure threshold."""

    def __init__(self, max_failure_score: float = 0.5) -> None:
        self.max_failure_score = max_failure_score

    def screen(self, candidate: DiscoveryCandidate) -> ScreeningDecision:
        score = _normalized_failure(candidate)
        status = ScreeningStatus.PASS if score <= self.max_failure_score else ScreeningStatus.REJECT
        return ScreeningDecision(
            layer="mock_failure_screen",
            adapter_name=self.__class__.__name__,
            status=status,
            score=score,
            reason="aggregate_failure_below_threshold" if status is ScreeningStatus.PASS else "aggregate_failure_too_high",
            evidence={"max_failure_score": self.max_failure_score},
        )


class MockRanker(Ranker):
    """Rank candidates by success, novelty proxy, diversity proxy, and cost."""

    def rank(self, candidates: Sequence[DiscoveryCandidate]) -> list[RankedCandidate]:
        ranked: list[RankedCandidate] = []
        for candidate in candidates:
            failure = _normalized_failure(candidate)
            success = max(0.0, 1.0 - failure)
            novelty = float(candidate.metadata.get("mock_novelty", 0.5))
            diversity = float(candidate.metadata.get("mock_diversity", 0.5))
            cost = float(candidate.metadata.get("num_atoms", 10)) / 100.0
            utility = 0.5 * success + 0.2 * novelty + 0.2 * diversity - 0.1 * cost
            ranked.append(
                RankedCandidate(
                    candidate_id=candidate.candidate_id,
                    acquisition=AcquisitionScore(
                        utility=utility,
                        success_score=success,
                        novelty_score=novelty,
                        diversity_score=diversity,
                        cost_score=cost,
                        pred_f1=candidate.failure_label.f1_geometry if candidate.failure_label else None,
                        pred_f2=candidate.failure_label.f2_chemistry if candidate.failure_label else None,
                        pred_f3=candidate.failure_label.f3_stability if candidate.failure_label else None,
                    ),
                    pareto_layer=0,
                    rank=0,
                    selection_reason="mock_utility",
                    objectives={"success": success, "novelty": novelty, "diversity": diversity, "cost": cost},
                )
            )

        ranked.sort(key=lambda item: item.acquisition.utility, reverse=True)
        for index, item in enumerate(ranked, start=1):
            item.rank = index
        return ranked


class MockValidationAdapter(ValidationAdapter):
    """Create validation task metadata without running validation."""

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
            )
            for index, candidate in enumerate(candidates[: self.top_k], start=1)
        ]


class MockFeedbackSink(FeedbackSink):
    """Convert mock validation results to feedback records."""

    def record(self, results: Sequence[ValidationResult]) -> list[FeedbackRecord]:
        return [
            FeedbackRecord(
                feedback_id=f"feedback-{result.candidate_id}",
                candidate_id=result.candidate_id,
                validation_results=[result],
                use_for_predictor=True,
                use_for_fsal=True,
                notes="mock feedback",
            )
            for result in results
        ]


class MockDiscoveryPipeline(DiscoveryPipeline):
    """Discovery skeleton that labels, screens, ranks, exports tasks, and feeds back."""

    def __init__(
        self,
        labeler: MockFailureLabeler | None = None,
        screener: ScreeningAdapter | None = None,
        ranker: Ranker | None = None,
        validator: ValidationAdapter | None = None,
        feedback_sink: FeedbackSink | None = None,
        top_k: int = 3,
    ) -> None:
        self.labeler = labeler or MockFailureLabeler()
        self.screener = screener or MockScreeningAdapter()
        self.ranker = ranker or MockRanker()
        self.validator = validator or MockValidationAdapter(top_k=top_k)
        self.feedback_sink = feedback_sink or MockFeedbackSink()
        self.top_k = top_k

    def run_crystals(self, crystals: Sequence[CrystalRecord]) -> DiscoveryRun:
        """Run the mock pipeline directly from mock crystal records."""

        candidates = [self._candidate_from_crystal(crystal) for crystal in crystals]
        return self.run(candidates)

    def run(self, candidates: Sequence[DiscoveryCandidate]) -> DiscoveryRun:
        """Run the mock discovery flow without external services."""

        screened: list[DiscoveryCandidate] = []
        for candidate in candidates:
            if candidate.failure_label is None and "crystal" in candidate.metadata:
                candidate.failure_label = self.labeler.label_crystal(candidate.metadata["crystal"])
            decision = self.screener.screen(candidate)
            candidate.screening_records.append(decision)
            if decision.status is ScreeningStatus.PASS:
                screened.append(candidate)

        ranked = self.ranker.rank(screened)
        top_ranked = ranked[: self.top_k]
        tasks = self.validator.create_tasks(top_ranked)
        results = [
            ValidationResult(
                task_id=task.task_id,
                candidate_id=task.candidate_id,
                result_type="mock_selected",
                value=True,
                confidence=1.0,
                provenance={"pipeline": self.__class__.__name__},
            )
            for task in tasks
        ]
        feedback = self.feedback_sink.record(results)

        return DiscoveryRun(
            run_id="mock-discovery",
            candidates=list(candidates),
            ranked_candidates=ranked,
            validation_tasks=tasks,
            feedback_records=feedback,
            metadata={
                "input_count": len(candidates),
                "screened_count": len(screened),
                "top_k": self.top_k,
            },
        )

    def _candidate_from_crystal(self, crystal: CrystalRecord) -> DiscoveryCandidate:
        label = self.labeler.label_crystal(crystal)
        return DiscoveryCandidate(
            candidate_id=crystal.sample_id,
            sample_id=crystal.sample_id,
            structure_ref=crystal.structure_ref,
            source_model="mock",
            failure_label=label,
            predicted_failure={
                "f1": label.f1_geometry,
                "f2": label.f2_chemistry,
                "f3": label.f3_stability,
            },
            metadata={
                "crystal": crystal,
                "composition": crystal.composition,
                "num_atoms": crystal.num_atoms,
                "space_group": crystal.space_group,
                "prototype": crystal.prototype,
                "mock_novelty": crystal.metadata.get("mock_novelty", 0.5),
                "mock_diversity": crystal.metadata.get("mock_diversity", 0.5),
            },
        )
