from fiir_crystal.discovery import MockDiscoveryPipeline
from fiir_crystal.evaluation import evaluate_mock_fiir_loop
from fiir_crystal.failure import (
    ChemistryFailureLabeler,
    FailureOracle,
    GeometryFailureLabeler,
    MockFailureLabeler,
    StabilityFailureLabeler,
    StructureLike,
    demo_mock_crystals,
)
from fiir_crystal.fsal import AxisAlignedPairMiner, LabeledCandidate, MatchedPairConfig
from scripts.run_mock_fiir_loop import build_labeled_candidates


def _good_structure(candidate_id: str = "good") -> StructureLike:
    return StructureLike(
        candidate_id=candidate_id,
        composition="CaTiO3",
        num_atoms=5,
        space_group=221,
        prototype="perovskite",
        mock_geometry_score=0.02,
        mock_chemistry_score=0.03,
        mock_stability_score=0.04,
        lattice_lengths=(3.8, 3.8, 3.8),
        lattice_angles=(90.0, 90.0, 90.0),
        frac_coords=(
            (0.0, 0.0, 0.0),
            (0.5, 0.5, 0.5),
            (0.5, 0.5, 0.0),
            (0.5, 0.0, 0.5),
            (0.0, 0.5, 0.5),
        ),
    )


def test_structure_like_creation_and_aliases() -> None:
    structure = _good_structure("alias")

    assert structure.candidate_id == "alias"
    assert structure.sample_id == "alias"
    assert structure.structure_ref == "mock://alias"
    assert structure.chemical_bucket == "perovskite"


def test_geometry_labeler_normal_structure_low_score() -> None:
    result = GeometryFailureLabeler().label_structure(_good_structure())

    assert result.f1_geometry < 0.1
    assert result.hard_failed is False


def test_geometry_labeler_close_atoms_high_score() -> None:
    structure = _good_structure("close")
    structure.frac_coords = (
        (0.0, 0.0, 0.0),
        (0.01, 0.01, 0.01),
        (0.5, 0.5, 0.0),
        (0.5, 0.0, 0.5),
        (0.0, 0.5, 0.5),
    )

    result = GeometryFailureLabeler().label_structure(structure)

    assert result.f1_geometry > 0.7
    assert result.hard_failed is False


def test_geometry_labeler_abnormal_lattice_high_score() -> None:
    structure = _good_structure("bad_lattice")
    structure.lattice_angles = (5.0, 90.0, 90.0)

    result = GeometryFailureLabeler().label_structure(structure)

    assert result.f1_geometry > 0.7


def test_chemistry_labeler_uses_mock_score() -> None:
    structure = _good_structure("chem")
    structure.mock_chemistry_score = 0.42

    result = ChemistryFailureLabeler().label_structure(structure)

    assert result.f2_chemistry == 0.42
    assert result.hard_failed is False


def test_stability_labeler_uses_mock_score() -> None:
    structure = _good_structure("stable")
    structure.mock_stability_score = 0.37

    result = StabilityFailureLabeler().label_structure(structure)

    assert result.f3_stability == 0.37


def test_failure_oracle_outputs_vector_and_rule_based_tier() -> None:
    oracle = FailureOracle.default()

    vector = oracle.vectorize(_good_structure("oracle"))

    assert vector.is_valid is True
    assert vector.hard_failures == []
    assert vector.calibration_tier == 3
    assert vector.confidence == 0.5


def test_failure_oracle_invalid_structure_gets_tier_zero() -> None:
    invalid = StructureLike(
        candidate_id="invalid",
        composition="",
        num_atoms=0,
        lattice_lengths=None,
        lattice_angles=None,
        frac_coords=None,
    )

    vector = FailureOracle.default().vectorize(invalid)

    assert vector.is_valid is False
    assert vector.calibration_tier == 0
    assert vector.hard_failures


def test_mock_failure_labeler_preserves_mock_only_tier() -> None:
    vector = MockFailureLabeler().vectorize(_good_structure("mock_only"))

    assert vector.calibration_tier == 4
    assert vector.confidence == 0.2


