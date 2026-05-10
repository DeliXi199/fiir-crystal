"""Tiny config loader with JSON and a small YAML subset."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ExperimentConfig:
    """Normalized config for a lightweight FIIR experiment."""

    input_path: str = "examples/mock_candidates.jsonl"
    output_dir: str = "outputs/mock_run"
    random_seed: int = 7
    failure_thresholds: dict[str, float] = field(
        default_factory=lambda: {"f1": 0.1, "f2": 0.1, "f3": 0.1}
    )
    calibration: dict[str, Any] = field(default_factory=lambda: {"default_tier": 2})
    pair_mining: dict[str, Any] = field(
        default_factory=lambda: {
            "main_axis_threshold": 0.3,
            "other_axis_threshold": 0.15,
            "atom_count_tolerance": 0.2,
            "min_pair_quality": 0.05,
            "require_prototype_match": True,
            "require_space_group_match": False,
            "require_composition_family_match": False,
        }
    )
    pair_mode: str = "axis_aligned"
    weighted_sum_weights: dict[str, float] = field(default_factory=lambda: {"f1": 1.0, "f2": 1.0, "f3": 1.0})
    binary_success_threshold: float = 0.1
    ranking: dict[str, Any] = field(
        default_factory=lambda: {
            "mode": "utility",
            "weights": {
                "success": 0.4,
                "confidence": 0.2,
                "validity": 0.15,
                "novelty": 0.15,
                "diversity": 0.1,
                "cost": 0.05,
            },
            "allow_invalid": False,
        }
    )
    top_k: int = 5
    output_options: dict[str, bool] = field(
        default_factory=lambda: {
            "write_intermediates": True,
            "write_report": True,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_dir": self.output_dir,
            "random_seed": self.random_seed,
            "failure_thresholds": dict(self.failure_thresholds),
            "calibration": dict(self.calibration),
            "pair_mining": dict(self.pair_mining),
            "pair_mode": self.pair_mode,
            "weighted_sum_weights": dict(self.weighted_sum_weights),
            "binary_success_threshold": self.binary_success_threshold,
            "ranking": dict(self.ranking),
            "top_k": self.top_k,
            "output_options": dict(self.output_options),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        default = cls()
        merged = _deep_merge(default.to_dict(), data)
        return cls(
            input_path=str(merged["input_path"]),
            output_dir=str(merged["output_dir"]),
            random_seed=int(merged["random_seed"]),
            failure_thresholds={str(key): float(value) for key, value in merged["failure_thresholds"].items()},
            calibration=dict(merged["calibration"]),
            pair_mining=dict(merged["pair_mining"]),
            pair_mode=str(merged["pair_mode"]),
            weighted_sum_weights={str(key): float(value) for key, value in merged["weighted_sum_weights"].items()},
            binary_success_threshold=float(merged["binary_success_threshold"]),
            ranking=dict(merged["ranking"]),
            top_k=int(merged["top_k"]),
            output_options={str(key): bool(value) for key, value in merged["output_options"].items()},
        )


def load_experiment_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> ExperimentConfig:
    """Load experiment config from JSON or a simple YAML subset."""

    data: dict[str, Any] = {}
    if path is not None:
        source = Path(path)
        text = source.read_text(encoding="utf-8")
        if source.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = _parse_simple_yaml(text)
    if overrides:
        data = _deep_merge(data, overrides)
    return ExperimentConfig.from_dict(data)


def merge_config_overrides(config: ExperimentConfig, overrides: dict[str, Any]) -> ExperimentConfig:
    """Apply CLI-style overrides to a loaded config."""

    return ExperimentConfig.from_dict(_deep_merge(config.to_dict(), overrides))


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if ":" not in line:
            raise ValueError(f"Unsupported config line: {raw_line}")
        key, raw_value = line.strip().split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value_text = raw_value.strip()
        if not value_text:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value_text)
    return root


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if any(char in value for char in [".", "e", "E"]):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
