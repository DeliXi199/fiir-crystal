"""Bulk CrystalFormer generation orchestration.

This module plans and optionally executes multiple explicit CrystalFormer
generation commands, then routes each formula through the local smoke pipeline.
It never clones, installs, downloads, trains, or calls external APIs.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Any, Sequence

from fiir_crystal.evaluation.error_audit import F3_UNAVAILABLE_MODE
from fiir_crystal.generation.crystalformer_smoke_pipeline import (
    CrystalFormerSmokePipelineConfig,
    run_crystalformer_smoke_pipeline,
)
from fiir_crystal.io import write_json


REQUIRED_COMMAND_TEMPLATE_FIELDS = frozenset({"formula", "raw_output_dir"})


@dataclass(slots=True)
class BulkFormulaConfig:
    """One formula entry in a bulk CrystalFormer generation plan."""

    formula: str
    num_samples: int
    spacegroup: int | None = None
    top_k: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CrystalFormerBulkConfig:
    """Bulk CrystalFormer orchestration config."""

    formulas: tuple[BulkFormulaConfig, ...]
    command_template: str
    crystalformer_work_dir: Path = Path("external/CrystalFormer")
    checkpoint_dir: Path = Path("external/checkpoints")
    output_root: Path = Path("outputs/crystalformer_bulk")
    raw_output_root: Path | None = None
    smoke_output_root: Path | None = None
    parser_backend: str = "none"
    stability_mode: str = F3_UNAVAILABLE_MODE
    source_format: str = "auto"
    default_num_samples: int = 100
    default_top_k: int = 40
    skip_existing: bool = True
    max_candidates: int | None = None
    offline_validation_root: Path | None = None


def load_bulk_config(path: str | Path) -> CrystalFormerBulkConfig:
    """Load a JSON bulk-generation config."""

    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"bulk config must be a JSON object: {source}")
    return bulk_config_from_dict(data)


def bulk_config_from_dict(data: dict[str, Any]) -> CrystalFormerBulkConfig:
    """Normalize a bulk config dictionary."""

    defaults = dict(data.get("defaults", {})) if isinstance(data.get("defaults"), dict) else {}
    formula_rows = data.get("formulas")
    if not isinstance(formula_rows, list) or not formula_rows:
        raise ValueError("bulk config requires a non-empty formulas list")
    default_num_samples = int(defaults.get("num_samples", data.get("default_num_samples", 100)))
    default_top_k = int(defaults.get("top_k", data.get("default_top_k", 40)))
    formulas = tuple(_formula_config(row, default_num_samples, default_top_k) for row in formula_rows)
    command_template = str(data.get("command_template", "")).strip()
    if not command_template:
        raise ValueError("bulk config requires command_template")
    _validate_command_template_required_fields(command_template)
    return CrystalFormerBulkConfig(
        formulas=formulas,
        command_template=command_template,
        crystalformer_work_dir=Path(str(data.get("crystalformer_work_dir", "external/CrystalFormer"))),
        checkpoint_dir=Path(str(data.get("checkpoint_dir", "external/checkpoints"))),
        output_root=Path(str(data.get("output_root", "outputs/crystalformer_bulk"))),
        raw_output_root=(
            None if data.get("raw_output_root") in (None, "") else Path(str(data["raw_output_root"]))
        ),
        smoke_output_root=(
            None if data.get("smoke_output_root") in (None, "") else Path(str(data["smoke_output_root"]))
        ),
        parser_backend=str(data.get("parser_backend", "none")),
        stability_mode=str(data.get("stability_mode", F3_UNAVAILABLE_MODE)),
        source_format=str(data.get("source_format", "auto")),
        default_num_samples=default_num_samples,
        default_top_k=default_top_k,
        skip_existing=bool(data.get("skip_existing", True)),
        max_candidates=_optional_int(data.get("max_candidates")),
        offline_validation_root=(
            None
            if data.get("offline_validation_root") in (None, "")
            else Path(str(data["offline_validation_root"]))
        ),
    )


def validate_bulk_generation_config(
    config: CrystalFormerBulkConfig,
    *,
    only_formula: str | None = None,
    skip_existing: bool | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Validate and expand a bulk config without running generation or smoke."""

    cfg = _with_output_override(config, output_root)
    skip_existing_effective = cfg.skip_existing if skip_existing is None else skip_existing
    plan = build_bulk_plan(cfg, only_formula=only_formula, skip_existing=skip_existing_effective)
    cfg.output_root.mkdir(parents=True, exist_ok=True)

    summary = _bulk_validation_summary(cfg, plan, skip_existing=skip_existing_effective)
    files = {
        "plan": str(cfg.output_root / "bulk_plan.json"),
        "summary": str(cfg.output_root / "bulk_validation_summary.json"),
        "report": str(cfg.output_root / "validate_report.md"),
    }
    write_json(files["plan"], {"items": plan, "validate_only": True, "run_generation": False})
    write_json(files["summary"], summary)
    Path(files["report"]).write_text(_render_validation_report(summary), encoding="utf-8")
    return {"summary": summary, "plan": plan, "files": files}


