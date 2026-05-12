from fiir_crystal.discovery import (
    AcquisitionScore,
    DiscoveryCandidate,
    RankedCandidate,
    ScreeningDecision,
    ScreeningStatus,
    ValidationTask,
    ValidationTaskType,
)
from fiir_crystal.evaluation import EvaluationMetric, MetricDirection, MetricValue
from fiir_crystal.failure import (
    CandidateRecord,
    FailureAxis,
    FailureLabel,
    FailureLabelBatch,
    FailureScore,
    FailureSeverity,
)
from fiir_crystal.fsal import (
    FailureBucket,
    LabeledCandidate,
    MatchedPairConfig,
    PreferenceAxis,
    PreferenceDataset,
    PreferencePair,
)
from fiir_crystal.generation import GenerationRequest, GenerationResult
from fiir_crystal.predictor import FailurePrediction


def test_failure_dataclasses_can_be_instantiated() -> None:
    candidate = CandidateRecord(sample_id="s1", structure={"mock": True})
    score = FailureScore(
        axis=FailureAxis.F1_GEOMETRY,
        value=0.0,
        unit="unitless",
        severity=FailureSeverity.PASS,
        confidence=1.0,
    )
    label = FailureLabel(
        sample_id=candidate.sample_id,
        structure_ref="mock://s1",
        f1_geometry=0.0,
        f2_chemistry=0.0,
        f3_stability=0.05,
        f4_novelty_leakage=0.0,
        f5_synthesizability=0.2,
        axis_scores=[score],
        calibration_tier=1,
    )
    batch = FailureLabelBatch(labels=[label])

    assert label.is_stable is True
    assert label.f4_novelty_leakage == 0.0
    assert label.f5_synthesizability == 0.2
    assert batch.labels[0].sample_id == "s1"


def test_fsal_dataclasses_can_be_instantiated() -> None:
    label = FailureLabel(
        sample_id="s1",
        structure_ref="mock://s1",
        f1_geometry=0.0,
        f2_chemistry=0.0,
        f3_stability=0.05,
    )
    labeled = LabeledCandidate(
        sample_id="s1",
        structure_ref="mock://s1",
        failure_label=label,
        chemical_bucket="mock_bucket",
        atom_count=5,
    )
    pair = PreferencePair(
        pair_id="p1",
        winner_id="s1",
        loser_id="s2",
        axis=PreferenceAxis.F3_STABILITY,
        failure_bucket=FailureBucket.NEAR_MISS,
        main_axis_gap=0.2,
    )
    dataset = PreferenceDataset(
        dataset_id="d1",
        pairs=[pair],
        candidate_index={labeled.sample_id: labeled},
        config={"pair": MatchedPairConfig().main_axis_threshold},
    )

    assert dataset.pairs[0].axis == PreferenceAxis.F3_STABILITY


def test_generation_predictor_evaluation_and_discovery_dataclasses() -> None:
    candidate = CandidateRecord(sample_id="s1", structure={"mock": True})
    request = GenerationRequest(num_samples=1, seed=7)
    result = GenerationResult(candidates=[candidate], model_id="mock", request=request)
    prediction = FailurePrediction(sample_id="s1", pred_f1=0.1, pred_f2=0.2, pred_f4=0.3, pred_f5=0.4)
    metric = MetricValue(
        name=EvaluationMetric.VALIDITY.value,
        value=1.0,
        direction=MetricDirection.HIGHER_IS_BETTER,
        n=1,
    )
    discovery_candidate = DiscoveryCandidate(
        candidate_id="c1",
        sample_id="s1",
        structure_ref="mock://s1",
    )
    decision = ScreeningDecision(
        layer="failure_predictor",
        adapter_name="mock",
        status=ScreeningStatus.PASS,
    )
    acquisition = AcquisitionScore(utility=0.5, pred_f4=0.3, pred_f5=0.4)
    ranked = RankedCandidate(
        candidate_id="c1",
        acquisition=acquisition,
        pareto_layer=0,
        rank=1,
        selection_reason="test",
    )
    task = ValidationTask(
        task_id="t1",
        candidate_id="c1",
        task_type=ValidationTaskType.DFT_VALIDATION,
        priority=1,
    )

    assert result.candidates[0].sample_id == prediction.sample_id
    assert prediction.pred_f4 == acquisition.pred_f4
    assert prediction.pred_f5 == acquisition.pred_f5
    assert metric.value == 1.0
    assert discovery_candidate.candidate_id == ranked.candidate_id
    assert decision.status is ScreeningStatus.PASS
    assert task.task_type is ValidationTaskType.DFT_VALIDATION
