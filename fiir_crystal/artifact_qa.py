"""Local-only QA checks for CrystalFormer bulk/audit/DPO artifacts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.collection import (
    JSON_ARTIFACTS,
    JSONL_ARTIFACTS,
    ArtifactRead,
    CollectionConfig,
    collect_crystalformer_bulk_results,
    discover_artifact_files,
    read_artifact,
    resolve_scan_roots,
)
from fiir_crystal.dpo.preference_builder import (
    GEOMETRY_CHEMISTRY_ONLY,
    SEQUENCE_FIELDS,
    STABILITY_AWARE_OFFLINE_VALIDATION,
)
from fiir_crystal.io import read_json, write_json, write_jsonl


CRITICAL = "critical"
WARNING = "warning"
INFO = "info"
ALLOWED_ZERO_PAIR_REASONS = {
    "no_comparable_margin",
    "no_eligible_candidates",
    "no_comparable_candidates",
    "condition_group_too_small",
}


@dataclass(slots=True)
class ArtifactQAFailure:
    """One QA finding."""

    severity: str
    check: str
    message: str
    path: str | None = None
    formula: str | None = None
    candidate_id: str | None = None
    pair_id: str | None = None
    line_no: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "check": self.check,
            "message": self.message,
            "path": self.path,
            "formula": self.formula,
            "candidate_id": self.candidate_id,
            "pair_id": self.pair_id,
            "line_no": self.line_no,
        }


@dataclass(slots=True)
class ArtifactQAConfig:
    """Configuration for artifact QA."""

    input_roots: tuple[Path, ...] = ()
    glob_patterns: tuple[str, ...] = ()
    collection_summary: Path | None = None
    output_dir: Path = Path("outputs/crystalformer_bulk_qa")
    strict: bool = False
    fail_on_critical: bool = False
    max_examples: int = 20


def check_crystalformer_bulk_artifacts(config: ArtifactQAConfig) -> dict[str, Any]:
    """Run local QA checks and write QA outputs."""

    roots = resolve_scan_roots(config.input_roots, config.glob_patterns)
    reads: list[ArtifactRead] = []
    failures: list[ArtifactQAFailure] = []
    for root in roots:
        files = discover_artifact_files(root)
        if _looks_in_progress(root, files):
            failures.append(
                ArtifactQAFailure(
                    severity=CRITICAL if config.strict else WARNING,
                    check="partial_or_in_progress_root",
                    message="root has a bulk plan but no completed bulk summary",
                    path=str(root),
                )
            )
        for path in files:
            read = read_artifact(root, path)
            reads.append(read)
            failures.extend(_read_failures(read, strict=config.strict))

    collection_data = _load_collection_summary(config.collection_summary, failures)
    failures.extend(_collection_status_failures(collection_data, strict=config.strict))

    candidate_index = _build_candidate_index(reads, failures)
    failures.extend(_check_candidate_uniqueness(candidate_index))
    failures.extend(_check_audit_candidates(reads))
    failures.extend(_check_preference_pairs(reads, candidate_index))
    failures.extend(_check_zero_pair_summaries(reads))
    failures.extend(_info_counts(reads, roots))

    failures = sorted(
        failures,
        key=lambda item: (
            _severity_order(item.severity),
            item.check,
            item.formula or "",
            item.candidate_id or "",
            item.pair_id or "",
            item.path or "",
            item.line_no or 0,
        ),
    )
    severity_counts = Counter(failure.severity for failure in failures)
    check_counts = Counter(failure.check for failure in failures)
    summary = {
        "workflow": "crystalformer_bulk_artifact_qa",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "scanned_root_count": len(roots),
        "scanned_roots": [str(root) for root in roots],
        "critical_count": severity_counts.get(CRITICAL, 0),
        "warning_count": severity_counts.get(WARNING, 0),
        "info_count": severity_counts.get(INFO, 0),
        "severity_counts": dict(sorted(severity_counts.items())),
        "check_counts": dict(sorted(check_counts.items())),
        "ready": severity_counts.get(CRITICAL, 0) == 0,
        "failure_examples": [
            failure.to_dict() for failure in failures[: max(0, config.max_examples)]
        ],
        "collection_summary": None if config.collection_summary is None else str(config.collection_summary),
    }
    files = write_qa_outputs(config.output_dir, summary, failures)
    return {"summary": summary, "failures": failures, "files": files}


def write_qa_outputs(
    output_dir: str | Path,
    summary: dict[str, Any],
    failures: Sequence[ArtifactQAFailure],
) -> dict[str, str]:
    """Write QA summary, findings, tables, and report."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(destination / "qa_summary.json"),
        "failures": str(destination / "qa_failures.jsonl"),
        "table": str(destination / "qa_table.md"),
        "report": str(destination / "report.md"),
    }
    write_json(files["summary"], summary)
    write_jsonl(files["failures"], (failure.to_dict() for failure in failures))
    Path(files["table"]).write_text(render_qa_table(failures), encoding="utf-8")
    Path(files["report"]).write_text(render_qa_report(summary), encoding="utf-8")
    return files