def run_crystalformer_bulk_generation(
    config: CrystalFormerBulkConfig,
    *,
    run_generation: bool = False,
    only_formula: str | None = None,
    continue_on_error: bool = False,
    skip_existing: bool | None = None,
    output_root: Path | None = None,
    max_concurrent_generations: int | None = None,
    generation_cpu_threads: int | None = None,
    total_cpu_cores: int | None = None,
) -> dict[str, Any]:
    """Run a bulk plan, optionally executing generation commands."""

    cfg = _with_output_override(config, output_root)
    skip_existing_effective = cfg.skip_existing if skip_existing is None else skip_existing
    plan = build_bulk_plan(cfg, only_formula=only_formula, skip_existing=skip_existing_effective)
    parallelism = _resolve_parallelism(
        plan,
        run_generation=run_generation,
        max_concurrent_generations=max_concurrent_generations,
        generation_cpu_threads=generation_cpu_threads,
        total_cpu_cores=total_cpu_cores,
    )
    plan = _annotate_plan_parallelism(plan, parallelism)
    cfg.output_root.mkdir(parents=True, exist_ok=True)
    write_json(
        cfg.output_root / "bulk_plan.json",
        {"items": plan, "run_generation": run_generation, "parallelism": parallelism},
    )

    if run_generation and parallelism["max_concurrent_generations"] > 1:
        rows = _run_plan_items_parallel(
            cfg,
            plan,
            run_generation=run_generation,
            continue_on_error=continue_on_error,
            max_workers=int(parallelism["max_concurrent_generations"]),
        )
    else:
        rows = []
        for item in plan:
            row = _run_plan_item(
                cfg,
                item,
                run_generation=run_generation,
                continue_on_error=continue_on_error,
            )
            rows.append(row)
            if row["status"] == "failed" and not continue_on_error:
                break

    summary = _bulk_summary(cfg, plan, rows, run_generation=run_generation, parallelism=parallelism)
    files = {
        "plan": str(cfg.output_root / "bulk_plan.json"),
        "summary": str(cfg.output_root / "bulk_summary.json"),
        "report": str(cfg.output_root / "report.md"),
    }
    write_json(files["summary"], summary)
    Path(files["report"]).write_text(_render_bulk_report(summary), encoding="utf-8")
    return {"summary": summary, "plan": plan, "rows": rows, "files": files}


