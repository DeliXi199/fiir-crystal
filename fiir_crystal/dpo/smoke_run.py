"""Prepare non-overwriting CrystalFormer DPO smoke-run artifacts.

This module prepares data and command provenance only. It does not import
CrystalFormer, JAX, torch, pymatgen, or run DPO training.
"""

from __future__ import annotations

import ast
import shlex
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.dpo.training_boundary import validate_preference_pairs_for_training
from fiir_crystal.io import read_jsonl, write_json, write_jsonl


DEFAULT_CRYSTALFORMER_MODEL_ARGS = {
    "Nf": 5,
    "Kx": 16,
    "Kl": 4,
    "h0_size": 256,
    "transformer_layers": 16,
    "num_heads": 8,
    "key_size": 32,
    "model_size": 256,
    "embed_size": 256,
    "dropout_rate": 0.1,
    "attn_dropout": 0.1,
    "n_max": 21,
    "atom_types": 119,
    "wyck_types": 28,
}


@dataclass(slots=True)
class CrystalFormerDpoSmokeRunConfig:
    """Configuration for preparing a safe CrystalFormer DPO smoke run."""

    preference_pairs_jsonl: Path
    output_dir: Path
    base_checkpoint_dir: Path
    crystalformer_work_dir: Path = Path("external/CrystalFormer")
    run_name: str = "fiir_dpo_smoke"
    epochs: int = 1
    batchsize: int = 32
    lr: float = 1e-5
    beta: float = 0.1
    label_smoothing: float = 0.0
    gamma: float = 0.0
    val_ratio: float = 0.2
    optimizer: str = "adam"
    num_io_process: int = 1
    max_pairs: int | None = None


def prepare_crystalformer_dpo_smoke_run(
    config: CrystalFormerDpoSmokeRunConfig,
) -> dict[str, Any]:
    """Write chosen/rejected raw-sequence JSONL files and a safe run manifest."""

    _validate_smoke_config(config)
    all_pairs = read_jsonl(config.preference_pairs_jsonl)
    pair_summary = validate_preference_pairs_for_training(all_pairs)
    if pair_summary.invalid_pair_count:
        raise ValueError(f"invalid preference pairs: {pair_summary.invalid_reasons}")
    pairs = all_pairs if config.max_pairs is None else all_pairs[: config.max_pairs]
    if not pairs:
        raise ValueError("no preference pairs available for DPO smoke run")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    chosen_path = config.output_dir / "chosen_sequences.jsonl"
    rejected_path = config.output_dir / "rejected_sequences.jsonl"
    pair_index_path = config.output_dir / "pair_index.jsonl"
    manifest_path = config.output_dir / "dpo_smoke_manifest.json"
    report_path = config.output_dir / "report.md"
    run_script_path = config.output_dir / "run_training.sh"

    chosen_rows, rejected_rows, index_rows = _sequence_rows(pairs)
    write_jsonl(chosen_path, chosen_rows)
    write_jsonl(rejected_path, rejected_rows)
    write_jsonl(pair_index_path, index_rows)

    command = _training_command(config, chosen_path, rejected_path)
    start_epoch = _latest_checkpoint_epoch(config.base_checkpoint_dir)
    target_epoch = None if start_epoch is None else start_epoch + config.epochs
    manifest = {
        "manifest_type": "crystalformer_dpo_smoke_run",
        "run_name": config.run_name,
        "runs_training": False,
        "non_overwrite": True,
        "base_checkpoint_dir": str(config.base_checkpoint_dir),
        "training_output_root": str(_training_output_root(config)),
        "crystalformer_work_dir": str(config.crystalformer_work_dir),
        "preference_pairs_jsonl": str(config.preference_pairs_jsonl),
        "preference_pairs_sha256": sha256(config.preference_pairs_jsonl.read_bytes()).hexdigest(),
        "input_pair_count": pair_summary.input_pair_count,
        "prepared_pair_count": len(pairs),
        "checkpoint_start_epoch": start_epoch,
        "checkpoint_target_epoch": target_epoch,
        "pair_validation": pair_summary.to_dict(),
        "chosen_sequences_jsonl": str(chosen_path),
        "rejected_sequences_jsonl": str(rejected_path),
        "pair_index_jsonl": str(pair_index_path),
        "recommended_training_command": command,
        "run_script": str(run_script_path),
        "model_args": dict(DEFAULT_CRYSTALFORMER_MODEL_ARGS),
        "training_args": {
            "epochs": config.epochs,
            "epochs_are_additional": True,
            "batchsize": config.batchsize,
            "lr": config.lr,
            "beta": config.beta,
            "label_smoothing": config.label_smoothing,
            "gamma": config.gamma,
            "val_ratio": config.val_ratio,
            "optimizer": config.optimizer,
            "num_io_process": config.num_io_process,
        },
        "before_after_protocol": [
            "Use base_checkpoint_dir as the before model and do not write into it.",
            "Run the recommended command from crystalformer_work_dir on an allocated compute node.",
            "Use the produced checkpoint directory as the after model.",
            "Generate before and after samples with identical formulas, seeds, K/top-k, temperature, and sample counts.",
            "Run the same FIIR audit, offline validation import, and reporting on both outputs.",
        ],
    }
    write_json(manifest_path, manifest)
    run_script_path.write_text(_run_script(command, config.crystalformer_work_dir), encoding="utf-8")
    run_script_path.chmod(0o755)
    report_path.write_text(render_dpo_smoke_run_report(manifest), encoding="utf-8")

    return {
        "manifest": manifest,
        "files": {
            "manifest": str(manifest_path),
            "report": str(report_path),
            "run_script": str(run_script_path),
            "chosen_sequences": str(chosen_path),
            "rejected_sequences": str(rejected_path),
            "pair_index": str(pair_index_path),
        },
    }


