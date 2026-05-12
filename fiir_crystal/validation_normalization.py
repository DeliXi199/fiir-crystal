"""Normalize local offline validation outputs into FIIR-compatible JSONL.

This module reads validation results that already exist on disk. It never runs
DFT, MLIP, relaxation, downloads, or external APIs.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.io import read_jsonl, write_json, write_jsonl


SUPPORTED_INPUT_FORMATS = {"auto", "csv", "json", "jsonl"}
SUCCESS_STATUSES = {"completed", "success", "succeeded", "validated"}


@dataclass(slots=True)
class NormalizationIssue:
    """A non-fatal normalization issue."""

    input_path: str
    reason: str
    message: str
    row_index: int | None = None
    candidate_id: str | None = None
    formula: str | None = None
    row: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "reason": self.reason,
            "message": self.message,
            "row_index": self.row_index,
            "candidate_id": self.candidate_id,
            "formula": self.formula,
            "row": dict(self.row),
        }


@dataclass(slots=True)
class ValidationNormalizationConfig:
    """Configuration for local offline validation normalization."""

    inputs: tuple[Path, ...]
    input_format: str = "auto"
    output_jsonl: Path = Path("outputs/offline_validation_normalized/validation_results.jsonl")
    output_summary: Path = Path("outputs/offline_validation_normalized/normalization_summary.json")
    report: Path = Path("outputs/offline_validation_normalized/report.md")
    candidate_index: Path | None = None
    strict: bool = False
    derive_stability_from_relaxation: bool = False
    relaxation_stability_force_max: float = 0.05
    relaxation_stability_stress_max: float | None = None
    relaxation_stability_require_converged: bool = True


def normalize_offline_validation_results(
    config: ValidationNormalizationConfig,
) -> dict[str, Any]:
    """Normalize local validation rows and write JSONL, summary, and report."""

    _validate_config(config)
    candidate_index, index_issues = _load_candidate_index(config.candidate_index)
    rows: list[dict[str, Any]] = []
    issues: list[NormalizationIssue] = list(index_issues)
    unmatched: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    calibration_counts: Counter[str] = Counter()
    seen_candidate_ids: Counter[str] = Counter()

    for input_path in config.inputs:
        raw_rows, read_issues = read_validation_input(input_path, config.input_format)
        issues.extend(read_issues)
        for row_index, raw_row in enumerate(raw_rows, start=1):
            normalized, row_issues = normalize_validation_row(
                raw_row,
                input_path=input_path,
                row_index=row_index,
                derive_stability_from_relaxation=config.derive_stability_from_relaxation,
                relaxation_stability_force_max=config.relaxation_stability_force_max,
                relaxation_stability_stress_max=config.relaxation_stability_stress_max,
                relaxation_stability_require_converged=config.relaxation_stability_require_converged,
            )
            issues.extend(row_issues)
            if normalized is None:
                continue
            rows.append(normalized)
            source_counts[str(normalized["validation_source"])] += 1
            status_counts[str(normalized["validation_status"])] += 1
            calibration_counts[str(normalized["calibration_tier"])] += 1
            seen_candidate_ids[str(normalized["candidate_id"])] += 1
            if candidate_index is not None:
                index_issue = _check_against_candidate_index(normalized, candidate_index, input_path, row_index)
                if index_issue is not None:
                    issues.append(index_issue)
                    unmatched.append(index_issue.to_dict())

    for candidate_id, count in sorted(seen_candidate_ids.items()):
        if count > 1:
            issues.append(
                NormalizationIssue(
                    input_path=";".join(str(path) for path in config.inputs),
                    reason="duplicate_validation_candidate_id",
                    message=f"candidate_id appears {count} times in normalized validation rows",
                    candidate_id=candidate_id,
                )
            )

    rows = sorted(rows, key=lambda row: (str(row["formula"]), str(row["candidate_id"]), str(row.get("validator"))))
    summary = {
        "workflow": "offline_validation_normalization",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "input_paths": [str(path) for path in config.inputs],
        "input_format": config.input_format,
        "candidate_index": None if config.candidate_index is None else str(config.candidate_index),
        "normalized_row_count": len(rows),
        "issue_count": len(issues),
        "malformed_row_count": sum(issue.reason == "malformed_row" for issue in issues),
        "missing_required_field_count": sum(issue.reason == "missing_required_field" for issue in issues),
        "unmatched_candidate_id_count": sum(issue.reason == "candidate_not_found" for issue in issues),
        "formula_mismatch_count": sum(issue.reason == "formula_mismatch" for issue in issues),
        "duplicate_validation_candidate_id_count": sum(
            issue.reason == "duplicate_validation_candidate_id" for issue in issues
        ),
        "failed_or_incomplete_count": sum(not _status_is_success(row["validation_status"]) for row in rows),
        "f3_available_candidate_count": sum(_row_has_f3_evidence(row) for row in rows),
        "validation_source_breakdown": dict(sorted(source_counts.items())),
        "validation_status_breakdown": dict(sorted(status_counts.items())),
        "calibration_tier_breakdown": dict(sorted(calibration_counts.items())),
        "strict": config.strict,
        "derive_stability_from_relaxation": config.derive_stability_from_relaxation,
        "relaxation_stability_force_max": config.relaxation_stability_force_max,
        "relaxation_stability_stress_max": config.relaxation_stability_stress_max,
        "relaxation_stability_require_converged": config.relaxation_stability_require_converged,
    }
    files = write_normalization_outputs(config, rows, summary, issues, unmatched)
    return {
        "summary": summary,
        "rows": rows,
        "issues": issues,
        "unmatched": unmatched,
        "files": files,
    }


def read_validation_input(
    path: str | Path,
    input_format: str = "auto",
) -> tuple[list[dict[str, Any]], list[NormalizationIssue]]:
    """Read CSV, JSONL, or JSON validation input into dictionaries."""

    source = Path(path)
    fmt = _resolve_format(source, input_format)
    issues: list[NormalizationIssue] = []
    try:
        if fmt == "csv":
            with source.open("r", encoding="utf-8", newline="") as handle:
                rows = [dict(row) for row in csv.DictReader(handle)]
        elif fmt == "jsonl":
            rows = read_jsonl(source)
        elif fmt == "json":
            data = json.loads(source.read_text(encoding="utf-8"))
            rows = _rows_from_json(data)
        else:
            raise ValueError(f"unsupported input format: {fmt}")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [], [
            NormalizationIssue(
                input_path=str(source),
                reason="input_read_error",
                message=str(exc),
            )
        ]
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            issues.append(
                NormalizationIssue(
                    input_path=str(source),
                    reason="malformed_row",
                    message="validation input row must be an object",
                    row_index=index,
                )
            )
    return [row for row in rows if isinstance(row, dict)], issues


def normalize_validation_row(
    row: dict[str, Any],
    *,
    input_path: str | Path,
    row_index: int,
    derive_stability_from_relaxation: bool = False,
    relaxation_stability_force_max: float = 0.05,
    relaxation_stability_stress_max: float | None = None,
    relaxation_stability_require_converged: bool = True,
) -> tuple[dict[str, Any] | None, list[NormalizationIssue]]:
    """Normalize one validation row into the canonical local schema."""

    issues: list[NormalizationIssue] = []
    condition = _as_dict(row.get("condition"))
    generation = _generation_condition(row, condition)
    candidate_id = _string_or_none(_first(row, "candidate_id", "id", "sample_id"))
    formula = _string_or_none(_first(row, "formula", "composition", default=condition.get("formula")))
    validation_source = _string_or_none(_first(row, "validation_source", "source", "validator"))
    missing = [
        name
        for name, value in (
            ("candidate_id", candidate_id),
            ("formula", formula),
            ("validation_source", validation_source),
        )
        if value in (None, "")
    ]
    if missing:
        issues.append(
            NormalizationIssue(
                input_path=str(input_path),
                reason="missing_required_field",
                message="missing required field(s): " + ",".join(missing),
                row_index=row_index,
                candidate_id=candidate_id,
                formula=formula,
                row=dict(row),
            )
        )
        return None, issues

    validator = _string_or_none(_first(row, "validator", "model", "mlip", default=validation_source))
    validation_status = _normalize_status(_first(row, "validation_status", "status", default="unknown"))
    calibration_tier = _normalize_calibration_tier(_first(row, "calibration_tier", "tier", default="unknown"))
    energy_above_hull = _optional_float(_first(row, "energy_above_hull", "e_above_hull", "ehull", "e_hull"))
    formation_energy = _optional_float(_first(row, "formation_energy", "formation_energy_per_atom"))
    relaxed = _optional_bool(_first(row, "relaxed", "structure_relaxed"))
    relaxation_converged = _optional_bool(_first(row, "relaxation_converged", "converged"))
    force_max = _optional_float(_first(row, "force_max", "fmax", "max_force"))
    stress_max = _optional_float(_first(row, "stress_max", "max_stress"))
    uncertainty = _optional_float(_first(row, "uncertainty", "energy_uncertainty", "e_above_hull_std"))
    spacegroup = _optional_int(_first(row, "spacegroup", default=condition.get("spacegroup")))
    source_checkpoint = _string_or_none(_first(row, "source_checkpoint", default=generation.get("source_checkpoint")))
    top_k = _string_or_none(_first(row, "top_k", default=generation.get("top_k")))
    big_k = _string_or_none(_first(row, "K", "k", default=generation.get("K")))
    temperature = _string_or_none(_first(row, "temperature", default=generation.get("temperature")))
    if source_checkpoint is not None:
        generation["source_checkpoint"] = source_checkpoint
    if top_k is not None:
        generation["top_k"] = top_k
    if big_k is not None:
        generation["K"] = big_k
    if temperature is not None:
        generation["temperature"] = temperature
    generation = _clean_generation(generation)
    is_stable = _optional_bool(row.get("is_stable"))
    relaxation_proxy_reason: str | None = None
    if is_stable is None and derive_stability_from_relaxation:
        is_stable, relaxation_proxy_reason = _derive_stability_from_relaxation(
            row,
            force_max=force_max,
            stress_max=stress_max,
            force_threshold=relaxation_stability_force_max,
            stress_threshold=relaxation_stability_stress_max,
            require_converged=relaxation_stability_require_converged,
        )

    metadata = _as_dict(row.get("metadata"))
    metadata.setdefault("normalization_source_path", str(input_path))
    metadata.setdefault("normalization_source_row_index", row_index)
    if "validator" not in metadata:
        metadata["validator"] = validator
    if relaxation_proxy_reason is not None:
        metadata["relaxation_stability_proxy"] = {
            "enabled": True,
            "source": "normalization_relaxation_thresholds",
            "derived_is_stable": is_stable,
            "reason": relaxation_proxy_reason,
            "force_max": force_max,
            "force_threshold": relaxation_stability_force_max,
            "stress_max": stress_max,
            "stress_threshold": relaxation_stability_stress_max,
            "require_converged": relaxation_stability_require_converged,
            "relaxation_converged": _optional_bool(row.get("relaxation_converged")),
        }
    metadata["f3_available_after_normalization"] = _status_is_success(validation_status) and (
        energy_above_hull is not None or is_stable is not None
    )

    normalized = {
        "candidate_id": candidate_id,
        "formula": formula,
        "validation_status": validation_status,
        "validator": validator,
        "validation_source": validation_source,
        "calibration_tier": calibration_tier,
        "energy_above_hull": energy_above_hull,
        "e_above_hull": energy_above_hull,
        "formation_energy": formation_energy,
        "relaxed": relaxed,
        "relaxation_converged": relaxation_converged,
        "force_max": force_max,
        "stress_max": stress_max,
        "uncertainty": uncertainty,
        "spacegroup": spacegroup,
        "source_checkpoint": source_checkpoint,
        "generation_condition": dict(generation),
        "top_k": top_k,
        "K": big_k,
        "temperature": temperature,
        "condition": {
            "mode": condition.get("mode", "csp"),
            "formula": formula,
            "spacegroup": spacegroup,
            "generation": dict(generation),
        },
        "is_stable": is_stable,
        "relaxed_structure_ref": _string_or_none(row.get("relaxed_structure_ref")),
        "error_reason": _string_or_none(_first(row, "error_reason", "error_message", "error")),
        "metadata": metadata,
    }
    return normalized, issues


def write_normalization_outputs(
    config: ValidationNormalizationConfig,
    rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    issues: Sequence[NormalizationIssue],
    unmatched: Sequence[dict[str, Any]],
) -> dict[str, str]:
    """Write normalized JSONL, summary, unmatched rows, and report."""

    config.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    config.output_summary.parent.mkdir(parents=True, exist_ok=True)
    config.report.parent.mkdir(parents=True, exist_ok=True)
    unmatched_path = config.output_jsonl.parent / "unmatched_validation_rows.jsonl"
    alias_path = config.output_jsonl.parent / "normalized_validation_results.jsonl"
    write_jsonl(config.output_jsonl, rows)
    if alias_path != config.output_jsonl:
        write_jsonl(alias_path, rows)
    write_json(config.output_summary, summary)
    write_jsonl(unmatched_path, unmatched)
    config.report.write_text(render_normalization_report(summary), encoding="utf-8")
    return {
        "normalized_validation_results": str(config.output_jsonl),
        "normalized_validation_results_alias": str(alias_path),
        "normalization_summary": str(config.output_summary),
        "unmatched_validation_rows": str(unmatched_path),
        "report": str(config.report),
    }


def render_normalization_report(summary: dict[str, Any]) -> str:
    """Render a concise Markdown normalization report."""

    lines = [
        "# Offline Validation Normalization Report",
        "",
        "## Boundary",
        "- This workflow reads local validation result files only.",
        "- It does not run validators, DFT, MLIP, relaxation, downloads, or external APIs.",
        "- Failed or incomplete rows remain explicit and do not make F3 available.",
        "",
        "## Summary",
        f"- normalized_row_count: {summary['normalized_row_count']}",
        f"- issue_count: {summary['issue_count']}",
        f"- missing_required_field_count: {summary['missing_required_field_count']}",
        f"- unmatched_candidate_id_count: {summary['unmatched_candidate_id_count']}",
        f"- formula_mismatch_count: {summary['formula_mismatch_count']}",
        f"- failed_or_incomplete_count: {summary['failed_or_incomplete_count']}",
        f"- f3_available_candidate_count: {summary['f3_available_candidate_count']}",
        f"- validation_source_breakdown: {summary['validation_source_breakdown']}",
        f"- validation_status_breakdown: {summary['validation_status_breakdown']}",
        f"- calibration_tier_breakdown: {summary['calibration_tier_breakdown']}",
        f"- derive_stability_from_relaxation: {summary.get('derive_stability_from_relaxation', False)}",
        "",
    ]
    return "\n".join(lines)


def _validate_config(config: ValidationNormalizationConfig) -> None:
    if not config.inputs:
        raise ValueError("at least one --input is required")
    if config.input_format not in SUPPORTED_INPUT_FORMATS:
        raise ValueError(f"unsupported input format: {config.input_format}")
    for path in config.inputs:
        if not path.exists():
            raise FileNotFoundError(f"validation input does not exist: {path}")


def _resolve_format(path: Path, input_format: str) -> str:
    if input_format != "auto":
        return input_format
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    return "jsonl"


def _rows_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("validation_results", "results", "rows", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [data]
    raise ValueError("JSON input must be an object, list, or object containing rows")


def _load_candidate_index(path: Path | None) -> tuple[dict[str, dict[str, Any]] | None, list[NormalizationIssue]]:
    if path is None:
        return None, []
    issues: list[NormalizationIssue] = []
    try:
        rows = read_jsonl(path)
    except Exception as exc:
        return None, [
            NormalizationIssue(
                input_path=str(path),
                reason="candidate_index_read_error",
                message=str(exc),
            )
        ]
    index: dict[str, dict[str, Any]] = {}
    for row_index, row in enumerate(rows, start=1):
        candidate_id = _string_or_none(_first(row, "candidate_id", "id", "sample_id"))
        if candidate_id is None:
            continue
        formula = _string_or_none(_first(row, "formula", "composition"))
        condition = _as_dict(row.get("condition"))
        if formula is None:
            formula = _string_or_none(condition.get("formula"))
        index[candidate_id] = {
            "candidate_id": candidate_id,
            "formula": formula,
            "generation": _generation_condition(row, condition),
            "row_index": row_index,
        }
    return index, issues


def _check_against_candidate_index(
    row: dict[str, Any],
    candidate_index: dict[str, dict[str, Any]],
    input_path: Path,
    row_index: int,
) -> NormalizationIssue | None:
    candidate_id = str(row["candidate_id"])
    indexed = candidate_index.get(candidate_id)
    if indexed is None:
        return NormalizationIssue(
            input_path=str(input_path),
            reason="candidate_not_found",
            message="validation candidate_id was not found in candidate index",
            row_index=row_index,
            candidate_id=candidate_id,
            formula=str(row.get("formula")),
            row=row,
        )
    indexed_formula = indexed.get("formula")
    if indexed_formula and indexed_formula != row.get("formula"):
        return NormalizationIssue(
            input_path=str(input_path),
            reason="formula_mismatch",
            message=f"validation formula {row.get('formula')} does not match candidate index formula {indexed_formula}",
            row_index=row_index,
            candidate_id=candidate_id,
            formula=str(row.get("formula")),
            row=row,
        )
    return None


def _generation_condition(row: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any]:
    generation = _as_dict(row.get("generation_condition"))
    if not generation:
        generation = _as_dict(condition.get("generation"))
    for key in ("source_checkpoint", "source_model", "temperature", "top_k", "K"):
        value = row.get(key)
        if value not in (None, ""):
            generation[key] = value
    return _clean_generation(generation)


def _clean_generation(value: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value[key]) for key in sorted(value) if value[key] not in (None, "")}


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _string_or_none(value: Any) -> str | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "null", "None", "none"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value in (None, "", "null", "None", "none"):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"true", "yes", "1", "stable", "pass", "passed"}:
        return True
    if lowered in {"false", "no", "0", "unstable", "fail", "failed"}:
        return False
    return None


def _derive_stability_from_relaxation(
    row: dict[str, Any],
    *,
    force_max: float | None,
    stress_max: float | None,
    force_threshold: float,
    stress_threshold: float | None,
    require_converged: bool,
) -> tuple[bool | None, str | None]:
    relaxed = _optional_bool(row.get("relaxed", row.get("structure_relaxed")))
    metadata = _as_dict(row.get("metadata"))
    relax_requested = _optional_bool(metadata.get("relax_requested"))
    if relaxed is not True and relax_requested is not True:
        return None, None
    if force_max is None:
        return None, "missing_force_max"

    converged = _optional_bool(row.get("relaxation_converged", row.get("converged")))
    if require_converged and converged is not True:
        return False, "relaxation_not_converged"
    if force_max > force_threshold:
        return False, "force_above_relaxation_stability_threshold"
    if stress_threshold is not None and stress_max is not None and stress_max > stress_threshold:
        return False, "stress_above_relaxation_stability_threshold"
    if stress_threshold is not None and stress_max is None:
        return False, "missing_stress_max"
    return True, "relaxation_converged_below_thresholds"


def _normalize_status(value: Any) -> str:
    raw = "unknown" if value in (None, "") else str(value).strip().lower()
    mapping = {
        "complete": "completed",
        "ok": "success",
        "done": "completed",
        "error": "failed",
        "failure": "failed",
        "not_converged": "failed",
    }
    return mapping.get(raw, raw)


def _normalize_calibration_tier(value: Any) -> str:
    if value in (None, "", "null", "None", "none"):
        return "unknown"
    text = str(value).strip()
    if text.lower() == "unknown":
        return "unknown"
    if text.isdigit():
        return f"tier{text}"
    return text


def _status_is_success(value: Any) -> bool:
    return str(value).lower() in SUCCESS_STATUSES


def _row_has_f3_evidence(row: dict[str, Any]) -> bool:
    return _status_is_success(row.get("validation_status")) and (
        row.get("energy_above_hull") is not None or row.get("is_stable") is not None
    )
