"""CrystalFormer DPO training boundary preparation.

This module does not implement or run DPO training. It validates FIIR-produced
preference artifacts, checks the external CrystalFormer workspace shape, and
writes a manifest that an explicit external trainer command can consume later.
"""

from __future__ import annotations

import shlex
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.dpo.preference_builder import (
    GEOMETRY_CHEMISTRY_ONLY,
    SEQUENCE_FIELDS,
    STABILITY_AWARE_OFFLINE_VALIDATION,
)
from fiir_crystal.generation.crystalformer_workspace import (
    CrystalFormerWorkspaceCheckConfig,
    check_crystalformer_workspace,
)
from fiir_crystal.io import read_jsonl, write_json


TRAINING_BOUNDARY_NAME = "crystalformer_dpo_training_adapter_boundary"


@dataclass(slots=True)
class TrainingBoundaryConfig:
    """Configuration for preparing an external CrystalFormer training manifest."""

    preference_pairs_jsonl: Path
    output_dir: Path
    crystalformer_work_dir: Path = Path("external/CrystalFormer")
    checkpoint_dir: Path = Path("external/checkpoints")
    require_workspace: bool = True
    require_submodule_for_training: bool = False
    training_command: str | None = None
    run_training: bool = False


@dataclass(slots=True)
class PairValidationSummary:
    """Preference-pair validation result for the training boundary."""

    input_pair_count: int
    valid_pair_count: int
    invalid_pair_count: int
    invalid_reasons: dict[str, int]
    preference_type_breakdown: dict[str, int]
    condition_count: int
    condition_breakdown: dict[str, int]
    stability_aware_pair_count: int = 0
    geometry_chemistry_pair_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_pair_count": self.input_pair_count,
            "valid_pair_count": self.valid_pair_count,
            "invalid_pair_count": self.invalid_pair_count,
            "invalid_reasons": dict(self.invalid_reasons),
            "preference_type_breakdown": dict(self.preference_type_breakdown),
            "condition_count": self.condition_count,
            "condition_breakdown": dict(self.condition_breakdown),
            "stability_aware_pair_count": self.stability_aware_pair_count,
            "geometry_chemistry_pair_count": self.geometry_chemistry_pair_count,
        }


@dataclass(slots=True)
class TrainingBoundarySummary:
    """Readiness summary for the external CrystalFormer DPO training boundary."""

    boundary: str
    train_dpo_in_fiir: bool
    preference_pairs_jsonl: str
    output_dir: str
    pair_validation: dict[str, Any]
    workspace: dict[str, Any]
    ready_for_external_training: bool
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest_path: str | None = None
    provenance_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary,
            "train_dpo_in_fiir": self.train_dpo_in_fiir,
            "preference_pairs_jsonl": self.preference_pairs_jsonl,
            "output_dir": self.output_dir,
            "pair_validation": dict(self.pair_validation),
            "workspace": dict(self.workspace),
            "ready_for_external_training": self.ready_for_external_training,
            "blocking_reasons": list(self.blocking_reasons),
            "warnings": list(self.warnings),
            "manifest_path": self.manifest_path,
            "provenance_path": self.provenance_path,
        }


def prepare_crystalformer_dpo_training_boundary(
    config: TrainingBoundaryConfig,
) -> dict[str, Any]:
    """Validate preferences and write a CrystalFormer trainer handoff manifest."""

    _validate_config(config)
    pairs = read_jsonl(config.preference_pairs_jsonl)
    pair_summary = validate_preference_pairs_for_training(pairs)
    workspace_summary = check_crystalformer_workspace(
        CrystalFormerWorkspaceCheckConfig(
            repo_root=Path("."),
            crystalformer_dir=config.crystalformer_work_dir,
            checkpoint_dir=config.checkpoint_dir,
            create_output_dirs=False,
        )
    )
    summary = _build_summary(config, pair_summary, workspace_summary)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _build_manifest(config, pairs, summary)
    manifest_path = config.output_dir / "trainer_manifest.json"
    summary_path = config.output_dir / "training_boundary_summary.json"
    report_path = config.output_dir / "report.md"
    provenance_path = config.output_dir / "training_command_provenance.json"

    summary.manifest_path = str(manifest_path)
    summary.provenance_path = str(provenance_path)
    write_json(manifest_path, manifest)
    write_json(summary_path, summary)
    report_path.write_text(render_training_boundary_report(summary), encoding="utf-8")

    provenance = _command_provenance(config, executed=False, reason="run_training_not_requested")
    if config.run_training:
        provenance = _run_training_command(config)
    write_json(provenance_path, provenance)

    return {
        "summary": summary.to_dict(),
        "manifest": manifest,
        "files": {
            "manifest": str(manifest_path),
            "summary": str(summary_path),
            "report": str(report_path),
            "provenance": str(provenance_path),
        },
    }