def build_bulk_plan(
    config: CrystalFormerBulkConfig,
    *,
    only_formula: str | None = None,
    skip_existing: bool | None = None,
) -> list[dict[str, Any]]:
    """Build per-formula command plan rows."""

    _validate_command_template_required_fields(config.command_template)
    skip_existing_effective = config.skip_existing if skip_existing is None else skip_existing
    rows = []
    raw_root = config.raw_output_root or config.output_root / "crystalformer_raw"
    smoke_root = config.smoke_output_root or config.output_root / "smoke"
    for formula_config in config.formulas:
        if only_formula and formula_config.formula != only_formula:
            continue
        raw_output_dir = raw_root / formula_config.formula
        context = _template_context(config, formula_config, raw_output_dir, smoke_root)
        command = _render_command(config.command_template, context)
        rows.append(
            {
                "formula": formula_config.formula,
                "spacegroup": formula_config.spacegroup,
                "num_samples": formula_config.num_samples,
                "top_k": formula_config.top_k,
                "raw_output_dir": context["raw_output_dir"],
                "smoke_output_root": context["smoke_output_root"],
                "offline_validation_jsonl": _offline_validation_path(config, formula_config),
                "command": command,
                "work_dir": context["crystalformer_work_dir"],
                "skip_existing": skip_existing_effective and _has_existing_raw_output(raw_output_dir),
                "skip_reason": (
                    "existing_raw_output"
                    if skip_existing_effective and _has_existing_raw_output(raw_output_dir)
                    else None
                ),
            }
        )
    if only_formula and not rows:
        raise ValueError(f"only_formula did not match any configured formula: {only_formula}")
    return rows


def _run_plan_item(
    config: CrystalFormerBulkConfig,
    item: dict[str, Any],
    *,
    run_generation: bool,
    continue_on_error: bool,
) -> dict[str, Any]:
    formula = str(item["formula"])
    formula_dir = config.output_root / "formula_runs" / formula
    formula_dir.mkdir(parents=True, exist_ok=True)
    Path(str(item["raw_output_dir"])).mkdir(parents=True, exist_ok=True)
    provenance_path = formula_dir / "generation_provenance.json"
    row: dict[str, Any] = {
        "formula": formula,
        "raw_output_dir": item["raw_output_dir"],
        "provenance": str(provenance_path),
        "status": "planned",
        "generation_returncode": None,
        "smoke_summary": None,
        "error": None,
    }

    generation = _generation_provenance(item, executed=False, reason="run_generation_not_requested")
    if item["skip_existing"]:
        generation = _generation_provenance(item, executed=False, reason=str(item["skip_reason"]))
        row["status"] = "skipped_existing"
    elif run_generation:
        generation = _execute_generation(item)
        row["generation_returncode"] = generation["returncode"]
        if generation["returncode"] != 0:
            row["status"] = "failed"
            row["error"] = f"generation_failed_returncode_{generation['returncode']}"
            write_json(provenance_path, generation)
            if continue_on_error:
                return row
            return row
    write_json(provenance_path, generation)

    if not run_generation and not item["skip_existing"]:
        return row

    try:
        smoke_result = run_crystalformer_smoke_pipeline(
            CrystalFormerSmokePipelineConfig(
                input_dir=Path(str(item["raw_output_dir"])),
                formula=formula,
                output_root=Path(str(item["smoke_output_root"])),
                parser_backend=config.parser_backend,
                stability_mode=config.stability_mode,
                spacegroup=item.get("spacegroup"),
                source_format=config.source_format,
                max_candidates=config.max_candidates,
                offline_validation_jsonl=(
                    None
                    if item.get("offline_validation_jsonl") in (None, "")
                    else Path(str(item["offline_validation_jsonl"]))
                ),
            )
        )
        row["smoke_summary"] = smoke_result["summary"]
        row["status"] = "succeeded" if run_generation else "smoke_from_existing"
    except Exception as exc:
        row["status"] = "failed"
        row["error"] = f"{exc.__class__.__name__}: {exc}"
    return row


