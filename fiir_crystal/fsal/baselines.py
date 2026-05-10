"""Preference-pair construction modes for lightweight FIIR experiments."""

from __future__ import annotations

import random
from enum import Enum
from typing import Sequence

from fiir_crystal.fsal.pair_mining import AxisAlignedPairMiner
from fiir_crystal.fsal.preference_data import (
    FailureBucket,
    LabeledCandidate,
    MatchedPairConfig,
    PreferenceAxis,
    PreferenceDataset,
    PreferencePair,
)


class PairConstructionMode(str, Enum):
    """Supported lightweight pair construction modes."""

    AXIS_ALIGNED = "axis_aligned"
    WEIGHTED_SUM = "weighted_sum"
    RANDOM_NEGATIVE = "random_negative"
    BINARY_SUCCESS_FAILURE = "binary_success_failure"


def build_preference_dataset(
    candidates: Sequence[LabeledCandidate],
    mode: str | PairConstructionMode = PairConstructionMode.AXIS_ALIGNED,
    config: MatchedPairConfig | None = None,
    seed: int = 0,
    weighted_sum_weights: dict[str, float] | None = None,
    success_threshold: float = 0.1,
) -> PreferenceDataset:
    """Build a preference dataset using one of the lightweight baseline modes."""

    selected_mode = PairConstructionMode(mode)
    cfg = config or MatchedPairConfig()
    if selected_mode is PairConstructionMode.AXIS_ALIGNED:
        dataset = AxisAlignedPairMiner().mine(candidates, config=cfg)
        for pair in dataset.pairs:
            pair.metadata["mode"] = selected_mode.value
        dataset.stats["mode"] = selected_mode.value
        return dataset
    if selected_mode is PairConstructionMode.WEIGHTED_SUM:
        pairs = _weighted_sum_pairs(candidates, cfg, weighted_sum_weights or {"f1": 1.0, "f2": 1.0, "f3": 1.0})
    elif selected_mode is PairConstructionMode.RANDOM_NEGATIVE:
        pairs = _random_negative_pairs(candidates, cfg, seed, success_threshold)
    else:
        pairs = _binary_success_failure_pairs(candidates, cfg, success_threshold)
    return _dataset_from_pairs(candidates, pairs, selected_mode, cfg)


def _weighted_sum_pairs(
    candidates: Sequence[LabeledCandidate],
    config: MatchedPairConfig,
    weights: dict[str, float],
) -> list[PreferencePair]:
    pairs: list[PreferencePair] = []
    usable = [candidate for candidate in candidates if _is_valid(candidate)]
    for left_index, left in enumerate(usable):
        for right in usable[left_index + 1 :]:
            if not _compatible(left, right, config):
                continue
            left_score = _weighted_score(left, weights)
            right_score = _weighted_score(right, weights)
            gap = abs(left_score - right_score)
            if gap < config.main_axis_threshold:
                continue
            winner, loser = (left, right) if left_score <= right_score else (right, left)
            pairs.append(
                _make_pair(
                    winner,
                    loser,
                    axis=PreferenceAxis.MIXED,
                    margin=_margin_for_gap(gap),
                    confidence=_confidence(winner, loser, gap, config),
                    reason="weighted_sum_gap",
                    mode=PairConstructionMode.WEIGHTED_SUM.value,
                    score_details={
                        "winner_score": min(left_score, right_score),
                        "loser_score": max(left_score, right_score),
                        "weights": dict(weights),
                    },
                )
            )
    pairs.sort(key=lambda pair: (pair.margin, pair.confidence, pair.pair_id), reverse=True)
    return pairs


def _random_negative_pairs(
    candidates: Sequence[LabeledCandidate],
    config: MatchedPairConfig,
    seed: int,
    success_threshold: float,
) -> list[PreferencePair]:
    rng = random.Random(seed)
    successes, failures = _split_success_failure(candidates, success_threshold)
    pairs: list[PreferencePair] = []
    for winner in successes:
        compatible_failures = [candidate for candidate in failures if _compatible(winner, candidate, config)]
        if not compatible_failures:
            continue
        loser = rng.choice(compatible_failures)
        gap = max(0.1, _aggregate_failure(loser) - _aggregate_failure(winner))
        pairs.append(
            _make_pair(
                winner,
                loser,
                axis=PreferenceAxis.MIXED,
                margin=_margin_for_gap(gap),
                confidence=_confidence(winner, loser, gap, config),
                reason="random_negative",
                mode=PairConstructionMode.RANDOM_NEGATIVE.value,
                score_details={"seed": seed, "success_threshold": success_threshold},
            )
        )
    return pairs


def _binary_success_failure_pairs(
    candidates: Sequence[LabeledCandidate],
    config: MatchedPairConfig,
    success_threshold: float,
) -> list[PreferencePair]:
    successes, failures = _split_success_failure(candidates, success_threshold)
    pairs: list[PreferencePair] = []
    for winner in successes:
        for loser in failures:
            if not _compatible(winner, loser, config):
                continue
            gap = max(0.1, _aggregate_failure(loser) - _aggregate_failure(winner))
            pairs.append(
                _make_pair(
                    winner,
                    loser,
                    axis=PreferenceAxis.MIXED,
                    margin=_margin_for_gap(gap),
                    confidence=_confidence(winner, loser, gap, config),
                    reason="binary_success_failure",
                    mode=PairConstructionMode.BINARY_SUCCESS_FAILURE.value,
                    score_details={"success_threshold": success_threshold},
                )
            )
    return pairs


