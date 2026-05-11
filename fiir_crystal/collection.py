"""Local-only collection of CrystalFormer bulk, audit, and DPO artifacts.

The collector reads existing files and writes reports to a caller-selected
output directory. It does not run generation, validation, training, DFT, MLIP,
or external APIs.
"""

from __future__ import annotations

import glob
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from fiir_crystal.io import write_json, write_jsonl


JSON_ARTIFACTS = {
    "bulk_plan.json",
    "bulk_summary.json",
    "bulk_validation_summary.json",
    "audit_summary.json",
    "preference_summary.json",
}
JSONL_ARTIFACTS = {
    "candidates.jsonl",
    "audit_candidates.jsonl",
    "failure_vectors.jsonl",
    "preference_pairs.jsonl",
}
TEXT_ARTIFACTS = {"report.md", "validate_report.md"}
KNOWN_ARTIFACTS = JSON_ARTIFACTS | JSONL_ARTIFACTS | TEXT_ARTIFACTS
AUDIT_EXPECTED = {
    "candidates.jsonl",
    "audit_candidates.jsonl",
    "audit_summary.json",
    "failure_vectors.jsonl",
    "report.md",
}
PREFERENCE_EXPECTED = {"preference_pairs.jsonl", "preference_summary.json", "report.md"}
AUDIT_CONTEXT_ARTIFACTS = AUDIT_EXPECTED - {"report.md"}
PREFERENCE_CONTEXT_ARTIFACTS = PREFERENCE_EXPECTED - {"report.md"}
BULK_EXPECTED_ANY_SUMMARY = {"bulk_summary.json", "bulk_validation_summary.json"}


@dataclass(slots=True)
class ArtifactError:
    """Problem observed while collecting an artifact."""

    root: str
    path: str
    artifact: str
    issue: str
    message: str
    formula: str | None = None
    line_no: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "path": self.path,
            "artifact": self.artifact,
            "issue": self.issue,
            "message": self.message,
            "formula": self.formula,
            "line_no": self.line_no,
        }


