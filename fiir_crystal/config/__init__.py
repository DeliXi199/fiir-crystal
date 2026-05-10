"""Configuration loading for lightweight FIIR experiments."""

from fiir_crystal.config.loader import (
    ExperimentConfig,
    load_experiment_config,
    merge_config_overrides,
)

__all__ = ["ExperimentConfig", "load_experiment_config", "merge_config_overrides"]
