"""Configurable lightweight FIIR experiment runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.config import ExperimentConfig
from fiir_crystal.discovery import MockDiscoveryPipeline
from fiir_crystal.evaluation import EvaluationReport, evaluate_mock_fiir_loop
from fiir_crystal.failure import FailureOracle, StructureLike
from fiir_crystal.fsal import LabeledCandidate, MatchedPairConfig, build_preference_dataset
from fiir_crystal.io import read_mock_candidates_jsonl, write_json, write_jsonl
from fiir_crystal.reporting import render_experiment_report


def build_labeled_candidates(
    oracle: FailureOracle,
    structures: Sequence[StructureLike],
) -> list[LabeledCandidate]:
    """Build FSAL candidates from lightweight structures."""

    candidates: list[LabeledCandidate] = []
    for structure in structures:
        vector = oracle.vectorize(structure)
        label = oracle.label_structure(structure)
        candidates.append(
            LabeledCandidate(
                sample_id=structure.sample_id,
                structure_ref=structure.structure_ref,
                failure_label=label,
                failure_vector=vector,
                chemical_bucket=structure.chemical_bucket,
                atom_count=structure.num_atoms,
                space_group=structure.space_group,
                prototype=structure.prototype,
                metadata={
                    "composition": structure.composition,
                    "composition_family": structure.metadata.get("composition_family", structure.chemical_bucket),
                },
            )
        )
    return candidates


def run_fiir_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Run the full lightweight FIIR experiment and write configured outputs."""

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    structures = read_mock_candidates_jsonl(config.input_path)
    oracle = FailureOracle.default()
    labeled_candidates = build_labeled_candidates(oracle, structures)
    labels = [candidate.failure_label for candidate in labeled_candidates]
    vectors = [candidate.failure_vector for candidate in labeled_candidates if candidate.failure_vector is not None]

    pair_config = MatchedPairConfig(**_allowed_pair_config(config.pair_mining))
    preference_dataset = build_preference_dataset(
        labeled_candidates,
        mode=config.pair_mode,
        config=pair_config,
        seed=config.random_seed,
        weighted_sum_weights=config.weighted_sum_weights,
        success_threshold=config.binary_success_threshold,
    )

    discovery = MockDiscoveryPipeline(
        oracle=oracle,
        top_k=config.top_k,
        ranking_mode=str(config.ranking.get("mode", "utility")),
        ranking_weights=dict(config.ranking.get("weights", {})),
        allow_invalid=bool(config.ranking.get("allow_invalid", False)),
    )
    discovery_run = discovery.run_structures(structures)
    evaluation_report = evaluate_mock_fiir_loop(
        labels,
        preference_dataset.pairs,
        ranked_candidates=discovery_run.ranked_candidates,
        top_k=config.top_k,
        failure_threshold=config.failure_thresholds.get("f3", 0.1),
    )
    summary = _summary(config, structures, vectors, preference_dataset.pairs, discovery_run.ranked_candidates, discovery_run.feedback_records)

    if config.output_options.get("write_intermediates", True):
        write_jsonl(output_dir / "candidates.jsonl", structures)
        write_jsonl(output_dir / "failure_vectors.jsonl", vectors)
        write_jsonl(output_dir / "preference_pairs.jsonl", preference_dataset.pairs)
        write_json(output_dir / "evaluation_report.json", evaluation_report)
        write_jsonl(output_dir / "discovery_ranking.jsonl", discovery_run.ranked_candidates)
        write_jsonl(output_dir / "feedback_records.jsonl", discovery_run.feedback_records)
        write_json(output_dir / "experiment_summary.json", summary)

    if config.output_options.get("write_report", True):
        report = render_experiment_report(
            summary=summary,
            config=config.to_dict(),
            evaluation_report=evaluation_report,
            ranked_candidates=discovery_run.ranked_candidates,
            feedback_records=discovery_run.feedback_records,
        )
        (output_dir / "report.md").write_text(report, encoding="utf-8")

    return {
        "config": config,
        "structures": structures,
        "labeled_candidates": labeled_candidates,
        "failure_vectors": vectors,
        "preference_dataset": preference_dataset,
        "evaluation_report": evaluation_report,
        "discovery_run": discovery_run,
        "summary": summary,
        "output_dir": output_dir,
    }


def _allowed_pair_config(pair_config: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "main_axis_threshold",
        "other_axis_threshold",
        "atom_count_tolerance",
        "require_prototype_match",
        "require_space_group_match",
        "require_composition_family_match",
        "min_structure_match_score",
        "min_pair_quality",
        "max_pairs_per_axis",
    }
    return {key: value for key, value in pair_config.items() if key in allowed}


def _summary(
    config: ExperimentConfig,
    structures: Sequence[StructureLike],
    vectors: Sequence[Any],
    pairs: Sequence[Any],
    ranked: Sequence[Any],
    feedback: Sequence[Any],
) -> dict[str, Any]:
    return {
        "input_path": config.input_path,
        "output_dir": config.output_dir,
        "pair_mode": config.pair_mode,
        "ranking_mode": config.ranking.get("mode", "utility"),
        "candidate_count": len(structures),
        "failure_vector_count": len(vectors),
        "pair_count": len(pairs),
        "ranked_count": len(ranked),
        "feedback_count": len(feedback),
        "top_k": config.top_k,
    }
