import pytest

from fiir_crystal.config import load_experiment_config
from fiir_crystal.evaluation import EvaluationReport
from fiir_crystal.experiment import run_fiir_experiment
from fiir_crystal.failure import FailureVector, StructureLike
from fiir_crystal.fsal import PreferenceAxis, PreferencePair
from fiir_crystal.io import JsonlFormatError, read_json, read_jsonl, read_mock_candidates_jsonl, write_jsonl


def test_jsonl_round_trip_candidates(tmp_path) -> None:
    path = tmp_path / "candidates.jsonl"
    candidates = [
        StructureLike(
            candidate_id="c1",
            composition="CaTiO3",
            num_atoms=5,
            lattice_lengths=(3.8, 3.8, 3.8),
            lattice_angles=(90, 90, 90),
            frac_coords=((0, 0, 0), (0.5, 0.5, 0.5)),
        )
    ]

    write_jsonl(path, candidates)
    loaded = read_mock_candidates_jsonl(path)

    assert loaded[0].candidate_id == "c1"
    assert loaded[0].lattice_lengths == (3.8, 3.8, 3.8)


def test_failure_vector_round_trip() -> None:
    vector = FailureVector(
        sample_id="v1",
        structure_ref="mock://v1",
        f1_geometry=0.1,
        f2_chemistry=0.2,
        f3_stability=0.3,
        f4_novelty_leakage=0.4,
        f5_synthesizability=0.5,
        confidence=0.7,
        calibration_tier=2,
        hard_failures=["x"],
        is_valid=False,
    )

    loaded = FailureVector.from_dict(vector.to_dict())

    assert loaded.sample_id == vector.sample_id
    assert loaded.f4_novelty_leakage == 0.4
    assert loaded.f5_synthesizability == 0.5
    assert loaded.hard_failures == ["x"]
    assert loaded.is_valid is False


def test_preference_pair_round_trip() -> None:
    pair = PreferencePair(
        pair_id="p1",
        winner_id="w",
        loser_id="l",
        axis=PreferenceAxis.F1_GEOMETRY,
        margin=0.5,
        label_confidence=0.8,
        reason="test",
        metadata={"mode": "axis_aligned"},
    )

    loaded = PreferencePair.from_dict(pair.to_dict())

    assert loaded.pair_id == "p1"
    assert loaded.axis is PreferenceAxis.F1_GEOMETRY
    assert loaded.confidence == 0.8


def test_invalid_jsonl_error(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(JsonlFormatError):
        read_jsonl(path)


def test_default_config_loads_and_cli_overrides() -> None:
    config = load_experiment_config(
        "configs/mock_fiir_loop.yaml",
        overrides={"top_k": 3, "output_dir": "outputs/override"},
    )

    assert config.input_path == "examples/mock_candidates.jsonl"
    assert config.top_k == 3
    assert config.output_dir == "outputs/override"
    assert config.pair_mining["min_pair_quality"] == 0.05


def test_missing_config_fields_get_defaults(tmp_path) -> None:
    path = tmp_path / "minimal.yaml"
    path.write_text("input_path: examples/mock_candidates.jsonl\n", encoding="utf-8")

    config = load_experiment_config(path)

    assert config.output_dir == "outputs/mock_run"
    assert config.top_k == 5


def test_runner_writes_expected_outputs(tmp_path) -> None:
    output_dir = tmp_path / "run"
    config = load_experiment_config(
        "configs/mock_fiir_loop.yaml",
        overrides={"output_dir": str(output_dir), "top_k": 4},
    )

    result = run_fiir_experiment(config)

    expected = [
        "candidates.jsonl",
        "failure_vectors.jsonl",
        "preference_pairs.jsonl",
        "evaluation_report.json",
        "discovery_ranking.jsonl",
        "feedback_records.jsonl",
        "experiment_summary.json",
        "report.md",
    ]
    assert all((output_dir / name).exists() for name in expected)
    assert result["summary"]["candidate_count"] >= 24
    assert read_json(output_dir / "experiment_summary.json")["feedback_count"] == 4
    report = EvaluationReport.from_dict(read_json(output_dir / "evaluation_report.json"))
    assert report.pair_count > 0