def render_dpo_smoke_run_report(manifest: dict[str, Any]) -> str:
    """Render a concise report for the prepared DPO smoke run."""

    lines = [
        "# CrystalFormer DPO Smoke Run",
        "",
        "## Safety",
        "- This preparation step did not run training.",
        "- The before checkpoint is used only through `--restore_path`.",
        "- The after checkpoint will be written under a separate `--folder` output root.",
        "",
        "## Inputs",
        f"- preference_pairs_jsonl: `{manifest['preference_pairs_jsonl']}`",
        f"- prepared_pair_count: {manifest['prepared_pair_count']}",
        f"- base_checkpoint_dir: `{manifest['base_checkpoint_dir']}`",
        "",
        "## Outputs",
        f"- training_output_root: `{manifest['training_output_root']}`",
        f"- chosen_sequences_jsonl: `{manifest['chosen_sequences_jsonl']}`",
        f"- rejected_sequences_jsonl: `{manifest['rejected_sequences_jsonl']}`",
        "",
        "## Recommended Command",
        "",
        "```bash",
        f"cd {shlex.quote(manifest['crystalformer_work_dir'])}",
        manifest["recommended_training_command"],
        "```",
        "",
    ]
    return "\n".join(lines)


def _validate_smoke_config(config: CrystalFormerDpoSmokeRunConfig) -> None:
    if not config.preference_pairs_jsonl.exists():
        raise FileNotFoundError(f"preference pairs JSONL does not exist: {config.preference_pairs_jsonl}")
    if not config.base_checkpoint_dir.exists():
        raise FileNotFoundError(f"base checkpoint dir does not exist: {config.base_checkpoint_dir}")
    if not config.crystalformer_work_dir.exists():
        raise FileNotFoundError(f"CrystalFormer work dir does not exist: {config.crystalformer_work_dir}")
    if config.epochs < 1:
        raise ValueError("epochs must be >= 1")
    if config.batchsize < 1:
        raise ValueError("batchsize must be >= 1")
    if config.optimizer not in {"adam", "adamw"}:
        raise ValueError("optimizer must be adam or adamw")
    _ensure_non_overwrite(config.base_checkpoint_dir, _training_output_root(config))


def _ensure_non_overwrite(base_checkpoint_dir: Path, training_output_root: Path) -> None:
    base = base_checkpoint_dir.resolve()
    output = training_output_root.resolve()
    if output == base:
        raise ValueError("training output root must not equal the base checkpoint dir")
    if _is_relative_to(output, base):
        raise ValueError("training output root must not be inside the base checkpoint dir")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _training_output_root(config: CrystalFormerDpoSmokeRunConfig) -> Path:
    return config.output_dir / "after_checkpoint"