def _run_plan_items_parallel(
    config: CrystalFormerBulkConfig,
    plan: Sequence[dict[str, Any]],
    *,
    run_generation: bool,
    continue_on_error: bool,
    max_workers: int,
) -> list[dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    next_index = 0
    stop_scheduling = False
    in_flight: dict[Future[dict[str, Any]], tuple[int, dict[str, Any]]] = {}

    def submit_next(executor: ThreadPoolExecutor) -> None:
        nonlocal next_index
        item = plan[next_index]
        future = executor.submit(
            _run_plan_item,
            config,
            item,
            run_generation=run_generation,
            continue_on_error=continue_on_error,
        )
        in_flight[future] = (next_index, item)
        next_index += 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while next_index < len(plan) and len(in_flight) < max_workers:
            submit_next(executor)
        while in_flight:
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                index, item = in_flight.pop(future)
                try:
                    row = future.result()
                except Exception as exc:
                    row = _exception_row(item, exc)
                results[index] = row
                if row["status"] == "failed" and not continue_on_error:
                    stop_scheduling = True
            while not stop_scheduling and next_index < len(plan) and len(in_flight) < max_workers:
                submit_next(executor)

    return [results[index] for index in sorted(results)]


def _exception_row(item: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "formula": item["formula"],
        "raw_output_dir": item["raw_output_dir"],
        "provenance": None,
        "status": "failed",
        "generation_returncode": None,
        "smoke_summary": None,
        "error": f"{exc.__class__.__name__}: {exc}",
    }


def _bulk_summary(
    config: CrystalFormerBulkConfig,
    plan: Sequence[dict[str, Any]],
    rows: Sequence[dict[str, Any]],
    *,
    run_generation: bool,
    parallelism: dict[str, Any],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    total_candidates = 0
    total_dpo_eligible = 0
    total_pairs = 0
    parse_status_counts: dict[str, int] = {}
    f3_status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        smoke = row.get("smoke_summary") or {}
        total_candidates += int(smoke.get("candidate_count", 0))
        total_dpo_eligible += int(smoke.get("dpo_eligible_count", 0))
        total_pairs += int(smoke.get("preference_pair_count", 0))
        _merge_counts(parse_status_counts, smoke.get("parse_status_counts", {}))
        _merge_counts(f3_status_counts, smoke.get("f3_status_counts", {}))
    return {
        "bulk_generation": "crystalformer_existing_checkpoint_orchestration",
        "train_dpo": False,
        "run_generation": run_generation,
        "parallelism": parallelism,
        "formula_count": len(plan),
        "completed_formula_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "total_candidates": total_candidates,
        "total_dpo_eligible": total_dpo_eligible,
        "total_preference_pairs": total_pairs,
        "parse_status_counts": dict(sorted(parse_status_counts.items())),
        "f3_status_counts": dict(sorted(f3_status_counts.items())),
        "output_root": str(config.output_root),
        "raw_output_root": str(config.raw_output_root or config.output_root / "crystalformer_raw"),
        "smoke_output_root": str(config.smoke_output_root or config.output_root / "smoke"),
        "items": [dict(row) for row in rows],
    }


def _bulk_validation_summary(
    config: CrystalFormerBulkConfig,
    plan: Sequence[dict[str, Any]],
    *,
    skip_existing: bool,
) -> dict[str, Any]:
    fields = set(_template_fields(config.command_template))
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    work_dir_exists = config.crystalformer_work_dir.exists()
    checkpoint_dir_exists = config.checkpoint_dir.exists()
    checkpoint_referenced = "checkpoint_dir" in fields
    checkpoint_files = _checkpoint_files(config.checkpoint_dir)
    if not work_dir_exists:
        blocking_reasons.append(f"crystalformer_work_dir_missing:{config.crystalformer_work_dir}")
    if checkpoint_referenced and not checkpoint_dir_exists:
        blocking_reasons.append(f"checkpoint_dir_missing:{config.checkpoint_dir}")
    elif checkpoint_referenced and not checkpoint_files:
        blocking_reasons.append(f"checkpoint_file_missing:{config.checkpoint_dir}")
    elif not checkpoint_dir_exists:
        warnings.append(f"checkpoint_dir_missing_but_not_referenced:{config.checkpoint_dir}")
    if not plan:
        blocking_reasons.append("no_formula_selected")

    per_formula = []
    for item in plan:
        raw_output_dir = Path(str(item["raw_output_dir"]))
        per_formula.append(
            {
                "formula": item["formula"],
                "spacegroup": item["spacegroup"],
                "num_samples": item["num_samples"],
                "top_k": item["top_k"],
                "raw_output_dir": str(raw_output_dir),
                "raw_output_parent_exists": raw_output_dir.parent.exists(),
                "skip_existing": item["skip_existing"],
                "skip_reason": item["skip_reason"],
                "command": item["command"],
            }
        )

    total_num_samples = sum(int(item["num_samples"]) for item in plan)
    return {
        "bulk_generation": "crystalformer_existing_checkpoint_orchestration",
        "train_dpo": False,
        "validate_only": True,
        "run_generation": False,
        "ready_for_generation": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "formula_count": len(plan),
        "total_num_samples": total_num_samples,
        "skip_existing": skip_existing,
        "command_template_fields": sorted(fields),
        "required_command_template_fields": sorted(REQUIRED_COMMAND_TEMPLATE_FIELDS),
        "output_root": str(config.output_root),
        "raw_output_root": str(config.raw_output_root or config.output_root / "crystalformer_raw"),
        "smoke_output_root": str(config.smoke_output_root or config.output_root / "smoke"),
        "workspace": {
            "crystalformer_work_dir": str(config.crystalformer_work_dir),
            "crystalformer_work_dir_exists": work_dir_exists,
            "checkpoint_dir": str(config.checkpoint_dir),
            "checkpoint_dir_exists": checkpoint_dir_exists,
            "checkpoint_dir_referenced_by_template": checkpoint_referenced,
            "checkpoint_file_count": len(checkpoint_files),
            "checkpoint_files": checkpoint_files,
        },
        "items": per_formula,
    }


def _render_validation_report(summary: dict[str, Any]) -> str:
    lines = [
        "# CrystalFormer Bulk Validation Report",
        "",
        "## Boundary",
        "- This is validate-only: no generation command, smoke pipeline, training, download, or install is run.",
        "- `ready_for_generation` is false whenever required local paths are missing.",
        "",
        "## Summary",
        f"- ready_for_generation: {summary['ready_for_generation']}",
        f"- formula_count: {summary['formula_count']}",
        f"- total_num_samples: {summary['total_num_samples']}",
        f"- blocking_reasons: {summary['blocking_reasons']}",
        f"- warnings: {summary['warnings']}",
        f"- command_template_fields: {summary['command_template_fields']}",
        "",
        "## Planned Formulas",
    ]
    for item in summary["items"]:
        lines.append(
            "- "
            f"{item['formula']}: num_samples={item['num_samples']}, "
            f"spacegroup={item['spacegroup']}, raw_output_dir={item['raw_output_dir']}"
        )
    lines.append("")
    return "\n".join(lines)


def _render_bulk_report(summary: dict[str, Any]) -> str:
    lines = [
        "# CrystalFormer Bulk Generation Report",
        "",
        "## Boundary",
        "- This orchestrates existing-checkpoint generation commands only.",
        "- It is not DPO training and does not download checkpoints, datasets, or dependencies.",
        "- Commands run only when `--run-generation` is supplied.",
        "",
        "## Summary",
        f"- parallelism: {summary['parallelism']}",
        f"- formula_count: {summary['formula_count']}",
        f"- completed_formula_count: {summary['completed_formula_count']}",
        f"- status_counts: {summary['status_counts']}",
        f"- total_candidates: {summary['total_candidates']}",
        f"- total_dpo_eligible: {summary['total_dpo_eligible']}",
        f"- total_preference_pairs: {summary['total_preference_pairs']}",
        f"- parse_status_counts: {summary['parse_status_counts']}",
        f"- f3_status_counts: {summary['f3_status_counts']}",
        "",
    ]
    return "\n".join(lines)


def _resolve_parallelism(
    plan: Sequence[dict[str, Any]],
    *,
    run_generation: bool,
    max_concurrent_generations: int | None,
    generation_cpu_threads: int | None,
    total_cpu_cores: int | None,
) -> dict[str, Any]:
    plan_count = len(plan)
    if not run_generation or plan_count == 0:
        return {
            "max_concurrent_generations": 1,
            "generation_cpu_threads": None,
            "total_cpu_cores": total_cpu_cores,
            "thread_allocations": [],
            "parallel_core_budget": 0,
        }

    requested_workers = _positive_int_or_none(max_concurrent_generations)
    total_cores = _positive_int_or_none(total_cpu_cores)
    fixed_threads = _positive_int_or_none(generation_cpu_threads)
    if requested_workers is None:
        requested_workers = plan_count if total_cores is not None else 1
    workers = max(1, min(plan_count, requested_workers))

    if fixed_threads is not None:
        allocations = [fixed_threads for _ in range(workers)]
    elif total_cores is not None:
        base = max(1, total_cores // workers)
        remainder = max(0, total_cores - base * workers)
        allocations = [base + (1 if index < remainder else 0) for index in range(workers)]
    else:
        allocations = [1 for _ in range(workers)]

    return {
        "max_concurrent_generations": workers,
        "generation_cpu_threads": fixed_threads,
        "total_cpu_cores": total_cores,
        "thread_allocations": allocations,
        "parallel_core_budget": sum(allocations),
    }


def _annotate_plan_parallelism(
    plan: Sequence[dict[str, Any]],
    parallelism: dict[str, Any],
) -> list[dict[str, Any]]:
    allocations = list(parallelism.get("thread_allocations") or [])
    if not allocations:
        return [dict(item) for item in plan]
    rows = []
    for index, item in enumerate(plan):
        slot = index % len(allocations)
        row = dict(item)
        row["generation_slot"] = slot
        row["generation_cpu_threads"] = allocations[slot]
        rows.append(row)
    return rows


def _formula_config(row: Any, default_num_samples: int, default_top_k: int) -> BulkFormulaConfig:
    if isinstance(row, str):
        if default_num_samples <= 0:
            raise ValueError("num_samples must be positive")
        return BulkFormulaConfig(formula=row, num_samples=default_num_samples, top_k=default_top_k)
    if not isinstance(row, dict) or not row.get("formula"):
        raise ValueError("each formula entry must be a string or object with formula")
    num_samples = int(row.get("num_samples", default_num_samples))
    if num_samples <= 0:
        raise ValueError(f"num_samples must be positive for formula {row['formula']}")
    extra = {str(key): value for key, value in row.items() if key not in {"formula", "num_samples", "spacegroup", "top_k"}}
    return BulkFormulaConfig(
        formula=str(row["formula"]),
        num_samples=num_samples,
        spacegroup=_optional_int(row.get("spacegroup")),
        top_k=_optional_int(row.get("top_k", default_top_k)),
        extra=extra,
    )


def _template_context(
    config: CrystalFormerBulkConfig,
    formula: BulkFormulaConfig,
    raw_output_dir: Path,
    smoke_output_root: Path,
) -> dict[str, Any]:
    context = {
        "formula": formula.formula,
        "spacegroup": "" if formula.spacegroup is None else formula.spacegroup,
        "num_samples": formula.num_samples,
        "top_k": config.default_top_k if formula.top_k is None else formula.top_k,
        "checkpoint_dir": _absolute_path(config.checkpoint_dir),
        "crystalformer_work_dir": _absolute_path(config.crystalformer_work_dir),
        "raw_output_dir": _absolute_path(raw_output_dir),
        "smoke_output_root": _absolute_path(smoke_output_root),
        "output_root": _absolute_path(config.output_root),
    }
    context.update(formula.extra)
    return context


def _render_command(template: str, context: dict[str, Any]) -> str:
    required = _template_fields(template)
    missing = [field for field in required if field not in context]
    if missing:
        raise ValueError(f"command_template contains unknown fields: {missing}")
    return template.format(**context)


def _validate_command_template_required_fields(template: str) -> None:
    fields = set(_template_fields(template))
    missing = sorted(REQUIRED_COMMAND_TEMPLATE_FIELDS - fields)
    if missing:
        raise ValueError(f"command_template must contain required fields: {missing}")


def _template_fields(template: str) -> list[str]:
    fields = []
    for _, field_name, _, _ in Formatter().parse(template):
        if not field_name:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        if root not in fields:
            fields.append(root)
    return fields


def _execute_generation(item: dict[str, Any]) -> dict[str, Any]:
    work_dir = Path(str(item["work_dir"]))
    if not work_dir.exists():
        return _generation_provenance(
            item,
            executed=False,
            reason=f"work_dir_missing:{work_dir}",
            returncode=127,
        )
    args = shlex.split(str(item["command"]))
    env_overrides = _generation_env_overrides(item)
    env = os.environ.copy()
    env.update(env_overrides)
    completed = subprocess.run(
        args,
        cwd=str(work_dir),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return _generation_provenance(
        item,
        executed=True,
        reason=None,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        args=args,
        env_overrides=env_overrides,
    )


def _generation_provenance(
    item: dict[str, Any],
    *,
    executed: bool,
    reason: str | None,
    returncode: int | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    args: list[str] | None = None,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "formula": item["formula"],
        "executed": executed,
        "reason": reason,
        "command": item["command"],
        "args": args,
        "cwd": item["work_dir"],
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "raw_output_dir": item["raw_output_dir"],
        "env_overrides": env_overrides or {},
        "generation_slot": item.get("generation_slot"),
        "generation_cpu_threads": item.get("generation_cpu_threads"),
    }


def _offline_validation_path(config: CrystalFormerBulkConfig, formula: BulkFormulaConfig) -> str | None:
    if config.offline_validation_root is None:
        return None
    path = config.offline_validation_root / f"{formula.formula}_validation.jsonl"
    return str(path) if path.exists() else None


def _has_existing_raw_output(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return path.stat().st_size > 0
    return any(child.is_file() for child in path.iterdir())


def _checkpoint_files(path: Path) -> list[str]:
    if path.is_file():
        return [str(path)]
    if path.is_dir():
        return [str(candidate) for candidate in sorted(path.glob("*.pkl"))]
    return []


def _generation_env_overrides(item: dict[str, Any]) -> dict[str, str]:
    threads = _positive_int_or_none(item.get("generation_cpu_threads"))
    if threads is None:
        return {}
    overrides = {
        "OMP_NUM_THREADS": str(threads),
        "MKL_NUM_THREADS": str(threads),
        "OPENBLAS_NUM_THREADS": str(threads),
        "NUMEXPR_NUM_THREADS": str(threads),
    }
    xla_flags = os.environ.get("XLA_FLAGS", "").strip()
    cpu_flags = f"--xla_cpu_multi_thread_eigen=true intra_op_parallelism_threads={threads}"
    overrides["XLA_FLAGS"] = f"{xla_flags} {cpu_flags}".strip()
    return overrides


def _with_output_override(
    config: CrystalFormerBulkConfig,
    output_root: Path | None,
) -> CrystalFormerBulkConfig:
    if output_root is None:
        return config
    return CrystalFormerBulkConfig(
        formulas=config.formulas,
        command_template=config.command_template,
        crystalformer_work_dir=config.crystalformer_work_dir,
        checkpoint_dir=config.checkpoint_dir,
        output_root=output_root,
        raw_output_root=None,
        smoke_output_root=None,
        parser_backend=config.parser_backend,
        stability_mode=config.stability_mode,
        source_format=config.source_format,
        default_num_samples=config.default_num_samples,
        default_top_k=config.default_top_k,
        skip_existing=config.skip_existing,
        max_candidates=config.max_candidates,
        offline_validation_root=config.offline_validation_root,
    )


def _absolute_path(path: Path) -> str:
    return str(path if path.is_absolute() else path.resolve())


def _merge_counts(target: dict[str, int], incoming: Any) -> None:
    if not isinstance(incoming, dict):
        return
    for key, value in incoming.items():
        target[str(key)] = target.get(str(key), 0) + int(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return int(float(str(value)))


def _positive_int_or_none(value: Any) -> int | None:
    if value in (None, "", "0", 0, "auto", "AUTO", "none", "None", "null"):
        return None
    number = int(float(str(value)))
    if number <= 0:
        return None
    return number