@dataclass(slots=True)
class ArtifactRead:
    """Parsed artifact plus non-fatal read errors."""

    root: Path
    path: Path
    artifact: str
    data: Any = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[ArtifactError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class FormulaCollection:
    """Formula-level collection state."""

    formula: str
    roots: set[str] = field(default_factory=set)
    artifact_paths: set[str] = field(default_factory=set)
    candidate_ids: set[str] = field(default_factory=set)
    audit_candidate_ids: set[str] = field(default_factory=set)
    dpo_eligible_ids: set[str] = field(default_factory=set)
    preference_pair_keys: set[str] = field(default_factory=set)
    statuses: list[str] = field(default_factory=list)
    blocking_reasons: Counter[str] = field(default_factory=Counter)
    timing: dict[str, Any] = field(default_factory=dict)
    candidate_count_estimate: int = 0
    audit_candidate_count_estimate: int = 0
    dpo_eligible_count_estimate: int = 0
    preference_pair_count_estimate: int = 0

    def final_status(self) -> str:
        statuses = {status for status in self.statuses if status}
        if "failed" in statuses or "generation_failed" in statuses:
            return "failed"
        completed = {"succeeded", "smoke_from_existing", "completed", "validated_ready"}
        if statuses & completed:
            return "completed"
        if self.preference_pair_keys or self.audit_candidate_ids or self.candidate_ids:
            return "in_progress"
        return "in_progress"

    def to_row(self) -> dict[str, Any]:
        candidate_count = max(len(self.candidate_ids), self.candidate_count_estimate)
        audit_count = max(len(self.audit_candidate_ids), self.audit_candidate_count_estimate)
        eligible_count = max(len(self.dpo_eligible_ids), self.dpo_eligible_count_estimate)
        pair_count = max(len(self.preference_pair_keys), self.preference_pair_count_estimate)
        return {
            "formula": self.formula,
            "status": self.final_status(),
            "roots": sorted(self.roots),
            "artifact_paths": sorted(self.artifact_paths),
            "candidate_count": candidate_count,
            "audit_candidate_count": audit_count,
            "dpo_eligible_count": eligible_count,
            "preference_pair_count": pair_count,
            "status_sources": list(self.statuses),
            "top_reasons": _top_counter(self.blocking_reasons),
            "timing": dict(sorted(self.timing.items())),
        }


@dataclass(slots=True)
class CollectionConfig:
    """Configuration for local CrystalFormer artifact collection."""

    output_roots: tuple[Path, ...] = ()
    glob_patterns: tuple[str, ...] = ()
    output_dir: Path = Path("outputs/crystalformer_bulk_collection")
    include_in_progress: bool = False
    strict: bool = False
    max_error_examples: int = 20


def collect_crystalformer_bulk_results(config: CollectionConfig) -> dict[str, Any]:
    """Collect local CrystalFormer bulk/audit/DPO outputs into report files."""

    roots = resolve_scan_roots(config.output_roots, config.glob_patterns)
    reads: list[ArtifactRead] = []
    errors: list[ArtifactError] = []
    for root in roots:
        files = discover_artifact_files(root)
        errors.extend(_missing_artifact_errors(root, files))
        for path in files:
            read = read_artifact(root, path)
            reads.append(read)
            errors.extend(read.errors)

    formula_state: dict[str, FormulaCollection] = {}
    root_summaries: list[dict[str, Any]] = []
    aggregate_reasons: Counter[str] = Counter()
    timing: dict[str, Any] = {}

    for root in roots:
        root_reads = [read for read in reads if read.root == root]
        root_summaries.append(_root_summary(root, root_reads))

    for read in sorted(reads, key=lambda item: str(item.path)):
        if not read.ok:
            formula = _formula_from_path(read.path)
            if formula:
                _formula_state(formula_state, formula).artifact_paths.add(str(read.path))
            continue
        _apply_artifact_read(formula_state, aggregate_reasons, timing, read)

    for error in errors:
        if error.formula:
            _formula_state(formula_state, error.formula).blocking_reasons[error.issue] += 1

    rows = [
        state.to_row()
        for formula, state in sorted(formula_state.items())
        if config.include_in_progress or state.candidate_ids or state.audit_candidate_ids or state.preference_pair_keys or state.final_status() != "in_progress"
    ]
    all_rows = [state.to_row() for _, state in sorted(formula_state.items())]
    status_counts = Counter(row["status"] for row in all_rows)
    missing_count = sum(error.issue == "missing_artifact" for error in errors)
    empty_count = sum(error.issue == "empty_artifact" for error in errors)
    corrupt_count = sum(
        error.issue in {"corrupt_json", "malformed_jsonl", "empty_artifact"}
        for error in errors
    )
    summary = {
        "workflow": "crystalformer_bulk_collection",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "scanned_root_count": len(roots),
        "scanned_roots": [str(root) for root in roots],
        "formula_count": len(all_rows),
        "completed_formula_count": status_counts.get("completed", 0),
        "failed_formula_count": status_counts.get("failed", 0),
        "in_progress_formula_count": status_counts.get("in_progress", 0),
        "missing_artifact_count": missing_count,
        "corrupt_artifact_count": corrupt_count,
        "empty_artifact_count": empty_count,
        "total_candidates": sum(int(row["candidate_count"]) for row in all_rows),
        "total_audit_candidates": sum(int(row["audit_candidate_count"]) for row in all_rows),
        "total_dpo_eligible": sum(int(row["dpo_eligible_count"]) for row in all_rows),
        "total_preference_pairs": sum(int(row["preference_pair_count"]) for row in all_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "top_failure_blocking_reasons": _top_counter(aggregate_reasons),
        "timing": timing,
        "root_summaries": root_summaries,
        "formula_status": {row["formula"]: row["status"] for row in all_rows},
        "artifact_error_examples": [
            error.to_dict() for error in errors[: max(0, config.max_error_examples)]
        ],
    }

    files = write_collection_outputs(config.output_dir, summary, rows, errors)
    return {"summary": summary, "formula_rows": rows, "errors": errors, "files": files}


def resolve_scan_roots(
    output_roots: Sequence[str | Path] = (),
    glob_patterns: Sequence[str] = (),
) -> list[Path]:
    """Resolve explicit roots and glob patterns into deterministic directories."""

    roots: set[Path] = set()
    for root in output_roots:
        roots.add(Path(root))
    for pattern in glob_patterns:
        for match in glob.glob(pattern):
            roots.add(Path(match))
    return sorted(roots, key=lambda path: str(path))


def discover_artifact_files(root: str | Path) -> list[Path]:
    """Find known CrystalFormer artifact files below a root."""

    source = Path(root)
    if source.is_file():
        return [source] if source.name in KNOWN_ARTIFACTS else []
    if not source.exists():
        return []
    return sorted(
        (path for path in source.rglob("*") if path.is_file() and path.name in KNOWN_ARTIFACTS),
        key=lambda path: str(path),
    )


def read_artifact(root: str | Path, path: str | Path) -> ArtifactRead:
    """Read a known artifact file without raising on malformed content."""

    root_path = Path(root)
    source = Path(path)
    artifact = source.name
    read = ArtifactRead(root=root_path, path=source, artifact=artifact)
    if _is_empty_file(source):
        read.errors.append(
            ArtifactError(
                root=str(root_path),
                path=str(source),
                artifact=artifact,
                issue="empty_artifact",
                message="artifact file is empty",
                formula=_formula_from_path(source),
            )
        )
        return read
    if artifact in JSON_ARTIFACTS:
        try:
            read.data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            read.errors.append(
                ArtifactError(
                    root=str(root_path),
                    path=str(source),
                    artifact=artifact,
                    issue="corrupt_json",
                    message=str(exc),
                    formula=_formula_from_path(source),
                )
            )
    elif artifact in JSONL_ARTIFACTS:
        rows: list[dict[str, Any]] = []
        try:
            with source.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        item = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        read.errors.append(
                            ArtifactError(
                                root=str(root_path),
                                path=str(source),
                                artifact=artifact,
                                issue="malformed_jsonl",
                                message=exc.msg,
                                formula=_formula_from_path(source),
                                line_no=line_no,
                            )
                        )
                        continue
                    if not isinstance(item, dict):
                        read.errors.append(
                            ArtifactError(
                                root=str(root_path),
                                path=str(source),
                                artifact=artifact,
                                issue="malformed_jsonl",
                                message="JSONL row must be an object",
                                formula=_formula_from_path(source),
                                line_no=line_no,
                            )
                        )
                        continue
                    rows.append(item)
        except OSError as exc:
            read.errors.append(
                ArtifactError(
                    root=str(root_path),
                    path=str(source),
                    artifact=artifact,
                    issue="malformed_jsonl",
                    message=str(exc),
                    formula=_formula_from_path(source),
                )
            )
        read.rows = rows
    else:
        read.data = {"size_bytes": source.stat().st_size if source.exists() else None}
    return read


def write_collection_outputs(
    output_dir: str | Path,
    summary: dict[str, Any],
    formula_rows: Sequence[dict[str, Any]],
    errors: Sequence[ArtifactError],
) -> dict[str, str]:
    """Write collection summary, tables, errors, and report."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(destination / "collection_summary.json"),
        "formula_table_jsonl": str(destination / "formula_table.jsonl"),
        "formula_table_md": str(destination / "formula_table.md"),
        "artifact_errors": str(destination / "artifact_errors.jsonl"),
        "error_table_md": str(destination / "error_table.md"),
        "report": str(destination / "report.md"),
    }
    write_json(files["summary"], summary)
    write_jsonl(files["formula_table_jsonl"], formula_rows)
    Path(files["formula_table_md"]).write_text(render_formula_table(formula_rows), encoding="utf-8")
    write_jsonl(files["artifact_errors"], (error.to_dict() for error in errors))
    Path(files["error_table_md"]).write_text(render_error_table(errors), encoding="utf-8")
    Path(files["report"]).write_text(render_collection_report(summary), encoding="utf-8")
    return files


def render_formula_table(rows: Sequence[dict[str, Any]]) -> str:
    """Render the formula table as Markdown."""

    lines = [
        "| formula | status | candidates | audit candidates | dpo eligible | preference pairs |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(rows, key=lambda item: str(item["formula"])):
        lines.append(
            "| {formula} | {status} | {candidate_count} | {audit_candidate_count} | "
            "{dpo_eligible_count} | {preference_pair_count} |".format(**row)
        )
    lines.append("")
    return "\n".join(lines)


def render_error_table(errors: Sequence[ArtifactError]) -> str:
    """Render artifact errors as Markdown."""

    lines = [
        "| artifact | issue | formula | line | path |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for error in errors:
        lines.append(
            "| {artifact} | {issue} | {formula} | {line} | `{path}` |".format(
                artifact=error.artifact,
                issue=error.issue,
                formula=error.formula or "",
                line="" if error.line_no is None else error.line_no,
                path=error.path,
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_collection_report(summary: dict[str, Any]) -> str:
    """Render a concise Markdown collection report."""

    lines = [
        "# CrystalFormer Bulk Collection Report",
        "",
        "## Boundary",
        "- This workflow reads local artifacts only.",
        "- It does not run generation, training, DFT, MLIP, downloads, or external APIs.",
        "- F3/stability labels are summarized only from existing imported evidence.",
        "",
        "## Summary",
        f"- scanned_root_count: {summary['scanned_root_count']}",
        f"- formula_count: {summary['formula_count']}",
        f"- completed_formula_count: {summary['completed_formula_count']}",
        f"- failed_formula_count: {summary['failed_formula_count']}",
        f"- in_progress_formula_count: {summary['in_progress_formula_count']}",
        f"- missing_artifact_count: {summary['missing_artifact_count']}",
        f"- corrupt_artifact_count: {summary['corrupt_artifact_count']}",
        f"- total_candidates: {summary['total_candidates']}",
        f"- total_audit_candidates: {summary['total_audit_candidates']}",
        f"- total_dpo_eligible: {summary['total_dpo_eligible']}",
        f"- total_preference_pairs: {summary['total_preference_pairs']}",
        f"- status_counts: {summary['status_counts']}",
        f"- top_failure_blocking_reasons: {summary['top_failure_blocking_reasons']}",
        "",
        "## Artifacts",
        "- See `formula_table.md` for formula-level status.",
        "- See `artifact_errors.jsonl` and `error_table.md` for missing, empty, corrupt, or malformed artifacts.",
        "",
    ]
    return "\n".join(lines)


def _apply_artifact_read(
    formula_state: dict[str, FormulaCollection],
    aggregate_reasons: Counter[str],
    timing: dict[str, Any],
    read: ArtifactRead,
) -> None:
    artifact = read.artifact
    path_formula = _formula_from_path(read.path)
    if artifact == "bulk_plan.json":
        for item in _items_from_mapping(read.data):
            formula = _formula_from_row(item) or path_formula
            if formula:
                state = _formula_state(formula_state, formula)
                _record_artifact(state, read)
                state.statuses.append("planned")
    elif artifact == "bulk_validation_summary.json":
        data = read.data if isinstance(read.data, dict) else {}
        for reason in data.get("blocking_reasons", []) or []:
            aggregate_reasons[str(reason)] += 1
        status = "validated_ready" if data.get("ready_for_generation") else "in_progress"
        for item in _items_from_mapping(data):
            formula = _formula_from_row(item) or path_formula
            if formula:
                state = _formula_state(formula_state, formula)
                _record_artifact(state, read)
                state.statuses.append(status)
                for reason in data.get("blocking_reasons", []) or []:
                    state.blocking_reasons[str(reason)] += 1
    elif artifact == "bulk_summary.json":
        data = read.data if isinstance(read.data, dict) else {}
        if isinstance(data.get("timing"), dict):
            timing[str(read.path)] = data["timing"]
        for item in _items_from_mapping(data):
            formula = _formula_from_row(item) or path_formula
            if not formula:
                continue
            state = _formula_state(formula_state, formula)
            _record_artifact(state, read)
            state.statuses.append(str(item.get("status", "unknown")))
            if item.get("error"):
                state.blocking_reasons[str(item["error"])] += 1
                aggregate_reasons[str(item["error"])] += 1
            smoke = item.get("smoke_summary")
            if isinstance(smoke, dict):
                state.candidate_count_estimate = max(
                    state.candidate_count_estimate, _safe_int(smoke.get("candidate_count"))
                )
                state.dpo_eligible_count_estimate = max(
                    state.dpo_eligible_count_estimate, _safe_int(smoke.get("dpo_eligible_count"))
                )
                state.preference_pair_count_estimate = max(
                    state.preference_pair_count_estimate, _safe_int(smoke.get("preference_pair_count"))
                )
                for reason, count in dict(smoke.get("preference_skip_reasons", {})).items():
                    aggregate_reasons[str(reason)] += _safe_int(count)
            if isinstance(item.get("total_duration_seconds"), (int, float)):
                state.timing["total_duration_seconds"] = item["total_duration_seconds"]
    elif artifact == "audit_summary.json":
        data = read.data if isinstance(read.data, dict) else {}
        formula = _formula_from_row(data) or path_formula
        if formula:
            state = _formula_state(formula_state, formula)
            _record_artifact(state, read)
            state.statuses.append("completed")
            state.candidate_count_estimate = max(
                state.candidate_count_estimate, _safe_int(data.get("total_candidates"))
            )
            state.audit_candidate_count_estimate = max(
                state.audit_candidate_count_estimate, _safe_int(data.get("total_candidates"))
            )
            state.dpo_eligible_count_estimate = max(
                state.dpo_eligible_count_estimate, _safe_int(data.get("dpo_eligible_count"))
            )
            for item in data.get("top_failure_reasons", []) or []:
                if isinstance(item, dict) and item.get("reason"):
                    count = _safe_int(item.get("count", 1))
                    state.blocking_reasons[str(item["reason"])] += count
                    aggregate_reasons[str(item["reason"])] += count
    elif artifact == "preference_summary.json":
        data = read.data if isinstance(read.data, dict) else {}
        formula = _formula_from_row(data) or path_formula
        if formula:
            state = _formula_state(formula_state, formula)
            _record_artifact(state, read)
            state.statuses.append("completed")
            state.preference_pair_count_estimate = max(
                state.preference_pair_count_estimate, _safe_int(data.get("pair_count"))
            )
            for group in ("skip_reasons", "candidate_skip_reasons", "pair_skip_reasons"):
                for reason, count in dict(data.get(group, {})).items():
                    state.blocking_reasons[str(reason)] += _safe_int(count)
                    aggregate_reasons[str(reason)] += _safe_int(count)
    elif artifact == "candidates.jsonl":
        for row in read.rows:
            formula = _formula_from_row(row) or path_formula
            if not formula:
                continue
            state = _formula_state(formula_state, formula)
            _record_artifact(state, read)
            candidate_id = _candidate_id(row)
            if candidate_id:
                state.candidate_ids.add(candidate_id)
    elif artifact == "audit_candidates.jsonl":
        for row in read.rows:
            formula = _formula_from_row(row) or path_formula
            if not formula:
                continue
            state = _formula_state(formula_state, formula)
            _record_artifact(state, read)
            candidate_id = _candidate_id(row)
            if candidate_id:
                state.audit_candidate_ids.add(candidate_id)
                if row.get("dpo_eligible") is True:
                    state.dpo_eligible_ids.add(candidate_id)
            for reason in row.get("dpo_ineligible_reasons", []) or []:
                state.blocking_reasons[str(reason)] += 1
                aggregate_reasons[str(reason)] += 1
    elif artifact == "failure_vectors.jsonl":
        formula = path_formula
        if formula:
            state = _formula_state(formula_state, formula)
            _record_artifact(state, read)
            for row in read.rows:
                for reason in row.get("hard_failures", []) or []:
                    state.blocking_reasons[str(reason)] += 1
                    aggregate_reasons[str(reason)] += 1
    elif artifact == "preference_pairs.jsonl":
        for row in read.rows:
            formula = _formula_from_row(row) or path_formula
            if not formula:
                continue
            state = _formula_state(formula_state, formula)
            _record_artifact(state, read)
            state.preference_pair_keys.add(_preference_pair_key(row))
            preference_type = row.get("preference_type")
            if preference_type:
                aggregate_reasons[f"preference_type:{preference_type}"] += 1
    elif artifact in TEXT_ARTIFACTS and path_formula:
        state = _formula_state(formula_state, path_formula)
        _record_artifact(state, read)


def _missing_artifact_errors(root: Path, files: Sequence[Path]) -> list[ArtifactError]:
    if root.is_file() or not root.exists():
        return []
    present_by_dir: dict[Path, set[str]] = defaultdict(set)
    for path in files:
        present_by_dir[path.parent].add(path.name)

    errors: list[ArtifactError] = []
    root_present = {path.name for path in files if path.parent == root}
    if root_present & {"bulk_plan.json", "bulk_summary.json", "bulk_validation_summary.json"}:
        if "bulk_plan.json" not in root_present:
            errors.append(_missing_error(root, root / "bulk_plan.json", "bulk_plan.json", None))
        if not (root_present & BULK_EXPECTED_ANY_SUMMARY):
            errors.append(
                _missing_error(
                    root,
                    root / "bulk_summary.json",
                    "bulk_summary.json",
                    None,
                    message="expected bulk_summary.json or bulk_validation_summary.json",
                )
            )
    for directory, present in sorted(present_by_dir.items(), key=lambda item: str(item[0])):
        formula = _formula_from_path(directory)
        if present & AUDIT_CONTEXT_ARTIFACTS:
            for artifact in sorted(AUDIT_EXPECTED - present):
                errors.append(_missing_error(root, directory / artifact, artifact, formula))
        if present & PREFERENCE_CONTEXT_ARTIFACTS:
            for artifact in sorted(PREFERENCE_EXPECTED - present):
                errors.append(_missing_error(root, directory / artifact, artifact, formula))
    return errors


def _missing_error(
    root: Path,
    path: Path,
    artifact: str,
    formula: str | None,
    *,
    message: str | None = None,
) -> ArtifactError:
    return ArtifactError(
        root=str(root),
        path=str(path),
        artifact=artifact,
        issue="missing_artifact",
        message=message or "expected artifact is missing",
        formula=formula,
    )


def _root_summary(root: Path, reads: Sequence[ArtifactRead]) -> dict[str, Any]:
    names = Counter(read.artifact for read in reads)
    issues = Counter(error.issue for read in reads for error in read.errors)
    return {
        "root": str(root),
        "exists": root.exists(),
        "artifact_count": len(reads),
        "artifact_name_counts": dict(sorted(names.items())),
        "read_issue_counts": dict(sorted(issues.items())),
    }


def _record_artifact(state: FormulaCollection, read: ArtifactRead) -> None:
    state.roots.add(str(read.root))
    state.artifact_paths.add(str(read.path))


def _formula_state(
    formula_state: dict[str, FormulaCollection],
    formula: str,
) -> FormulaCollection:
    formula_key = str(formula)
    if formula_key not in formula_state:
        formula_state[formula_key] = FormulaCollection(formula=formula_key)
    return formula_state[formula_key]


def _items_from_mapping(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    items = data.get("items", [])
    return [dict(item) for item in items if isinstance(item, dict)]


def _formula_from_row(row: dict[str, Any]) -> str | None:
    condition = row.get("condition")
    if isinstance(condition, dict) and condition.get("formula") not in (None, ""):
        return str(condition["formula"])
    if row.get("formula") not in (None, ""):
        return str(row["formula"])
    if row.get("composition") not in (None, ""):
        return str(row["composition"])
    metadata = row.get("metadata")
    if isinstance(metadata, dict) and metadata.get("formula_condition") not in (None, ""):
        return str(metadata["formula_condition"])
    return None


def _formula_from_path(path: str | Path) -> str | None:
    source = Path(path)
    parts = source.parts
    for marker in ("crystalformer_audit", "dpo_preferences", "crystalformer_smoke_pipeline"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    if source.name in (JSON_ARTIFACTS | JSONL_ARTIFACTS) and source.parent.name not in {"", ".", "outputs"}:
        parent = source.parent.name
        if parent not in {"smoke", "formula_runs", "crystalformer_raw"}:
            return parent
    if source.is_dir() and source.name not in {"smoke", "formula_runs", "crystalformer_raw"}:
        return source.name
    return None


def _candidate_id(row: dict[str, Any]) -> str | None:
    value = row.get("candidate_id", row.get("sample_id"))
    return None if value in (None, "") else str(value)


def _preference_pair_key(row: dict[str, Any]) -> str:
    condition = row.get("condition")
    condition_text = json.dumps(condition if isinstance(condition, dict) else {}, sort_keys=True)
    pair_id = row.get("pair_id")
    if pair_id not in (None, ""):
        return f"{condition_text}|{pair_id}"
    return "|".join(
        [
            condition_text,
            str(row.get("chosen_candidate_id")),
            str(row.get("rejected_candidate_id")),
        ]
    )


def _top_counter(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _safe_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_empty_file(path: Path) -> bool:
    try:
        return path.stat().st_size == 0
    except OSError:
        return False
