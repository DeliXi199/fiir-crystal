import subprocess
import sys

import pytest

from fiir_crystal.comparison import (
    aggregate_experiments,
    compare_pair_modes,
    load_experiment_summary,
    render_aggregate_table,
)
from fiir_crystal.config import load_experiment_config
from fiir_crystal.evaluation import evaluate_mock_fiir_loop
from fiir_crystal.experiment import build_labeled_candidates
from fiir_crystal.failure import FailureOracle, demo_mock_crystals
from fiir_crystal.feedback import FeedbackBuffer, run_mock_active_loop
from fiir_crystal.reporting import (
    render_active_loop_report,
    render_aggregate_report,
    render_pair_mode_comparison_report,
)
from fiir_crystal.validation import (
    ValidationResult,
    join_validation_to_rankings,
    read_validation_results_jsonl,
    write_validation_results_jsonl,
)


def _validation_results():
    return [
        ValidationResult(
            candidate_id="geo_good",
            validation_source="offline_mock",
            status="completed",
            validated=True,
            is_stable=True,
            e_above_hull=0.02,
            novelty_label="novel",
        ),
        ValidationResult(
            candidate_id="stable_bad",
            validation_source="offline_mock",
            status="completed",
            validated=True,
            is_stable=False,
            e_above_hull=0.4,
            novelty_label="known",
        ),
        ValidationResult(
            candidate_id="chem_good",
            validation_source="offline_mock",
            status="failed",
            validated=False,
            error_message="mock failure",
        ),
    ]


def test_validation_result_round_trip_and_join(tmp_path) -> None:
    path = tmp_path / "validation_results.jsonl"
    write_validation_results_jsonl(path, _validation_results())

    loaded = read_validation_results_jsonl(path)
    assert loaded[0].candidate_id == "geo_good"
    assert loaded[0].succeeded is True
    assert loaded[2].succeeded is False

    ranked = FailureOracle.default()
    run = __import__("fiir_crystal.discovery", fromlist=["MockDiscoveryPipeline"]).MockDiscoveryPipeline(
        oracle=ranked,
        top_k=2,
    ).run_structures(demo_mock_crystals())
    joined = join_validation_to_rankings(run.ranked_candidates, loaded)

    assert all("validation_result" in row for row in joined)


def test_validation_result_requires_candidate_id() -> None:
    with pytest.raises(ValueError, match="candidate_id"):
        ValidationResult.from_dict({"status": "completed"})


def test_validation_aware_evaluation_metrics() -> None:
    oracle = FailureOracle.default()
    structures = demo_mock_crystals()
    labels = [oracle.label_structure(structure) for structure in structures]
    candidates = build_labeled_candidates(oracle, structures)
    pairs = __import__("fiir_crystal.fsal", fromlist=["AxisAlignedPairMiner", "MatchedPairConfig"])
    dataset = pairs.AxisAlignedPairMiner().mine(candidates, config=pairs.MatchedPairConfig(min_pair_quality=0.0))
    run = __import__("fiir_crystal.discovery", fromlist=["MockDiscoveryPipeline"]).MockDiscoveryPipeline(
        oracle=oracle,
        top_k=3,
    ).run_structures(structures)

    report = evaluate_mock_fiir_loop(
        labels,
        dataset.pairs,
        ranked_candidates=run.ranked_candidates,
        top_k=3,
        validation_results=_validation_results(),
    )

    assert report.validation_metrics_available is True
    assert report.validation_count == 3
    assert report.validation_failure_count == 1
    assert report.validated_stable_rate == 0.5


def test_compare_pair_modes_outputs_all_modes_with_validation(tmp_path) -> None:
    output_dir = tmp_path / "comparison"
    result = compare_pair_modes(
        "configs/mock_fiir_loop.yaml",
        output_dir=output_dir,
        input_path="examples/mock_candidates.jsonl",
        top_k=3,
        seed=11,
        validation_results=read_validation_results_jsonl("examples/mock_validation_results.jsonl"),
    )

    assert (output_dir / "comparison_summary.json").exists()
    assert (output_dir / "comparison_table.md").exists()
    assert {row["mode"] for row in result["rows"]} == {
        "axis_aligned",
        "weighted_sum",
        "random_negative",
        "binary_success_failure",
    }
    assert all((output_dir / row["mode"]).exists() for row in result["rows"])
    assert "validated_stable_rate" in result["table"]


def test_aggregate_experiments_from_comparison_outputs(tmp_path) -> None:
    comparison = compare_pair_modes(
        "configs/mock_fiir_loop.yaml",
        modes=["axis_aligned", "weighted_sum"],
        output_dir=tmp_path / "comparison",
        input_path="examples/mock_candidates.jsonl",
        top_k=2,
        seed=3,
    )
    runs = [row["output_dir"] for row in comparison["rows"]]

    aggregate = aggregate_experiments(runs)
    table = render_aggregate_table(aggregate["runs"])

    assert aggregate["run_count"] == 2
    assert "pair_mode" in table
    assert load_experiment_summary(runs[0])["feedback_count"] == 2
    with pytest.raises(FileNotFoundError, match="required experiment output missing"):
        load_experiment_summary(tmp_path / "empty")


def test_active_loop_runs_two_rounds_with_feedback(tmp_path) -> None:
    result = run_mock_active_loop(
        load_experiment_config("configs/mock_fiir_loop.yaml"),
        validation_results=read_validation_results_jsonl("examples/mock_validation_results.jsonl"),
        output_dir=tmp_path / "active",
        input_path="examples/mock_candidates.jsonl",
        rounds=2,
    )

    assert (tmp_path / "active" / "round_001").exists()
    assert (tmp_path / "active" / "round_002").exists()
    assert (tmp_path / "active" / "feedback_buffer.jsonl").exists()
    assert result["feedback_buffer"].events
    assert result["summary"]["positive_evidence_count"] >= 1
    assert result["summary"]["negative_evidence_count"] >= 1


def test_feedback_buffer_from_validation_results() -> None:
    buffer = FeedbackBuffer.from_validation_results(_validation_results(), "round_001")

    assert buffer.positive_evidence_count == 1
    assert buffer.negative_evidence_count == 2
    assert "geo_good" in buffer.sampling_hints()["prefer_candidate_ids"]


def test_report_variants_handle_empty_inputs() -> None:
    assert "Pair Mode Comparison" in render_pair_mode_comparison_report({"modes": []}, "")
    assert "Aggregate Experiment" in render_aggregate_report({"runs": [], "run_count": 0}, "")
    assert "Mock Active Loop" in render_active_loop_report({"rounds": [], "round_count": 0})


def test_cli_help_and_missing_input_are_clear() -> None:
    scripts = [
        "scripts/run_mock_fiir_loop.py",
        "scripts/run_fiir_experiment.py",
        "scripts/compare_pair_modes.py",
        "scripts/compare_experiments.py",
        "scripts/run_mock_active_loop.py",
        "scripts/run_crystalformer_adapter.py",
    ]
    for script in scripts:
        completed = subprocess.run(
            [sys.executable, script, "--help"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert completed.returncode == 0
        assert "usage:" in completed.stdout

    missing = subprocess.run(
        [
            sys.executable,
            "scripts/compare_pair_modes.py",
            "--input",
            "missing.jsonl",
            "--output-dir",
            "unused",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert missing.returncode != 0
    assert "input file does not exist" in missing.stderr or "input file does not exist" in missing.stdout
