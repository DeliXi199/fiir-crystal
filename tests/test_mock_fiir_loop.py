from fiir_crystal.discovery import MockDiscoveryPipeline
from fiir_crystal.evaluation import evaluate_mock_fiir_loop
from fiir_crystal.failure import MockFailureLabeler, demo_mock_crystals
from fiir_crystal.fsal import AxisAlignedPairMiner, LabeledCandidate, MatchedPairConfig


def _labeled_candidates():
    crystals = demo_mock_crystals()
    labeler = MockFailureLabeler()
    labels = {label.sample_id: label for label in labeler.label_crystals(crystals).labels}
    return crystals, labeler, [
        LabeledCandidate(
            sample_id=crystal.sample_id,
            structure_ref=crystal.structure_ref,
            failure_label=labels[crystal.sample_id],
            chemical_bucket=crystal.chemical_bucket,
            atom_count=crystal.num_atoms,
            space_group=crystal.space_group,
            prototype=crystal.prototype,
        )
        for crystal in crystals
    ]


def test_mock_failure_labeler_generates_failure_vector_and_label() -> None:
    crystal = demo_mock_crystals()[0]
    labeler = MockFailureLabeler()

    vector = labeler.vectorize(crystal)
    label = labeler.label_crystal(crystal)

    assert vector.sample_id == crystal.sample_id
    assert vector.f1_geometry == crystal.mock_geometry_score
    assert label.f3_stability == crystal.mock_stability_score
    assert label.is_stable is True


def test_axis_aligned_pair_miner_generates_pairs() -> None:
    _, _, candidates = _labeled_candidates()
    miner = AxisAlignedPairMiner()

    dataset = miner.mine(candidates, config=MatchedPairConfig(min_pair_quality=0.05))

    assert dataset.pairs
    assert {pair.axis.value for pair in dataset.pairs} >= {
        "F1_GEOMETRY",
        "F2_CHEMISTRY",
        "F3_STABILITY",
    }
    assert all(pair.winner_id != pair.loser_id for pair in dataset.pairs)
    assert all(pair.confidence > 0 for pair in dataset.pairs)


def test_evaluation_report_counts_pairs_and_axes() -> None:
    _, labeler, candidates = _labeled_candidates()
    labels = labeler.label_crystals(demo_mock_crystals()).labels
    dataset = AxisAlignedPairMiner().mine(candidates, config=MatchedPairConfig(min_pair_quality=0.05))

    report = evaluate_mock_fiir_loop(labels, dataset.pairs)

    assert report.candidate_count == len(labels)
    assert report.pair_count == len(dataset.pairs)
    assert report.failure_rate > 0
    assert report.pairs_by_axis["F1_GEOMETRY"] >= 1


def test_mock_discovery_pipeline_outputs_top_k_and_feedback() -> None:
    crystals = demo_mock_crystals()
    pipeline = MockDiscoveryPipeline(top_k=2)

    run = pipeline.run_crystals(crystals)

    assert run.ranked_candidates
    assert len(run.validation_tasks) == 2
    assert len(run.feedback_records) == 2
    assert run.metadata["input_count"] == len(crystals)