def render_qa_table(failures: Sequence[ArtifactQAFailure]) -> str:
    """Render QA findings as a Markdown table."""

    lines = [
        "| severity | check | formula | candidate | pair | path | message |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for failure in failures:
        lines.append(
            "| {severity} | {check} | {formula} | {candidate} | {pair} | `{path}` | {message} |".format(
                severity=failure.severity,
                check=failure.check,
                formula=failure.formula or "",
                candidate=failure.candidate_id or "",
                pair=failure.pair_id or "",
                path=failure.path or "",
                message=str(failure.message).replace("|", "\\|"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_qa_report(summary: dict[str, Any]) -> str:
    """Render a concise Markdown QA report."""

    lines = [
        "# CrystalFormer Bulk Artifact QA Report",
        "",
        "## Boundary",
        "- This QA gate reads local artifacts only.",
        "- It does not run generation, training, DFT, MLIP, downloads, or external APIs.",
        "- F3/stability-aware checks require imported offline validation or pair-level MLIP force evidence.",
        "",
        "## Summary",
        f"- ready: {summary['ready']}",
        f"- scanned_root_count: {summary['scanned_root_count']}",
        f"- critical_count: {summary['critical_count']}",
        f"- warning_count: {summary['warning_count']}",
        f"- info_count: {summary['info_count']}",
        f"- severity_counts: {summary['severity_counts']}",
        f"- check_counts: {summary['check_counts']}",
        "",
        "## Findings",
        "- See `qa_failures.jsonl` and `qa_table.md`.",
        "",
    ]
    return "\n".join(lines)


def _read_failures(read: ArtifactRead, *, strict: bool) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    for error in read.errors:
        if error.issue == "empty_artifact":
            severity = WARNING
            if error.artifact in JSON_ARTIFACTS:
                severity = CRITICAL
            elif strict and error.artifact in JSONL_ARTIFACTS:
                severity = CRITICAL
            check = "empty_artifact"
        elif error.issue == "malformed_jsonl":
            severity = CRITICAL
            check = "malformed_jsonl"
        elif error.issue == "corrupt_json":
            severity = CRITICAL
            check = "corrupt_json"
        else:
            severity = WARNING
            check = error.issue
        failures.append(
            ArtifactQAFailure(
                severity=severity,
                check=check,
                message=error.message,
                path=error.path,
                formula=error.formula,
                line_no=error.line_no,
            )
        )
    return failures


def _build_candidate_index(
    reads: Sequence[ArtifactRead],
    failures: list[ArtifactQAFailure],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for read in reads:
        if not read.ok or read.artifact not in {"candidates.jsonl", "audit_candidates.jsonl"}:
            continue
        for row in read.rows:
            candidate_id = _candidate_id(row)
            formula = _formula(row)
            generation = _generation(row)
            if not candidate_id:
                failures.append(
                    ArtifactQAFailure(
                        severity=CRITICAL,
                        check="missing_candidate_id",
                        message="candidate row is missing candidate_id",
                        path=str(read.path),
                        formula=formula,
                    )
                )
                continue
            if not formula:
                failures.append(
                    ArtifactQAFailure(
                        severity=WARNING,
                        check="missing_formula",
                        message="candidate row has no formula or condition.formula",
                        path=str(read.path),
                        candidate_id=candidate_id,
                    )
                )
            index[candidate_id].append(
                {
                    "candidate_id": candidate_id,
                    "formula": formula,
                    "generation": generation,
                    "spacegroup": _spacegroup(row),
                    "root": str(read.root),
                    "path": str(read.path),
                    "artifact": read.artifact,
                    "row": row,
                }
            )
    return index


def _check_candidate_uniqueness(index: dict[str, list[dict[str, Any]]]) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    seen: set[tuple[str | None, str, str, str]] = set()
    for candidate_id, entries in sorted(index.items()):
        for entry in entries:
            formula = entry.get("formula")
            key = (
                str(entry.get("root")),
                formula,
                _generation_label(entry.get("generation")),
                candidate_id,
                str(entry.get("artifact")),
            )
            if key in seen:
                failures.append(
                    ArtifactQAFailure(
                        severity=CRITICAL,
                        check="duplicate_candidate_id",
                        message="candidate_id appears more than once within a formula/generation condition",
                        path=entry["path"],
                        formula=formula,
                        candidate_id=candidate_id,
                    )
                )
            else:
                seen.add(key)
    return failures


def _check_audit_candidates(reads: Sequence[ArtifactRead]) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    for read in reads:
        if not read.ok or read.artifact != "audit_candidates.jsonl":
            continue
        for row in read.rows:
            candidate_id = _candidate_id(row)
            formula = _formula(row)
            for field_name in ("f3_label", "failure_vector", "dpo_eligible"):
                if field_name not in row:
                    failures.append(
                        ArtifactQAFailure(
                            severity=WARNING,
                            check="missing_expected_audit_field",
                            message=f"audit candidate missing {field_name}",
                            path=str(read.path),
                            formula=formula,
                            candidate_id=candidate_id,
                        )
                    )
            if _claims_stable_without_f3(row):
                failures.append(
                    ArtifactQAFailure(
                        severity=CRITICAL,
                        check="fabricated_f3_or_stability",
                        message="candidate reports stable/pass F3 while F3 is unavailable or unvalidated",
                        path=str(read.path),
                        formula=formula,
                        candidate_id=candidate_id,
                    )
                )
    return failures


def _check_preference_pairs(
    reads: Sequence[ArtifactRead],
    candidate_index: dict[str, list[dict[str, Any]]],
) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    for read in reads:
        if not read.ok or read.artifact != "preference_pairs.jsonl":
            continue
        for row in read.rows:
            pair_id = None if row.get("pair_id") in (None, "") else str(row["pair_id"])
            formula = _formula(row)
            condition = row.get("condition")
            if not isinstance(condition, dict):
                failures.append(_pair_failure(read, row, CRITICAL, "missing_condition", "pair missing condition"))
                condition = {}
            chosen_id = _pair_candidate_id(row, "chosen_candidate_id")
            rejected_id = _pair_candidate_id(row, "rejected_candidate_id")
            if not chosen_id or not rejected_id:
                failures.append(_pair_failure(read, row, CRITICAL, "missing_pair_candidate_id", "pair missing chosen/rejected candidate id"))
                continue
            if chosen_id == rejected_id:
                failures.append(_pair_failure(read, row, CRITICAL, "same_chosen_rejected", "chosen and rejected candidate ids are identical"))
            chosen_entries = candidate_index.get(chosen_id, [])
            rejected_entries = candidate_index.get(rejected_id, [])
            if not chosen_entries:
                failures.append(_pair_failure(read, row, CRITICAL, "missing_chosen_candidate", "chosen candidate id not found in candidates/audit candidates"))
            if not rejected_entries:
                failures.append(_pair_failure(read, row, CRITICAL, "missing_rejected_candidate", "rejected candidate id not found in candidates/audit candidates"))
            root = str(read.root)
            chosen_entry = _best_candidate_entry(chosen_entries, formula, root)
            rejected_entry = _best_candidate_entry(rejected_entries, formula, root)
            failures.extend(_check_pair_condition(read, row, chosen_entry, rejected_entry))
            failures.extend(_check_pair_scores(read, row))
            failures.extend(_check_pair_sequences(read, row))
            if row.get("preference_type") == STABILITY_AWARE_OFFLINE_VALIDATION:
                if not _pair_has_imported_f3(row, chosen_entry, rejected_entry):
                    failures.append(
                        _pair_failure(
                            read,
                            row,
                            CRITICAL,
                            "stability_preference_without_f3",
                            "stability-aware pair lacks imported F3/offline validation or pair-level MLIP force evidence",
                        )
                    )
            elif row.get("preference_type") not in {GEOMETRY_CHEMISTRY_ONLY, STABILITY_AWARE_OFFLINE_VALIDATION}:
                failures.append(
                    ArtifactQAFailure(
                        severity=WARNING,
                        check="unsupported_preference_type",
                        message=f"unsupported preference_type: {row.get('preference_type')}",
                        path=str(read.path),
                        formula=formula,
                        pair_id=pair_id,
                    )
                )
    return failures


def _check_pair_condition(
    read: ArtifactRead,
    row: dict[str, Any],
    chosen: dict[str, Any] | None,
    rejected: dict[str, Any] | None,
) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    formula = _formula(row)
    chosen_formula = _explicit_or_entry_formula(row, "chosen", chosen)
    rejected_formula = _explicit_or_entry_formula(row, "rejected", rejected)
    if chosen_formula and rejected_formula and chosen_formula != rejected_formula:
        failures.append(_pair_failure(read, row, CRITICAL, "cross_formula_pair", "chosen and rejected formulas differ"))
    for side, side_formula in (("chosen", chosen_formula), ("rejected", rejected_formula)):
        if formula and side_formula and formula != side_formula:
            failures.append(_pair_failure(read, row, CRITICAL, "formula_mismatch", f"{side} formula differs from pair condition"))

    chosen_generation = _explicit_or_entry_generation(row, "chosen", chosen)
    rejected_generation = _explicit_or_entry_generation(row, "rejected", rejected)
    if chosen_generation is not None and rejected_generation is not None and _normalize_generation(chosen_generation) != _normalize_generation(rejected_generation):
        failures.append(_pair_failure(read, row, CRITICAL, "cross_generation_condition_pair", "chosen and rejected generation conditions differ"))
    pair_generation = _generation(row)
    for side, side_generation in (("chosen", chosen_generation), ("rejected", rejected_generation)):
        if side_generation is not None and _normalize_generation(pair_generation) != _normalize_generation(side_generation):
            failures.append(_pair_failure(read, row, CRITICAL, "generation_condition_mismatch", f"{side} generation differs from pair condition"))

    chosen_spacegroup = _explicit_or_entry_spacegroup(row, "chosen", chosen)
    rejected_spacegroup = _explicit_or_entry_spacegroup(row, "rejected", rejected)
    if chosen_spacegroup is not None and rejected_spacegroup is not None and chosen_spacegroup != rejected_spacegroup:
        failures.append(_pair_failure(read, row, CRITICAL, "cross_spacegroup_condition_pair", "chosen and rejected spacegroup conditions differ"))
    return failures


def _check_pair_scores(read: ArtifactRead, row: dict[str, Any]) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    chosen_score = _optional_float(row.get("chosen_score"))
    rejected_score = _optional_float(row.get("rejected_score"))
    margin = _optional_float(row.get("preference_margin"))
    if chosen_score is not None and rejected_score is not None and chosen_score > rejected_score:
        failures.append(_pair_failure(read, row, CRITICAL, "chosen_score_worse_than_rejected", "chosen_score is larger than rejected_score"))
    if chosen_score is not None and rejected_score is not None and margin is not None:
        expected = round(rejected_score - chosen_score, 12)
        if abs(expected - margin) > 1e-9:
            failures.append(_pair_failure(read, row, CRITICAL, "preference_margin_inconsistent", "preference_margin does not equal rejected_score - chosen_score"))
        if margin <= 0.0:
            failures.append(_pair_failure(read, row, CRITICAL, "non_positive_preference_margin", "preference_margin must be positive"))
    return failures


def _check_pair_sequences(read: ArtifactRead, row: dict[str, Any]) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    if not _has_sequence_or_equivalent(row, "chosen_sequence", "chosen"):
        failures.append(_pair_failure(read, row, CRITICAL, "chosen_missing_sequence_fields", "chosen side lacks g/W/A/X/L or documented equivalent raw sequence"))
    if not _has_sequence_or_equivalent(row, "rejected_sequence", "rejected"):
        failures.append(_pair_failure(read, row, CRITICAL, "rejected_missing_sequence_fields", "rejected side lacks g/W/A/X/L or documented equivalent raw sequence"))
    return failures


def _check_zero_pair_summaries(reads: Sequence[ArtifactRead]) -> list[ArtifactQAFailure]:
    failures: list[ArtifactQAFailure] = []
    pair_rows_by_dir: dict[Path, int] = {}
    for read in reads:
        if read.artifact == "preference_pairs.jsonl":
            pair_rows_by_dir[read.path.parent] = len(read.rows) if read.ok else 0
    for read in reads:
        if not read.ok or read.artifact != "preference_summary.json" or not isinstance(read.data, dict):
            continue
        pair_count = _safe_int(read.data.get("pair_count"))
        if pair_count != 0 and pair_rows_by_dir.get(read.path.parent, pair_count) != 0:
            continue
        reasons = set(str(reason) for reason in dict(read.data.get("skip_reasons", {})).keys())
        reasons.update(str(reason) for reason in dict(read.data.get("pair_skip_reasons", {})).keys())
        severity = WARNING if reasons & ALLOWED_ZERO_PAIR_REASONS else CRITICAL
        failures.append(
            ArtifactQAFailure(
                severity=severity,
                check="zero_preference_pairs",
                message=(
                    "zero pairs with documented reason"
                    if severity == WARNING
                    else "zero pairs without a documented no-comparable/no-eligible reason"
                ),
                path=str(read.path),
                formula=_formula(read.data) or _formula_from_summary_path(read.path),
            )
        )
    return failures


def _info_counts(reads: Sequence[ArtifactRead], roots: Sequence[Path]) -> list[ArtifactQAFailure]:
    artifact_counts = Counter(read.artifact for read in reads)
    return [
        ArtifactQAFailure(
            severity=INFO,
            check="artifact_counts",
            message=json.dumps(dict(sorted(artifact_counts.items())), sort_keys=True),
            path=";".join(str(root) for root in roots),
        )
    ]


def _load_collection_summary(
    path: Path | None,
    failures: list[ArtifactQAFailure],
) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(
            ArtifactQAFailure(
                severity=WARNING,
                check="collection_summary_unreadable",
                message=str(exc),
                path=str(path),
            )
        )
        return None
    return data if isinstance(data, dict) else None


def _collection_status_failures(
    collection_data: dict[str, Any] | None,
    *,
    strict: bool,
) -> list[ArtifactQAFailure]:
    if not collection_data:
        return []
    failures: list[ArtifactQAFailure] = []
    formula_status = collection_data.get("formula_status")
    if isinstance(formula_status, dict):
        for formula, status in sorted(formula_status.items()):
            if status == "in_progress":
                failures.append(
                    ArtifactQAFailure(
                        severity=CRITICAL if strict else WARNING,
                        check="partial_or_in_progress_formula",
                        message="collection summary reports formula in progress",
                        formula=str(formula),
                    )
                )
    return failures


def _looks_in_progress(root: Path, files: Sequence[Path]) -> bool:
    root_names = {path.name for path in files if path.parent == root}
    return "bulk_plan.json" in root_names and "bulk_summary.json" not in root_names


def _pair_failure(
    read: ArtifactRead,
    row: dict[str, Any],
    severity: str,
    check: str,
    message: str,
) -> ArtifactQAFailure:
    return ArtifactQAFailure(
        severity=severity,
        check=check,
        message=message,
        path=str(read.path),
        formula=_formula(row),
        pair_id=None if row.get("pair_id") in (None, "") else str(row["pair_id"]),
    )


def _best_candidate_entry(
    entries: Sequence[dict[str, Any]],
    formula: str | None,
    root: str | None = None,
) -> dict[str, Any] | None:
    if not entries:
        return None
    for entry in entries:
        if (
            root
            and entry.get("root") == root
            and formula
            and entry.get("formula") == formula
            and entry.get("artifact") == "audit_candidates.jsonl"
        ):
            return entry
    for entry in entries:
        if root and entry.get("root") == root and formula and entry.get("formula") == formula:
            return entry
    for entry in entries:
        if root and entry.get("root") == root and entry.get("artifact") == "audit_candidates.jsonl":
            return entry
    for entry in entries:
        if root and entry.get("root") == root:
            return entry
    for entry in entries:
        if formula and entry.get("formula") == formula and entry.get("artifact") == "audit_candidates.jsonl":
            return entry
    for entry in entries:
        if formula and entry.get("formula") == formula:
            return entry
    for entry in entries:
        if entry.get("artifact") == "audit_candidates.jsonl":
            return entry
    return entries[0]


def _candidate_id(row: dict[str, Any]) -> str | None:
    value = row.get("candidate_id", row.get("sample_id"))
    return None if value in (None, "") else str(value)


def _pair_candidate_id(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return None if value in (None, "") else str(value)


def _formula(row: dict[str, Any]) -> str | None:
    condition = row.get("condition")
    if isinstance(condition, dict) and condition.get("formula") not in (None, ""):
        return str(condition["formula"])
    if row.get("formula") not in (None, ""):
        return str(row["formula"])
    if row.get("composition") not in (None, ""):
        return str(row["composition"])
    return None


def _generation(row: dict[str, Any]) -> dict[str, Any]:
    condition = row.get("condition")
    if isinstance(condition, dict) and isinstance(condition.get("generation"), dict):
        return _normalize_generation(condition["generation"])
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        generation = {
            "source_checkpoint": metadata.get("source_checkpoint"),
            "temperature": metadata.get("temperature"),
            "top_k": metadata.get("top_k"),
            "K": metadata.get("K"),
        }
        return _normalize_generation(generation)
    return {}


def _spacegroup(row: dict[str, Any]) -> int | None:
    condition = row.get("condition")
    value = condition.get("spacegroup") if isinstance(condition, dict) else row.get("spacegroup")
    return _optional_int(value)


def _normalize_generation(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(value[key]) for key in sorted(value) if value[key] not in (None, "")}


def _generation_label(value: Any) -> str:
    return json.dumps(_normalize_generation(value), sort_keys=True)


def _explicit_or_entry_formula(row: dict[str, Any], side: str, entry: dict[str, Any] | None) -> str | None:
    for key in (f"{side}_formula", f"{side}_condition"):
        value = row.get(key)
        if isinstance(value, dict) and value.get("formula"):
            return str(value["formula"])
        if isinstance(value, str) and value:
            return value
    return None if entry is None else entry.get("formula")


def _explicit_or_entry_generation(row: dict[str, Any], side: str, entry: dict[str, Any] | None) -> dict[str, Any] | None:
    for key in (f"{side}_generation", f"{side}_condition"):
        value = row.get(key)
        if isinstance(value, dict):
            return value.get("generation") if isinstance(value.get("generation"), dict) else value
    return None if entry is None else entry.get("generation")


def _explicit_or_entry_spacegroup(row: dict[str, Any], side: str, entry: dict[str, Any] | None) -> int | None:
    for key in (f"{side}_spacegroup", f"{side}_condition"):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("spacegroup")
        parsed = _optional_int(value)
        if parsed is not None:
            return parsed
    return None if entry is None else entry.get("spacegroup")


def _claims_stable_without_f3(row: dict[str, Any]) -> bool:
    f3_available = bool(row.get("f3_validation_available"))
    validation_status = str(row.get("validation_status", "")).lower()
    evidence = row.get("evidence")
    evidence_f3_status = evidence.get("f3_status") if isinstance(evidence, dict) else None
    f3_label = str(row.get("f3_label", "")).lower()
    offline_validation = row.get("offline_validation")
    claims_stable = f3_label in {"pass", "stable"} or (
        isinstance(offline_validation, dict) and offline_validation.get("is_stable") is True
    )
    f3_unavailable = evidence_f3_status in {"unknown", "unavailable", "unknown_unavailable"} or not f3_available
    return claims_stable and (f3_unavailable or validation_status not in {"validated_success", "success", "validated", "completed"})


def _pair_has_imported_f3(
    row: dict[str, Any],
    chosen: dict[str, Any] | None,
    rejected: dict[str, Any] | None,
) -> bool:
    if _pair_has_mlip_force_evidence(row):
        return True
    if chosen is not None and rejected is not None:
        return _candidate_has_successful_f3(chosen["row"]) and _candidate_has_successful_f3(rejected["row"])
    return _failure_vector_has_imported_f3(row.get("chosen_failure_vector")) and _failure_vector_has_imported_f3(
        row.get("rejected_failure_vector")
    )


def _candidate_has_successful_f3(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("f3_validation_available"))
        and str(row.get("validation_status")) == "validated_success"
        and isinstance(row.get("offline_validation"), dict)
    )


def _failure_vector_has_imported_f3(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("f3_stability") is None:
        return False
    metadata = value.get("metadata")
    return isinstance(metadata, dict) and metadata.get("f3_status") == "offline_validation_imported"


def _pair_has_mlip_force_evidence(row: dict[str, Any]) -> bool:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("f3_pair_rule") != "same_formula_rank_neighbor_f3_pairing_v1":
        return False
    return _has_mlip_force_evidence(metadata.get("chosen_mlip_force_evidence")) and _has_mlip_force_evidence(
        metadata.get("rejected_mlip_force_evidence")
    )


def _has_mlip_force_evidence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    forces = value.get("model_forces")
    if not isinstance(forces, dict):
        return False
    return all(_optional_float(forces.get(model)) is not None for model in ("MACE", "CHGNet", "MatGL"))


def _has_sequence_or_equivalent(row: dict[str, Any], sequence_key: str, side: str) -> bool:
    sequence = row.get(sequence_key)
    if isinstance(sequence, dict) and all(sequence.get(field) not in (None, "", []) for field in SEQUENCE_FIELDS):
        return True
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return False
    equivalent = metadata.get(f"{side}_raw_sequence_equivalent") or metadata.get("raw_sequence_equivalent")
    documented = metadata.get("documented_raw_sequence_fields")
    return bool(equivalent or documented)


def _formula_from_summary_path(path: Path) -> str | None:
    parts = path.parts
    for marker in ("dpo_preferences", "crystalformer_audit"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    return None


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


def _safe_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _severity_order(severity: str) -> int:
    return {CRITICAL: 0, WARNING: 1, INFO: 2}.get(severity, 3)
