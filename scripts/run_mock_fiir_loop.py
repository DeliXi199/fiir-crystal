"""Run the first mock FIIR minimum-loop demo."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.discovery import MockDiscoveryPipeline
from fiir_crystal.evaluation import evaluate_mock_fiir_loop
from fiir_crystal.failure import MockFailureLabeler, demo_mock_crystals
from fiir_crystal.fsal import AxisAlignedPairMiner, LabeledCandidate, MatchedPairConfig


def _to_labeled_candidates(labeler: MockFailureLabeler, crystals) -> list[LabeledCandidate]:
    labels = {label.sample_id: label for label in labeler.label_crystals(crystals).labels}
    return [
        LabeledCandidate(
            sample_id=crystal.sample_id,
            structure_ref=crystal.structure_ref,
            failure_label=labels[crystal.sample_id],
            chemical_bucket=crystal.chemical_bucket,
            atom_count=crystal.num_atoms,
            space_group=crystal.space_group,
            prototype=crystal.prototype,
            metadata={"composition": crystal.composition},
        )
        for crystal in crystals
    ]


def main() -> None:
    crystals = demo_mock_crystals()
    labeler = MockFailureLabeler()

    print("Loaded mock candidates:")
    for crystal in crystals:
        print(
            f"  {crystal.sample_id}: composition={crystal.composition}, "
            f"prototype={crystal.prototype}, atoms={crystal.num_atoms}"
        )

    label_batch = labeler.label_crystals(crystals)
    print("\nFailure vectors:")
    for label in label_batch.labels:
        print(
            f"  {label.sample_id}: F1={label.f1_geometry:.2f}, "
            f"F2={label.f2_chemistry:.2f}, F3={label.f3_stability:.2f}, "
            f"tier={label.calibration_tier}"
        )

    labeled_candidates = _to_labeled_candidates(labeler, crystals)
    miner = AxisAlignedPairMiner()
    pair_dataset = miner.mine(
        labeled_candidates,
        config=MatchedPairConfig(min_pair_quality=0.05),
    )

    print("\nPreference pairs:")
    for pair in pair_dataset.pairs:
        print(
            f"  {pair.pair_id}: winner={pair.winner_id}, loser={pair.loser_id}, "
            f"axis={pair.axis.value}, margin={pair.margin:.2f}, "
            f"confidence={pair.confidence:.2f}"
        )

    report = evaluate_mock_fiir_loop(label_batch.labels, pair_dataset.pairs)
    print("\nEvaluation report:")
    for key, value in report.as_dict().items():
        print(f"  {key}: {value}")

    discovery = MockDiscoveryPipeline(labeler=labeler, top_k=3)
    run = discovery.run_crystals(crystals)

    print("\nMock discovery ranking:")
    for ranked in run.ranked_candidates[:3]:
        print(
            f"  rank={ranked.rank}, candidate={ranked.candidate_id}, "
            f"utility={ranked.acquisition.utility:.3f}, "
            f"success={ranked.acquisition.success_score:.3f}"
        )

    print("\nTop-k feedback records:")
    for feedback in run.feedback_records:
        print(f"  {feedback.feedback_id}: candidate={feedback.candidate_id}")


if __name__ == "__main__":
    main()