def validate_preference_pairs_for_training(
    pairs: Sequence[dict[str, Any]],
) -> PairValidationSummary:
    """Validate DPO preference-pair rows for external CrystalFormer handoff."""

    invalid: Counter[str] = Counter()
    preference_types: Counter[str] = Counter()
    condition_counts: Counter[str] = Counter()
    valid_count = 0
    for row in pairs:
        preference_type = str(row.get("preference_type", "missing"))
        preference_types[preference_type] += 1
        condition_counts[_condition_label(row.get("condition"))] += 1
        reasons = _pair_invalid_reasons(row)
        if reasons:
            invalid.update(reasons)
        else:
            valid_count += 1

    return PairValidationSummary(
        input_pair_count=len(pairs),
        valid_pair_count=valid_count,
        invalid_pair_count=len(pairs) - valid_count,
        invalid_reasons=dict(sorted(invalid.items())),
        preference_type_breakdown=dict(sorted(preference_types.items())),
        condition_count=len(condition_counts),
        condition_breakdown=dict(sorted(condition_counts.items())),
        stability_aware_pair_count=preference_types.get(STABILITY_AWARE_OFFLINE_VALIDATION, 0),
        geometry_chemistry_pair_count=preference_types.get(GEOMETRY_CHEMISTRY_ONLY, 0),
    )


def render_training_boundary_report(summary: TrainingBoundarySummary) -> str:
    """Render a concise Markdown report for the training boundary."""

    data = summary.to_dict()
    pair = data["pair_validation"]
    workspace = data["workspace"].get("crystalformer", {})
    lines = [
        "# CrystalFormer DPO Training Boundary Report",
        "",
        "## Boundary",
        "- FIIR Crystal does not implement DPO training.",
        "- CrystalFormer, JAX, torch, pymatgen, and ASE remain outside core dependencies.",
        "- Any real training must happen through an explicit external command in the CrystalFormer workspace.",
        "",
        "## Readiness",
        f"- ready_for_external_training: {data['ready_for_external_training']}",
        f"- blocking_reasons: {data['blocking_reasons']}",
        f"- warnings: {data['warnings']}",
        "",
        "## Preference Artifact",
        f"- preference_pairs_jsonl: `{data['preference_pairs_jsonl']}`",
        f"- input_pair_count: {pair['input_pair_count']}",
        f"- valid_pair_count: {pair['valid_pair_count']}",
        f"- invalid_pair_count: {pair['invalid_pair_count']}",
        f"- invalid_reasons: {pair['invalid_reasons']}",
        f"- preference_type_breakdown: {pair['preference_type_breakdown']}",
        "",
        "## Workspace",
        f"- crystalformer_dir: `{workspace.get('relative_path', 'unknown')}`",
        f"- clone_state: {workspace.get('clone_state', 'unknown')}",
        "",
    ]
    return "\n".join(lines)


def _validate_config(config: TrainingBoundaryConfig) -> None:
    if not config.preference_pairs_jsonl.exists():
        raise FileNotFoundError(f"preference pairs JSONL does not exist: {config.preference_pairs_jsonl}")
    if config.run_training:
        if not config.training_command:
            raise ValueError("--run-training requires --training-command.")
        if not config.crystalformer_work_dir.exists():
            raise FileNotFoundError(f"CrystalFormer work dir does not exist: {config.crystalformer_work_dir}")


def _build_summary(
    config: TrainingBoundaryConfig,
    pair_summary: PairValidationSummary,
    workspace_summary: dict[str, Any],
) -> TrainingBoundarySummary:
    blocking: list[str] = []
    warnings: list[str] = []
    workspace = workspace_summary["crystalformer"]
    if pair_summary.input_pair_count == 0:
        blocking.append("no_preference_pairs")
    if pair_summary.invalid_pair_count:
        blocking.append("invalid_preference_pairs")
    if config.require_workspace and not workspace.get("exists"):
        blocking.append("crystalformer_workspace_missing")
    if config.require_submodule_for_training and not workspace.get("is_submodule"):
        blocking.append("crystalformer_submodule_required")
    if workspace.get("clone_state") == "normal_clone":
        warnings.append("normal_clone_ok_for_smoke_but_submodule_or_fork_recommended_for_training")
    if pair_summary.stability_aware_pair_count == 0:
        warnings.append("no_stability_aware_pairs_available")

    return TrainingBoundarySummary(
        boundary=TRAINING_BOUNDARY_NAME,
        train_dpo_in_fiir=False,
        preference_pairs_jsonl=str(config.preference_pairs_jsonl),
        output_dir=str(config.output_dir),
        pair_validation=pair_summary.to_dict(),
        workspace=workspace_summary,
        ready_for_external_training=not blocking,
        blocking_reasons=blocking,
        warnings=warnings,
    )


