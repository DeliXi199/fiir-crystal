"""Pair-mining interfaces and a lightweight mock implementation for FSAL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from fiir_crystal.failure import FailureLabel
from fiir_crystal.fsal.preference_data import (
    FailureBucket,
    LabeledCandidate,
    MatchedPairConfig,
    PreferenceAxis,
    PreferenceDataset,
    PreferencePair,
)


@dataclass(slots=True)
class PairMiningSummary:
    """Audit summary for a pair-mining run."""

    candidate_count: int = 0
    accepted_pair_count: int = 0
    rejected_pair_count: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


class MatchedAxisAlignedPairMiner(ABC):
    """Contract for matched axis-aligned preference-pair mining."""

    @abstractmethod
    def mine(
        self,
        candidates: Sequence[LabeledCandidate],
        config: MatchedPairConfig | None = None,
    ) -> PreferenceDataset:
        """Build a preference dataset from labeled candidates."""


class AxisAlignedPairMiner(MatchedAxisAlignedPairMiner):
    """Lightweight matched axis-aligned pair miner for mock candidates."""

    _AXIS_FIELDS: dict[PreferenceAxis, str] = {
        PreferenceAxis.F1_GEOMETRY: "f1_geometry",
        PreferenceAxis.F2_CHEMISTRY: "f2_chemistry",
        PreferenceAxis.F3_STABILITY: "f3_stability",
    }

    def mine_pairs(
        self,
        candidates: Sequence[LabeledCandidate],
        config: MatchedPairConfig | None = None,
    ) -> list[PreferencePair]:
        """Return only mined preference pairs."""

        return self.mine(candidates, config=config).pairs

    def mine(
        self,
        candidates: Sequence[LabeledCandidate],
        config: MatchedPairConfig | None = None,
    ) -> PreferenceDataset:
        """Build F1/F2/F3 axis-aligned pairs from labeled mock candidates."""

        cfg = config or MatchedPairConfig()
        usable = [candidate for candidate in candidates if not candidate.failure_label.pre_filtered]
        pairs: list[PreferencePair] = []
        by_axis: dict[PreferenceAxis, list[PreferencePair]] = {
            PreferenceAxis.F1_GEOMETRY: [],
            PreferenceAxis.F2_CHEMISTRY: [],
            PreferenceAxis.F3_STABILITY: [],
        }
        rejected: dict[str, int] = {}

        for axis in by_axis:
            axis_pairs = self._mine_axis_pairs(usable, axis, cfg, rejected)
            by_axis[axis].extend(axis_pairs)
            pairs.extend(axis_pairs)
            if cfg.max_pairs_per_axis is not None and len(by_axis[axis]) >= cfg.max_pairs_per_axis:
                by_axis[axis] = by_axis[axis][: cfg.max_pairs_per_axis]

        if cfg.max_pairs_per_axis is not None:
            pairs = [pair for axis_pairs in by_axis.values() for pair in axis_pairs]

        return PreferenceDataset(
            dataset_id="mock-axis-aligned",
            pairs=pairs,
            pairs_by_axis=by_axis,
            candidate_index={candidate.sample_id: candidate for candidate in usable},
            stats={
                "candidate_count": len(candidates),
                "usable_candidate_count": len(usable),
                "pair_count": len(pairs),
                "pairs_by_axis": {axis.value: len(axis_pairs) for axis, axis_pairs in by_axis.items()},
                "rejection_reasons": rejected,
            },
            config={
                "main_axis_threshold": cfg.main_axis_threshold,
                "other_axis_threshold": cfg.other_axis_threshold,
                "atom_count_tolerance": cfg.atom_count_tolerance,
                "min_pair_quality": cfg.min_pair_quality,
            },
        )

    def _mine_axis_pairs(
        self,
        candidates: Sequence[LabeledCandidate],
        axis: PreferenceAxis,
        config: MatchedPairConfig,
        rejected: dict[str, int],
    ) -> list[PreferencePair]:
        pairs: list[PreferencePair] = []
        main_field = self._AXIS_FIELDS[axis]
        other_fields = [field_name for pair_axis, field_name in self._AXIS_FIELDS.items() if pair_axis != axis]

        for left_index, left in enumerate(candidates):
            for right in candidates[left_index + 1 :]:
                reason = self._reject_reason(left, right, main_field, other_fields, config)
                if reason is not None:
                    rejected[reason] = rejected.get(reason, 0) + 1
                    continue

                pair = self._make_pair(left, right, axis, main_field, other_fields, config)
                if pair.pair_quality < config.min_pair_quality:
                    rejected["low_pair_quality"] = rejected.get("low_pair_quality", 0) + 1
                    continue
                pairs.append(pair)
                if config.max_pairs_per_axis is not None and len(pairs) >= config.max_pairs_per_axis:
                    return pairs
        return pairs

    def _reject_reason(
        self,
        left: LabeledCandidate,
        right: LabeledCandidate,
        main_field: str,
        other_fields: Sequence[str],
        config: MatchedPairConfig,
    ) -> str | None:
        if not self._metadata_matches(left, right, config):
            return "metadata_mismatch"

        left_main = getattr(left.failure_label, main_field)
        right_main = getattr(right.failure_label, main_field)
        if left_main is None or right_main is None:
            return "missing_main_axis"
        if abs(left_main - right_main) < config.main_axis_threshold:
            return "small_main_axis_gap"

        for field_name in other_fields:
            left_value = getattr(left.failure_label, field_name)
            right_value = getattr(right.failure_label, field_name)
            if left_value is None or right_value is None:
                return "missing_other_axis"
            if abs(left_value - right_value) > config.other_axis_threshold:
                return "other_axis_leakage"
        return None

    def _metadata_matches(
        self,
        left: LabeledCandidate,
        right: LabeledCandidate,
        config: MatchedPairConfig,
    ) -> bool:
        max_atoms = max(left.atom_count, right.atom_count)
        if max_atoms <= 0:
            return False
        atom_delta = abs(left.atom_count - right.atom_count) / max_atoms
        if atom_delta > config.atom_count_tolerance:
            return False
        if left.prototype is not None and right.prototype is not None:
            return left.prototype == right.prototype
        if left.space_group is not None and right.space_group is not None:
            return left.space_group == right.space_group
        return left.chemical_bucket == right.chemical_bucket

    def _make_pair(
        self,
        left: LabeledCandidate,
        right: LabeledCandidate,
        axis: PreferenceAxis,
        main_field: str,
        other_fields: Sequence[str],
        config: MatchedPairConfig,
    ) -> PreferencePair:
        left_value = getattr(left.failure_label, main_field)
        right_value = getattr(right.failure_label, main_field)
        winner, loser = (left, right) if left_value <= right_value else (right, left)
        winner_value = getattr(winner.failure_label, main_field)
        loser_value = getattr(loser.failure_label, main_field)
        main_gap = abs(float(loser_value) - float(winner_value))
        other_delta = {
            field_name: abs(
                float(getattr(left.failure_label, field_name))
                - float(getattr(right.failure_label, field_name))
            )
            for field_name in other_fields
        }
        other_similarity = max(0.0, 1.0 - (sum(other_delta.values()) / len(other_delta)))
        structure_match = self._structure_match_score(left, right)
        label_confidence = min(
            config.tier_weights.get(left.failure_label.calibration_tier, 0.0),
            config.tier_weights.get(right.failure_label.calibration_tier, 0.0),
        )
        pair_quality = main_gap * other_similarity * structure_match * label_confidence
        margin = self._margin_for_gap(main_gap)

        return PreferencePair(
            pair_id=f"{axis.value}:{winner.sample_id}>{loser.sample_id}",
            winner_id=winner.sample_id,
            loser_id=loser.sample_id,
            axis=axis,
            winner_failure=self._failure_summary(winner.failure_label),
            loser_failure=self._failure_summary(loser.failure_label),
            main_axis_gap=main_gap,
            other_axis_delta=other_delta,
            other_axis_similarity=other_similarity,
            structure_match_score=structure_match,
            label_confidence=label_confidence,
            pair_quality=pair_quality,
            margin=margin,
            weight=label_confidence,
            failure_bucket=self._failure_bucket(loser.failure_label),
            metadata={
                "match_on": self._match_description(left, right),
                "winner_structure_ref": winner.structure_ref,
                "loser_structure_ref": loser.structure_ref,
                "confidence": label_confidence,
            },
        )

    def _structure_match_score(self, left: LabeledCandidate, right: LabeledCandidate) -> float:
        atom_score = min(left.atom_count, right.atom_count) / max(left.atom_count, right.atom_count)
        prototype_score = 1.0 if left.prototype and left.prototype == right.prototype else 0.0
        space_group_score = 1.0 if left.space_group and left.space_group == right.space_group else 0.0
        bucket_score = 1.0 if left.chemical_bucket == right.chemical_bucket else 0.0
        return 0.4 * atom_score + 0.25 * prototype_score + 0.25 * space_group_score + 0.1 * bucket_score

    def _match_description(self, left: LabeledCandidate, right: LabeledCandidate) -> dict[str, Any]:
        return {
            "same_prototype": left.prototype is not None and left.prototype == right.prototype,
            "same_space_group": left.space_group is not None and left.space_group == right.space_group,
            "atom_count_delta": abs(left.atom_count - right.atom_count),
        }

    def _margin_for_gap(self, gap: float) -> float:
        if gap < 0.15:
            return 0.1
        if gap < 0.4:
            return 0.3
        return 0.5

    def _failure_bucket(self, label: FailureLabel) -> FailureBucket:
        if label.is_near_miss:
            return FailureBucket.NEAR_MISS
        if label.is_moderate:
            return FailureBucket.MODERATE
        if label.is_catastrophic:
            return FailureBucket.CATASTROPHIC
        return FailureBucket.UNKNOWN

    def _failure_summary(self, label: FailureLabel) -> dict[str, float | None]:
        return {
            "f1_geometry": label.f1_geometry,
            "f2_chemistry": label.f2_chemistry,
            "f3_stability": label.f3_stability,
        }
