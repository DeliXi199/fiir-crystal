"""Run the lightweight FIIR-v1 mock closed-loop demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.discovery import MockDiscoveryPipeline
from fiir_crystal.evaluation import evaluate_mock_fiir_loop
from fiir_crystal.experiment import build_labeled_candidates
from fiir_crystal.failure import FailureOracle, StructureLike, demo_mock_crystals
from fiir_crystal.fsal import AxisAlignedPairMiner, MatchedPairConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the in-memory lightweight FIIR mock loop.")
    parser.add_argument("--quiet", action="store_true", help="Only print a compact summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    structures = demo_mock_crystals()
    oracle = FailureOracle.default()

    if not args.quiet:
        print("Loaded mock candidates:")
        for structure in structures:
            print(
                f"  {structure.candidate_id}: composition={structure.composition}, "
                f"prototype={structure.prototype}, atoms={structure.num_atoms}, "
                f"space_group={structure.space_group}"
            )

    labels = [oracle.label_structure(structure) for structure in structures]
    vectors = [oracle.vectorize(structure) for structure in structures]
    if not args.quiet:
        print("\nFailureOracle vectors:")
        for vector in vectors:
            hard = ",".join(vector.hard_failures) if vector.hard_failures else "none"
            print(
                f"  {vector.candidate_id}: F1={vector.f1_geometry:.2f}, "
                f"F2={vector.f2_chemistry:.2f}, F3={vector.f3_stability:.2f}, "
                f"tier={vector.calibration_tier}, confidence={vector.confidence:.2f}, "
                f"valid={vector.is_valid}, hard_failures={hard}"
            )

    labeled_candidates = build_labeled_candidates(oracle, structures)
    miner = AxisAlignedPairMiner()
    pair_dataset = miner.mine(
        labeled_candidates,
        config=MatchedPairConfig(
            min_pair_quality=0.05,
            require_prototype_match=True,
            require_space_group_match=False,
        ),
    )

    if not args.quiet:
        print("\nMatched axis-aligned preference pairs:")
        for pair in pair_dataset.pairs:
            print(
                f"  {pair.pair_id}: winner={pair.winner_id}, loser={pair.loser_id}, "
                f"axis={pair.axis.value}, margin={pair.margin:.2f}, "
                f"confidence={pair.confidence:.2f}, reason={pair.reason}, "
                f"match={pair.match_metadata}"
            )

    report = evaluate_mock_fiir_loop(labels, pair_dataset.pairs)
    if not args.quiet:
        print("\nEvaluation report:")
        for key, value in report.as_dict().items():
            print(f"  {key}: {value}")

    discovery = MockDiscoveryPipeline(oracle=oracle, top_k=3)
    run = discovery.run_structures(structures)

    if args.quiet:
        print(
            f"Mock FIIR loop complete: candidates={len(structures)}, "
            f"pairs={len(pair_dataset.pairs)}, top_k={len(run.feedback_records)}"
        )
        return

    print("\nMock discovery ranking:")
    for ranked in run.ranked_candidates[:3]:
        print(
            f"  rank={ranked.rank}, candidate={ranked.candidate_id}, "
            f"utility={ranked.acquisition.utility:.3f}, "
            f"success={ranked.acquisition.success_score:.3f}, "
            f"novelty={ranked.acquisition.novelty_score:.3f}, "
            f"diversity={ranked.acquisition.diversity_score:.3f}"
        )

    print("\nTop-k feedback records:")
    for feedback in run.feedback_records:
        vector = feedback.failure_vector
        print(
            f"  {feedback.feedback_id}: candidate={feedback.candidate_id}, "
            f"rank={feedback.selected_rank}, decision={feedback.decision}, "
            f"reason={feedback.reason}, F=({vector.f1_geometry:.2f}, "
            f"{vector.f2_chemistry:.2f}, {vector.f3_stability:.2f})"
        )


if __name__ == "__main__":
    main()