def _build_manifest(
    config: TrainingBoundaryConfig,
    pairs: Sequence[dict[str, Any]],
    summary: TrainingBoundarySummary,
) -> dict[str, Any]:
    data = config.preference_pairs_jsonl.read_bytes()
    return {
        "manifest_type": TRAINING_BOUNDARY_NAME,
        "train_dpo_in_fiir": False,
        "external_training_only": True,
        "preference_pairs_jsonl": str(config.preference_pairs_jsonl),
        "preference_pairs_sha256": sha256(data).hexdigest(),
        "preference_pair_count": len(pairs),
        "pair_validation": summary.pair_validation,
        "workspace": summary.workspace.get("crystalformer", {}),
        "checkpoint_dir": str(config.checkpoint_dir),
        "training_command": config.training_command,
        "run_training_requested": config.run_training,
        "required_external_dependencies": ["CrystalFormer", "JAX", "torch"],
        "not_core_dependencies": ["CrystalFormer", "JAX", "torch", "pymatgen", "ASE"],
        "next_manual_steps": [
            "Review trainer_manifest.json and report.md.",
            "Use a recorded CrystalFormer fork or submodule for code changes.",
            "Run external training only with an explicit command from that workspace.",
        ],
    }


def _pair_invalid_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in ("pair_id", "condition", "chosen_candidate_id", "rejected_candidate_id"):
        if row.get(key) in (None, ""):
            reasons.append(f"missing_{key}")
    if not isinstance(row.get("condition"), dict):
        reasons.append("missing_condition")
    if row.get("chosen_candidate_id") == row.get("rejected_candidate_id"):
        reasons.append("same_chosen_and_rejected")
    chosen_score = _optional_float(row.get("chosen_score"))
    rejected_score = _optional_float(row.get("rejected_score"))
    margin = _optional_float(row.get("preference_margin"))
    if chosen_score is None or rejected_score is None:
        reasons.append("missing_scores")
    elif chosen_score > rejected_score:
        reasons.append("chosen_score_worse_than_rejected")
    if margin is None or margin <= 0.0:
        reasons.append("non_positive_preference_margin")
    if not _has_full_sequence(row.get("chosen_sequence")):
        reasons.append("chosen_missing_sequence_fields")
    if not _has_full_sequence(row.get("rejected_sequence")):
        reasons.append("rejected_missing_sequence_fields")
    preference_type = row.get("preference_type")
    if preference_type not in {GEOMETRY_CHEMISTRY_ONLY, STABILITY_AWARE_OFFLINE_VALIDATION}:
        reasons.append("unsupported_preference_type")
    if preference_type == STABILITY_AWARE_OFFLINE_VALIDATION and not _has_pair_f3_evidence(row):
        reasons.append("stability_aware_missing_f3_evidence")
    return sorted(set(reasons))


def _has_pair_f3_evidence(row: dict[str, Any]) -> bool:
    chosen = row.get("chosen_failure_vector")
    rejected = row.get("rejected_failure_vector")
    if not isinstance(chosen, dict) or not isinstance(rejected, dict):
        return False
    return chosen.get("f3_stability") is not None and rejected.get("f3_stability") is not None


def _has_full_sequence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(value.get(field) not in (None, "", []) for field in SEQUENCE_FIELDS)


def _condition_label(value: Any) -> str:
    if not isinstance(value, dict):
        return "missing_condition"
    generation = value.get("generation")
    generation_label = ""
    if isinstance(generation, dict):
        generation_label = ",".join(f"{key}={generation[key]}" for key in sorted(generation))
    return "|".join(
        [
            str(value.get("mode", "csp")),
            str(value.get("formula")),
            str(value.get("spacegroup")),
            generation_label,
        ]
    )


def _command_provenance(
    config: TrainingBoundaryConfig,
    *,
    executed: bool,
    reason: str | None = None,
    returncode: int | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
) -> dict[str, Any]:
    return {
        "executed": executed,
        "reason": reason,
        "command": config.training_command,
        "cwd": str(config.crystalformer_work_dir),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def _run_training_command(config: TrainingBoundaryConfig) -> dict[str, Any]:
    args = shlex.split(str(config.training_command))
    completed = subprocess.run(
        args,
        cwd=str(config.crystalformer_work_dir),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return _command_provenance(
        config,
        executed=True,
        reason=None,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return float(value)