def _dataset_from_pairs(
    candidates: Sequence[LabeledCandidate],
    pairs: list[PreferencePair],
    mode: PairConstructionMode,
    config: MatchedPairConfig,
) -> PreferenceDataset:
    return PreferenceDataset(
        dataset_id=f"lightweight-{mode.value}",
        pairs=pairs,
        pairs_by_axis={PreferenceAxis.MIXED: pairs},
        candidate_index={candidate.sample_id: candidate for candidate in candidates if _is_valid(candidate)},
        stats={
            "mode": mode.value,
            "pair_count": len(pairs),
            "candidate_count": len(candidates),
        },
        config={
            "main_axis_threshold": config.main_axis_threshold,
            "atom_count_tolerance": config.atom_count_tolerance,
        },
    )


def _make_pair(
    winner: LabeledCandidate,
    loser: LabeledCandidate,
    axis: PreferenceAxis,
    margin: float,
    confidence: float,
    reason: str,
    mode: str,
    score_details: dict[str, object],
) -> PreferencePair:
    match_metadata = {
        "same_prototype": winner.prototype == loser.prototype,
        "same_space_group": winner.space_group == loser.space_group,
        "atom_count_delta": abs(winner.atom_count - loser.atom_count),
        "same_composition_family": _family(winner) == _family(loser),
    }
    return PreferencePair(
        pair_id=f"{mode}:{winner.sample_id}>{loser.sample_id}",
        winner_id=winner.sample_id,
        loser_id=loser.sample_id,
        axis=axis,
        winner_failure=_failure_summary(winner),
        loser_failure=_failure_summary(loser),
        main_axis_gap=abs(_aggregate_failure(loser) - _aggregate_failure(winner)),
        other_axis_delta={},
        other_axis_similarity=1.0,
        structure_match_score=1.0 if match_metadata["same_prototype"] else 0.5,
        label_confidence=confidence,
        pair_quality=confidence * margin,
        margin=margin,
        weight=confidence,
        failure_bucket=FailureBucket.MIXED,
        match_metadata=match_metadata,
        reason=reason,
        metadata={
            "mode": mode,
            "axis": axis.value,
            "margin": margin,
            "confidence": confidence,
            "reason": reason,
            "match_constraints": match_metadata,
            "score_details": score_details,
        },
    )


def _split_success_failure(
    candidates: Sequence[LabeledCandidate],
    success_threshold: float,
) -> tuple[list[LabeledCandidate], list[LabeledCandidate]]:
    usable = [candidate for candidate in candidates if _is_valid(candidate)]
    successes = [candidate for candidate in usable if _aggregate_failure(candidate) < success_threshold]
    failures = [candidate for candidate in usable if _aggregate_failure(candidate) >= success_threshold]
    return successes, failures


def _weighted_score(candidate: LabeledCandidate, weights: dict[str, float]) -> float:
    return (
        weights.get("f1", 1.0) * _value(candidate, "f1_geometry")
        + weights.get("f2", 1.0) * _value(candidate, "f2_chemistry")
        + weights.get("f3", 1.0) * _value(candidate, "f3_stability")
    )


def _aggregate_failure(candidate: LabeledCandidate) -> float:
    return (_value(candidate, "f1_geometry") + _value(candidate, "f2_chemistry") + _value(candidate, "f3_stability")) / 3.0


def _value(candidate: LabeledCandidate, field_name: str) -> float:
    source = candidate.failure_vector or candidate.failure_label
    value = getattr(source, field_name)
    return float(value if value is not None else 1.0)


def _compatible(left: LabeledCandidate, right: LabeledCandidate, config: MatchedPairConfig) -> bool:
    if not _is_valid(left) or not _is_valid(right):
        return False
    max_atoms = max(left.atom_count, right.atom_count)
    if max_atoms <= 0:
        return False
    if abs(left.atom_count - right.atom_count) / max_atoms > config.atom_count_tolerance:
        return False
    if config.require_prototype_match and left.prototype and right.prototype and left.prototype != right.prototype:
        return False
    if config.require_space_group_match and left.space_group and right.space_group and left.space_group != right.space_group:
        return False
    if config.require_composition_family_match and _family(left) != _family(right):
        return False
    return True


def _is_valid(candidate: LabeledCandidate) -> bool:
    if candidate.failure_vector is not None:
        return candidate.failure_vector.is_valid
    return not candidate.failure_label.pre_filtered


def _confidence(winner: LabeledCandidate, loser: LabeledCandidate, gap: float, config: MatchedPairConfig) -> float:
    base = min(_candidate_confidence(winner), _candidate_confidence(loser))
    margin_factor = min(1.0, gap / max(config.main_axis_threshold, 1e-8))
    return max(0.0, min(1.0, base * margin_factor))


def _candidate_confidence(candidate: LabeledCandidate) -> float:
    if candidate.failure_vector is not None:
        return candidate.failure_vector.confidence
    return candidate.failure_label.confidence


def _margin_for_gap(gap: float) -> float:
    if gap < 0.15:
        return 0.1
    if gap < 0.4:
        return 0.3
    return 0.5


def _failure_summary(candidate: LabeledCandidate) -> dict[str, float | None]:
    source = candidate.failure_vector or candidate.failure_label
    return {
        "f1_geometry": source.f1_geometry,
        "f2_chemistry": source.f2_chemistry,
        "f3_stability": source.f3_stability,
    }


def _family(candidate: LabeledCandidate) -> str:
    return str(candidate.metadata.get("composition_family", candidate.chemical_bucket))
