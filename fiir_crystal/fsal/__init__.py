"""Failure-Structured Alignment Learning skeleton."""

from fiir_crystal.fsal.pair_mining import (
    AxisAlignedPairMiner,
    MatchedAxisAlignedPairMiner,
    PairMiningSummary,
)
from fiir_crystal.fsal.baselines import PairConstructionMode, build_preference_dataset
from fiir_crystal.fsal.preference_data import (
    FailureBucket,
    LabeledCandidate,
    MatchedPairConfig,
    PreferenceAxis,
    PreferenceDataset,
    PreferencePair,
)
from fiir_crystal.fsal.trainer import (
    DPOObjective,
    DPOTrainingConfig,
    FSALTrainer,
    ModelLogProbAdapter,
    TrainingRunSummary,
)

__all__ = [
    "DPOObjective",
    "DPOTrainingConfig",
    "FSALTrainer",
    "FailureBucket",
    "AxisAlignedPairMiner",
    "LabeledCandidate",
    "MatchedAxisAlignedPairMiner",
    "MatchedPairConfig",
    "ModelLogProbAdapter",
    "PairMiningSummary",
    "PairConstructionMode",
    "PreferenceAxis",
    "PreferenceDataset",
    "PreferencePair",
    "TrainingRunSummary",
    "build_preference_dataset",
]