def test_failure_oracle_passes_through_optional_f4_f5() -> None:
    structure = _good_structure("with_f4_f5")
    structure.metadata["f4_novelty_leakage"] = 0.25
    structure.metadata["f5_synthesizability"] = 0.35

    vector = FailureOracle.default().vectorize(structure)
    label = FailureOracle.default().label_structure(structure)

    assert vector.f4_novelty_leakage == 0.25
    assert vector.f5_synthesizability == 0.35
    assert label.f4_novelty_leakage == 0.25
    assert label.f5_synthesizability == 0.35


def test_pair_mining_generates_all_axes_and_respects_constraints() -> None:
    oracle = FailureOracle.default()
    candidates = build_labeled_candidates(oracle, demo_mock_crystals())

    dataset = AxisAlignedPairMiner().mine(candidates, config=MatchedPairConfig(min_pair_quality=0.05))

    assert {pair.axis.value for pair in dataset.pairs} >= {
        "F1_GEOMETRY",
        "F2_CHEMISTRY",
        "F3_STABILITY",
    }
    assert all(pair.match_metadata["same_prototype"] for pair in dataset.pairs)
    assert all(pair.match_metadata["atom_count_delta"] == 0 for pair in dataset.pairs)
    assert all(pair.reason.startswith("axis_aligned_") for pair in dataset.pairs)


def test_pair_mining_num_atom_tolerance_blocks_mismatch() -> None:
    oracle = FailureOracle.default()
    winner = _good_structure("small")
    loser = _good_structure("large")
    loser.num_atoms = 10
    loser.frac_coords = tuple((0.1 * i, 0.1 * i, 0.1 * i) for i in range(10))
    loser.mock_geometry_score = 0.8
    candidates = build_labeled_candidates(oracle, [winner, loser])

    dataset = AxisAlignedPairMiner().mine(
        candidates,
        config=MatchedPairConfig(min_pair_quality=0.0, atom_count_tolerance=0.1),
    )

    assert dataset.pairs == []
    assert dataset.stats["rejection_reasons"]["metadata_mismatch"] >= 1


def test_pair_mining_can_filter_high_f4_leakage() -> None:
    oracle = FailureOracle.default()
    winner = _good_structure("winner")
    loser = _good_structure("leaky_loser")
    loser.mock_geometry_score = 0.8
    loser.metadata["f4_novelty_leakage"] = 0.9
    candidates = build_labeled_candidates(oracle, [winner, loser])

    dataset = AxisAlignedPairMiner().mine(
        candidates,
        config=MatchedPairConfig(min_pair_quality=0.0, max_f4_leakage=0.5),
    )

    assert dataset.pairs == []
    assert dataset.stats["rejection_reasons"]["f4_leakage_filter"] >= 1


def test_evaluation_report_contains_extended_metrics() -> None:
    oracle = FailureOracle.default()
    candidates = build_labeled_candidates(oracle, demo_mock_crystals())
    labels = [candidate.failure_label for candidate in candidates]
    pairs = AxisAlignedPairMiner().mine(candidates, config=MatchedPairConfig(min_pair_quality=0.05)).pairs

    report = evaluate_mock_fiir_loop(labels, pairs)

    assert report.valid_rate == 1.0
    assert report.max_f3 == 0.72
    assert report.calibration_tier_distribution == {3: 7}
    assert report.average_pair_confidence > 0


def test_mock_discovery_pipeline_uses_oracle_and_feedback_fields() -> None:
    run = MockDiscoveryPipeline(top_k=2).run_structures(demo_mock_crystals())

    assert len(run.feedback_records) == 2
    assert run.feedback_records[0].selected_rank == 1
    assert run.feedback_records[0].failure_vector is not None
    assert run.feedback_records[0].decision == "selected"


def test_demo_build_labeled_candidates_helper() -> None:
    candidates = build_labeled_candidates(FailureOracle.default(), demo_mock_crystals())

    assert candidates[0].failure_vector is not None
    assert candidates[0].failure_label.sample_id == candidates[0].sample_id