def _sequence_rows(
    pairs: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    chosen_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    for index, pair in enumerate(pairs):
        chosen_rows.append(_sequence_row(pair, "chosen", index))
        rejected_rows.append(_sequence_row(pair, "rejected", index))
        index_rows.append(
            {
                "row_index": index,
                "pair_id": pair["pair_id"],
                "condition": pair.get("condition", {}),
                "chosen_candidate_id": pair["chosen_candidate_id"],
                "rejected_candidate_id": pair["rejected_candidate_id"],
                "chosen_score": pair.get("chosen_score"),
                "rejected_score": pair.get("rejected_score"),
                "preference_margin": pair.get("preference_margin"),
                "preference_type": pair.get("preference_type"),
            }
        )
    return chosen_rows, rejected_rows, index_rows


def _sequence_row(pair: dict[str, Any], side: str, row_index: int) -> dict[str, Any]:
    sequence = pair[f"{side}_sequence"]
    return {
        "row_index": row_index,
        "pair_id": pair["pair_id"],
        "candidate_id": pair[f"{side}_candidate_id"],
        "condition": pair.get("condition", {}),
        "g": _parse_scalar_int(sequence.get("g")),
        "L": _parse_float_list(sequence.get("L"), expected_len=6, field="L"),
        "X": _parse_matrix(sequence.get("X"), field="X"),
        "A": _parse_int_list(sequence.get("A"), field="A"),
        "W": _parse_int_list(sequence.get("W"), field="W"),
    }


def _parse_sequence_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty sequence value")
        try:
            return ast.literal_eval(stripped)
        except (SyntaxError, ValueError):
            return stripped
    return value


def _parse_scalar_int(value: Any) -> int:
    parsed = _parse_sequence_value(value)
    return int(parsed)


def _parse_float_list(value: Any, *, expected_len: int, field: str) -> list[float]:
    parsed = _parse_sequence_value(value)
    if not isinstance(parsed, list) or len(parsed) != expected_len:
        raise ValueError(f"{field} must be a list of length {expected_len}")
    return [float(item) for item in parsed]


def _parse_int_list(value: Any, *, field: str) -> list[int]:
    parsed = _parse_sequence_value(value)
    if not isinstance(parsed, list):
        raise ValueError(f"{field} must be a list")
    return [int(item) for item in parsed]


def _parse_matrix(value: Any, *, field: str) -> list[list[float]]:
    parsed = _parse_sequence_value(value)
    if not isinstance(parsed, list) or not all(isinstance(row, list) and len(row) == 3 for row in parsed):
        raise ValueError(f"{field} must be a list of 3D coordinate rows")
    return [[float(item) for item in row] for row in parsed]


def _training_command(config: CrystalFormerDpoSmokeRunConfig, chosen_path: Path, rejected_path: Path) -> str:
    start_epoch = _latest_checkpoint_epoch(config.base_checkpoint_dir)
    target_epoch = config.epochs if start_epoch is None else start_epoch + config.epochs
    args: list[str] = [
        "python",
        "-m",
        "crystalformer.cli.train_dpo",
        "--restore_path",
        str(config.base_checkpoint_dir.resolve()),
        "--folder",
        _folder_arg(_training_output_root(config)),
        "--chosen_path",
        str(chosen_path.resolve()),
        "--rejected_path",
        str(rejected_path.resolve()),
        "--epochs",
        str(target_epoch),
        "--batchsize",
        str(config.batchsize),
        "--lr",
        str(config.lr),
        "--optimizer",
        config.optimizer,
        "--beta",
        str(config.beta),
        "--label_smoothing",
        str(config.label_smoothing),
        "--gamma",
        str(config.gamma),
        "--val_ratio",
        str(config.val_ratio),
        "--num_io_process",
        str(config.num_io_process),
    ]
    for key, value in DEFAULT_CRYSTALFORMER_MODEL_ARGS.items():
        args.extend([f"--{key}", str(value)])
    return " ".join(shlex.quote(arg) for arg in args)


def _latest_checkpoint_epoch(path: Path) -> int | None:
    if path.is_file():
        return _checkpoint_epoch(path)
    epochs = [epoch for checkpoint in path.glob("epoch_*.pkl") if (epoch := _checkpoint_epoch(checkpoint)) is not None]
    return max(epochs) if epochs else None


def _checkpoint_epoch(path: Path) -> int | None:
    stem = path.stem
    if not stem.startswith("epoch_"):
        return None
    value = stem.removeprefix("epoch_")
    return int(value) if value.isdigit() else None


def _folder_arg(path: Path) -> str:
    resolved = str(path.resolve())
    return resolved if resolved.endswith("/") else f"{resolved}/"


def _run_script(command: str, crystalformer_work_dir: Path) -> str:
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            "# Run this from an allocated compute node with the CrystalFormer environment active.",
            f"cd {shlex.quote(str(crystalformer_work_dir.resolve()))}",
            command,
            "",
        ]
    )
