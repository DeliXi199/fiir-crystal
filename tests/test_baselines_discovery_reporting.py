from fiir_crystal.config import ExperimentConfig
from fiir_crystal.discovery import MockDiscoveryPipeline
from fiir_crystal.experiment import build_labeled_candidates
from fiir_crystal.failure import FailureOracle, StructureLike, demo_mock_crystals
from fiir_crystal.fsal import MatchedPairConfig, build_preference_dataset
from fiir_crystal.reporting import render_experiment_report


def _baseline_candidates():
    oracle = FailureOracle.default()
    structures = [
        StructureLike(
            candidate_id="f1_bad",
            composition="CaTiO3",
            num_atoms=5,
            space_group=221,
            prototype="perovskite",
            lattice_lengths=(4, 4, 4),
            lattice_angles=(90, 90, 90),
            frac_coords=((0, 0, 0), (0.5, 0.5, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)),
            mock_geometry_score=0.5,
            mock_chemistry_score=0.0,
            mock_stability_score=0.0,
        ),
        StructureLike(
            candidate_id="f3_bad",
            composition="SrTiO3",
            num_atoms=5,
            space_group=221,
            prototype="perovskite",
            lattice_lengths=(4, 4, 4),
            lattice_angles=(90, 90, 90),
            frac_coords=((0, 0, 0), (0.5, 0.5, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)),
            mock_geometry_score=0.0,
            mock_chemistry_score=0.0,
            mock_stability_score=0.5,
        ),
        StructureLike(
            candidate_id="good",
            composition="BaTiO3",
            num_atoms=5,
            space_group=221,
            prototype="perovskite",
            lattice_lengths=(4, 4, 4),
            lattice_angles=(90, 90, 90),
            frac_coords=((0, 0, 0), (0.5, 0.5, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)),
            mock_geometry_score=0.0,
            mock_chemistry_score=0.0,
            mock_stability_score=0.0,
        ),
    ]
    return build_labeled_candidates(oracle, structures)


def test_all_pair_modes_run() -> None:
    candidates = build_labeled_candidates(FailureOracle.default(), demo_mock_crystals())
    config = MatchedPairConfig(min_pair_quality=0.0)

    for mode in ["axis_aligned", "weighted_sum", "random_negative", "binary_success_failure"]:
        dataset = build_preference_dataset(candidates, mode=mode, config=config, seed=123)
        assert dataset.pairs
        assert all(pair.metadata["mode"] == mode for pair in dataset.pairs)


def test_random_negative_seed_is_reproducible() -> None:
    candidates = build_labeled_candidates(FailureOracle.default(), demo_mock_crystals())
    config = MatchedPairConfig(min_pair_quality=0.0)

    first = build_preference_dataset(candidates, mode="random_negative", config=config, seed=5).pairs
    second = build_preference_dataset(candidates, mode="random_negative", config=config, seed=5).pairs

    assert [pair.pair_id for pair in first] == [pair.pair_id for pair in second]


def test_weighted_sum_weights_change_winner() -> None:
    candidates = _baseline_candidates()
    config = MatchedPairConfig(min_pair_quality=0.0, main_axis_threshold=0.1)

    f1_dataset = build_preference_dataset(candidates, mode="weighted_sum", config=config, weighted_sum_weights={"f1": 5, "f2": 0, "f3": 1})
    f3_dataset = build_preference_dataset(candidates, mode="weighted_sum", config=config, weighted_sum_weights={"f1": 1, "f2": 0, "f3": 5})
    f1_pair = next(pair for pair in f1_dataset.pairs if {pair.winner_id, pair.loser_id} == {"f1_bad", "f3_bad"})
    f3_pair = next(pair for pair in f3_dataset.pairs if {pair.winner_id, pair.loser_id} == {"f1_bad", "f3_bad"})

    assert f1_pair.winner_id != f3_pair.winner_id


def test_axis_aligned_respects_space_group_matching() -> None:
    candidates = build_labeled_candidates(FailureOracle.default(), demo_mock_crystals())
    strict = build_preference_dataset(
        candidates,
        mode="axis_aligned",
        config=MatchedPairConfig(min_pair_quality=0.0, require_space_group_match=True),
    )

    assert strict.pairs
    assert all(pair.match_metadata["same_space_group"] for pair in strict.pairs)


def test_discovery_utility_and_pareto_ranking() -> None:
    structures = demo_mock_crystals()

    utility_run = MockDiscoveryPipeline(top_k=3, ranking_mode="utility").run_structures(structures)
    pareto_run = MockDiscoveryPipeline(top_k=3, ranking_mode="pareto").run_structures(structures)

    assert utility_run.ranked_candidates[0].rank == 1
    assert pareto_run.ranked_candidates[0].pareto_layer == 0
    assert all(record.failure_vector is not None for record in utility_run.feedback_records)


def test_invalid_candidates_not_ranked_first_by_default() -> None:
    invalid = StructureLike(candidate_id="invalid", composition="", num_atoms=0)
    structures = [invalid, *demo_mock_crystals()]

    run = MockDiscoveryPipeline(top_k=3).run_structures(structures)

    assert run.ranked_candidates[0].candidate_id != "invalid"


def test_markdown_report_contains_sections_and_empty_state() -> None:
    config = ExperimentConfig().to_dict()
    report = render_experiment_report(
        summary={"candidate_count": 0},
        config=config,
        evaluation_report=None,
        ranked_candidates=[],
        feedback_records=[],
    )

    assert "## Experiment Config Summary" in report
    assert "## Top-K Candidates" in report
    assert "No ranked candidates" in report
