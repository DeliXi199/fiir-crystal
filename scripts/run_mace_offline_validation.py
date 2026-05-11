#!/usr/bin/env python
"""Run local-only MACE inference on existing FIIR candidate records.

This script lives outside the stdlib-only ``fiir_crystal`` core dependency
boundary. It imports MACE/ASE only at execution time, reads existing local
candidate JSONL files, and writes local validation evidence. It never calls
DFT, training, external APIs, or generation. To avoid implicit downloads, a
local MACE model file must be supplied or already present in the local cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import read_jsonl, write_json, write_jsonl


DEFAULT_OUTPUT_DIR = Path("outputs/mlip_validation_mace")
DEFAULT_VALIDATOR = "mace_mpa_0_medium"
DEFAULT_SOURCE = "local_mlip_mace_single_point"
DEFAULT_CACHE_MODEL = Path.home() / ".cache" / "mace" / "macempa0mediummodel"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local MACE inference over existing CrystalFormer candidate JSONL files."
    )
    parser.add_argument("--candidates-jsonl", required=True)
    parser.add_argument("--output-jsonl", default=str(DEFAULT_OUTPUT_DIR / "mace_validation_results.jsonl"))
    parser.add_argument("--output-summary", default=str(DEFAULT_OUTPUT_DIR / "mace_validation_summary.json"))
    parser.add_argument("--report", default=str(DEFAULT_OUTPUT_DIR / "report.md"))
    parser.add_argument("--model-path", default=os.environ.get("FIIR_MACE_MODEL_PATH"))
    parser.add_argument("--model-name", default=DEFAULT_VALIDATOR)
    parser.add_argument("--validation-source", default=DEFAULT_SOURCE)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--default-dtype", choices=("float32", "float64"), default="float32")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpu-devices", default=os.environ.get("CUDA_VISIBLE_DEVICES", ""))
    parser.add_argument("--relax", action="store_true")
    parser.add_argument("--relax-steps", type=int, default=100)
    parser.add_argument("--fmax", type=float, default=0.05)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.shard_count < 1:
        raise SystemExit("--shard-count must be positive")
    if args.shard_index is not None and not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("--shard-index must be in [0, shard_count)")
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    if args.workers > 1 and args.shard_index is None:
        return _run_worker_pool(args)
    return _run_single(args)


def _run_single(args: argparse.Namespace) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    start_time = time.monotonic()
    candidates_path = Path(args.candidates_jsonl)
    output_jsonl = Path(args.output_jsonl)
    output_summary = Path(args.output_summary)
    report = Path(args.report)
    model_path = _resolve_model_path(args.model_path)
    rows = _select_rows(read_jsonl(candidates_path), args.limit, args.shard_index, args.shard_count)

    if args.dry_run:
        results = [_planned_row(row, args, candidates_path, model_path) for row in rows]
    else:
        calc, actual_device, package_versions = _load_mace_calculator(
            model_path=model_path,
            device=args.device,
            default_dtype=args.default_dtype,
        )
        results = [
            _evaluate_row(
                row,
                args=args,
                candidates_path=candidates_path,
                model_path=model_path,
                calc=calc,
                actual_device=actual_device,
                package_versions=package_versions,
            )
            for row in rows
        ]

    results = sorted(results, key=lambda row: (str(row.get("formula")), str(row.get("candidate_id"))))
    summary = _summary(
        args=args,
        candidates_path=candidates_path,
        model_path=model_path,
        rows=results,
        started=started,
        elapsed_seconds=time.monotonic() - start_time,
    )
    _write_outputs(output_jsonl, output_summary, report, results, summary)
    _print_summary(summary, output_jsonl, output_summary, report)
    if args.strict and summary["failed_count"]:
        raise SystemExit("strict MACE validation found failed rows")
    return {"summary": summary, "rows": results}


def _run_worker_pool(args: argparse.Namespace) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    start_time = time.monotonic()
    output_jsonl = Path(args.output_jsonl)
    output_summary = Path(args.output_summary)
    report = Path(args.report)
    shard_dir = output_jsonl.parent / "mace_worker_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    devices = _gpu_devices(args.gpu_devices)
    env_base = os.environ.copy()
    processes: list[tuple[int, subprocess.Popen[str], Path, Path]] = []
    for index in range(args.workers):
        shard_jsonl = shard_dir / f"shard_{index:03d}.jsonl"
        shard_summary = shard_dir / f"shard_{index:03d}_summary.json"
        shard_report = shard_dir / f"shard_{index:03d}_report.md"
        env = dict(env_base)
        if args.device != "cpu" and devices:
            env["CUDA_VISIBLE_DEVICES"] = devices[index % len(devices)]
        command = _child_command(args, index, shard_jsonl, shard_summary, shard_report)
        processes.append(
            (
                index,
                subprocess.Popen(command, cwd=PROJECT_ROOT, env=env, text=True),
                shard_jsonl,
                shard_summary,
            )
        )

    failures: list[dict[str, Any]] = []
    for index, process, shard_jsonl, shard_summary in processes:
        returncode = process.wait()
        if returncode != 0:
            failures.append(
                {
                    "worker_index": index,
                    "returncode": returncode,
                    "output_jsonl": str(shard_jsonl),
                    "summary": str(shard_summary),
                }
            )

    rows: list[dict[str, Any]] = []
    child_summaries: list[dict[str, Any]] = []
    for _, _, shard_jsonl, shard_summary in processes:
        if shard_jsonl.exists():
            rows.extend(read_jsonl(shard_jsonl))
        if shard_summary.exists():
            child_summaries.append(json.loads(shard_summary.read_text(encoding="utf-8")))

    rows = sorted(rows, key=lambda row: (str(row.get("formula")), str(row.get("candidate_id"))))
    summary = _summary(
        args=args,
        candidates_path=Path(args.candidates_jsonl),
        model_path=_resolve_model_path(args.model_path),
        rows=rows,
        started=started,
        elapsed_seconds=time.monotonic() - start_time,
    )
    summary["worker_count"] = args.workers
    summary["worker_failures"] = failures
    summary["worker_summaries"] = child_summaries
    _write_outputs(output_jsonl, output_summary, report, rows, summary)
    _print_summary(summary, output_jsonl, output_summary, report)
    if failures or (args.strict and summary["failed_count"]):
        raise SystemExit("MACE worker pool failed" if failures else "strict MACE validation found failed rows")
    return {"summary": summary, "rows": rows}


def _child_command(
    args: argparse.Namespace,
    index: int,
    output_jsonl: Path,
    output_summary: Path,
    report: Path,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--candidates-jsonl",
        args.candidates_jsonl,
        "--output-jsonl",
        str(output_jsonl),
        "--output-summary",
        str(output_summary),
        "--report",
        str(report),
        "--model-path",
        str(_resolve_model_path(args.model_path)),
        "--model-name",
        args.model_name,
        "--validation-source",
        args.validation_source,
        "--device",
        args.device,
        "--default-dtype",
        args.default_dtype,
        "--shard-index",
        str(index),
        "--shard-count",
        str(args.workers),
        "--workers",
        "1",
    ]
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.relax:
        command.append("--relax")
        command.extend(["--relax-steps", str(args.relax_steps), "--fmax", str(args.fmax)])
    if args.strict:
        command.append("--strict")
    if args.dry_run:
        command.append("--dry-run")
    return command


def _load_mace_calculator(*, model_path: Path, device: str, default_dtype: str) -> tuple[Any, str, dict[str, str]]:
    try:
        import ase  # type: ignore[import-not-found]
        import mace  # type: ignore[import-not-found]
        import torch  # type: ignore[import-not-found]
        from mace.calculators import mace_mp  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise SystemExit(f"MACE runtime dependencies are unavailable: {exc}") from exc

    actual_device = device
    if actual_device == "auto":
        actual_device = "cuda" if torch.cuda.is_available() else "cpu"
    calc = mace_mp(model=str(model_path), device=actual_device, default_dtype=default_dtype)
    versions = {
        "ase": str(getattr(ase, "__version__", "unknown")),
        "mace": str(getattr(mace, "__version__", "unknown")),
        "torch": str(getattr(torch, "__version__", "unknown")),
    }
    return calc, actual_device, versions


def _evaluate_row(
    row: dict[str, Any],
    *,
    args: argparse.Namespace,
    candidates_path: Path,
    model_path: Path,
    calc: Any,
    actual_device: str,
    package_versions: dict[str, str],
) -> dict[str, Any]:
    started = time.monotonic()
    base = _base_validation_row(row, args, candidates_path, model_path)
    try:
        atoms = _atoms_from_candidate(row)
        atoms.calc = calc
        if args.relax:
            converged = _relax_atoms(atoms, args.fmax, args.relax_steps)
            base["relaxed"] = True
            base["relaxation_converged"] = bool(converged)
        energy = float(atoms.get_potential_energy())
        forces = atoms.get_forces()
        force_max = _max_vector_norm(forces)
        stress_max = _stress_max(atoms)
        base.update(
            {
                "validation_status": "completed",
                "force_max": force_max,
                "stress_max": stress_max,
                "relaxed": bool(base["relaxed"]),
                "relaxation_converged": base["relaxation_converged"],
            }
        )
        base["metadata"].update(
            {
                "mace_total_energy_eV": energy,
                "mace_total_energy_eV_per_atom": energy / max(1, len(atoms)),
                "num_atoms": len(atoms),
                "device": actual_device,
                "package_versions": package_versions,
                "elapsed_seconds": round(time.monotonic() - started, 6),
            }
        )
    except Exception as exc:
        base.update(
            {
                "validation_status": "failed",
                "error_reason": f"{exc.__class__.__name__}: {exc}",
                "relaxed": False,
                "relaxation_converged": False,
            }
        )
        base["metadata"].update(
            {
                "device": actual_device,
                "package_versions": package_versions,
                "elapsed_seconds": round(time.monotonic() - started, 6),
            }
        )
    return base


def _planned_row(
    row: dict[str, Any],
    args: argparse.Namespace,
    candidates_path: Path,
    model_path: Path,
) -> dict[str, Any]:
    base = _base_validation_row(row, args, candidates_path, model_path)
    base["validation_status"] = "planned_not_executed"
    base["metadata"]["dry_run"] = True
    return base


def _base_validation_row(
    row: dict[str, Any],
    args: argparse.Namespace,
    candidates_path: Path,
    model_path: Path,
) -> dict[str, Any]:
    candidate_id = _candidate_id(row)
    formula = _formula(row)
    condition = _condition(row, formula)
    generation = _generation_condition(row, condition)
    spacegroup = _spacegroup(row, condition)
    return {
        "candidate_id": candidate_id,
        "formula": formula,
        "validation_status": "unknown",
        "validator": args.model_name,
        "validation_source": args.validation_source,
        "calibration_tier": "tier3_single_mlip",
        "energy_above_hull": None,
        "formation_energy": None,
        "relaxed": False,
        "relaxation_converged": None,
        "force_max": None,
        "stress_max": None,
        "uncertainty": None,
        "spacegroup": spacegroup,
        "source_checkpoint": _string_or_none(generation.get("source_checkpoint")),
        "generation_condition": generation,
        "top_k": _string_or_none(generation.get("top_k")),
        "K": _string_or_none(generation.get("K")),
        "temperature": _string_or_none(generation.get("temperature")),
        "condition": {
            "mode": condition.get("mode", "csp"),
            "formula": formula,
            "spacegroup": spacegroup,
            "generation": generation,
        },
        "is_stable": None,
        "relaxed_structure_ref": None,
        "error_reason": None,
        "metadata": {
            "script": "scripts/run_mace_offline_validation.py",
            "local_only": True,
            "runs_mlip": not args.dry_run,
            "runs_dft": False,
            "runs_training": False,
            "runs_generation": False,
            "calls_external_apis": False,
            "downloads": False,
            "candidate_source_path": str(candidates_path),
            "mace_model_path": str(model_path),
            "mace_model_sha256": _sha256(model_path),
            "mace_model_name": args.model_name,
            "relax_requested": bool(args.relax),
            "energy_above_hull_status": "unavailable_without_local_hull_reference",
        },
    }


def _atoms_from_candidate(row: dict[str, Any]) -> Any:
    try:
        from ase import Atoms  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise RuntimeError(f"ASE is unavailable: {exc}") from exc

    species = [str(item) for item in row.get("species", []) if str(item)]
    coords = row.get("frac_coords", [])
    lattice = row.get("lattice_matrix", [])
    if not species or not coords or not lattice:
        species, coords, lattice = _structure_from_raw_sequence(row)
    if not species or not coords or not lattice:
        raise ValueError("candidate does not contain species, fractional coordinates, and lattice")
    if len(species) != len(coords):
        raise ValueError(f"species/coordinate length mismatch: {len(species)} != {len(coords)}")
    return Atoms(symbols=species, scaled_positions=coords, cell=lattice, pbc=True)


def _structure_from_raw_sequence(row: dict[str, Any]) -> tuple[list[str], list[list[float]], list[list[float]]]:
    from ase.data import chemical_symbols  # type: ignore[import-not-found]

    fields = _raw_sequence_fields(row)
    atomic_numbers = _literal(fields.get("A")) or []
    coords = _literal(fields.get("X")) or []
    lattice_params = _literal(fields.get("L")) or []
    species: list[str] = []
    frac_coords: list[list[float]] = []
    for index, value in enumerate(atomic_numbers):
        number = int(float(value))
        if number <= 0:
            continue
        species.append(chemical_symbols[number])
        frac_coords.append([float(item) for item in coords[index]])
    if len(lattice_params) == 6:
        lattice = _lattice_matrix_from_parameters([float(item) for item in lattice_params])
    else:
        lattice = [[float(item) for item in row] for row in lattice_params]
    return species, frac_coords, lattice


def _relax_atoms(atoms: Any, fmax: float, steps: int) -> bool:
    from ase.optimize import FIRE  # type: ignore[import-not-found]

    optimizer = FIRE(atoms, logfile=None)
    return bool(optimizer.run(fmax=fmax, steps=steps))


def _stress_max(atoms: Any) -> float | None:
    try:
        stress = atoms.get_stress(voigt=True)
    except Exception:
        return None
    try:
        return max(abs(float(value)) for value in stress)
    except Exception:
        return None


def _max_vector_norm(vectors: Any) -> float | None:
    values = []
    for vector in vectors:
        values.append(math.sqrt(sum(float(component) ** 2 for component in vector)))
    return None if not values else max(values)


def _select_rows(
    rows: list[dict[str, Any]],
    limit: int | None,
    shard_index: int | None,
    shard_count: int,
) -> list[dict[str, Any]]:
    selected = rows[:limit] if limit is not None else rows
    if shard_index is None:
        return selected
    return [row for index, row in enumerate(selected) if index % shard_count == shard_index]


def _summary(
    *,
    args: argparse.Namespace,
    candidates_path: Path,
    model_path: Path,
    rows: list[dict[str, Any]],
    started: datetime,
    elapsed_seconds: float,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    formula_counts: dict[str, int] = {}
    for row in rows:
        status_counts[str(row.get("validation_status"))] = status_counts.get(str(row.get("validation_status")), 0) + 1
        formula_counts[str(row.get("formula"))] = formula_counts.get(str(row.get("formula")), 0) + 1
    return {
        "workflow": "mace_offline_validation",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": not args.dry_run,
        "calls_external_apis": False,
        "downloads": False,
        "dry_run": bool(args.dry_run),
        "candidates_jsonl": str(candidates_path),
        "output_jsonl": str(args.output_jsonl),
        "model_path": str(model_path),
        "model_sha256": _sha256(model_path),
        "model_name": args.model_name,
        "device": args.device,
        "default_dtype": args.default_dtype,
        "limit": args.limit,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "worker_count": args.workers,
        "relax": bool(args.relax),
        "relax_steps": args.relax_steps,
        "fmax": args.fmax,
        "row_count": len(rows),
        "completed_count": sum(str(row.get("validation_status")) == "completed" for row in rows),
        "failed_count": sum(str(row.get("validation_status")) == "failed" for row in rows),
        "f3_available_candidate_count": 0,
        "status_counts": dict(sorted(status_counts.items())),
        "formula_counts": dict(sorted(formula_counts.items())),
        "start_time_utc": started.isoformat(),
        "end_time_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "notes": [
            "MACE energy/force inference is local MLIP evidence.",
            "energy_above_hull remains null because no local hull/reference phase calculation was provided.",
            "No stable F3 label is emitted by this workflow.",
        ],
    }


def _write_outputs(
    output_jsonl: Path,
    output_summary: Path,
    report: Path,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    write_jsonl(output_jsonl, rows)
    write_json(output_summary, summary)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_render_report(summary), encoding="utf-8")


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# MACE Offline Validation Report",
        "",
        "## Boundary",
        "- Reads existing candidate JSONL files only.",
        "- Runs local MACE inference only when dry_run is false.",
        "- Does not run generation, training, DFT, external APIs, or downloads.",
        "- Does not report stable F3 labels without local E_above_hull evidence.",
        "",
        "## Summary",
        f"- row_count: {summary['row_count']}",
        f"- completed_count: {summary['completed_count']}",
        f"- failed_count: {summary['failed_count']}",
        f"- status_counts: {summary['status_counts']}",
        f"- formula_counts: {summary['formula_counts']}",
        f"- f3_available_candidate_count: {summary['f3_available_candidate_count']}",
        f"- device: {summary['device']}",
        f"- worker_count: {summary['worker_count']}",
        f"- model_name: {summary['model_name']}",
        f"- output_jsonl: `{summary['output_jsonl']}`",
        "",
        "## Notes",
    ]
    lines.extend(f"- {note}" for note in summary["notes"])
    lines.append("")
    return "\n".join(lines)


def _print_summary(summary: dict[str, Any], output_jsonl: Path, output_summary: Path, report: Path) -> None:
    print("MACE offline validation complete")
    print(f"  row_count: {summary['row_count']}")
    print(f"  completed_count: {summary['completed_count']}")
    print(f"  failed_count: {summary['failed_count']}")
    print(f"  f3_available_candidate_count: {summary['f3_available_candidate_count']}")
    print(f"  output_jsonl: {output_jsonl}")
    print(f"  summary: {output_summary}")
    print(f"  report: {report}")


def _resolve_model_path(value: str | None) -> Path:
    candidates = [Path(value).expanduser()] if value else []
    candidates.append(DEFAULT_CACHE_MODEL)
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    checked = ", ".join(str(path) for path in candidates)
    raise SystemExit(
        "No local MACE model file found. Set --model-path or FIIR_MACE_MODEL_PATH. "
        f"Checked: {checked}"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_id(row: dict[str, Any]) -> str:
    value = row.get("candidate_id", row.get("sample_id", row.get("id")))
    if value in (None, ""):
        raise ValueError("candidate row is missing candidate_id")
    return str(value)


def _formula(row: dict[str, Any]) -> str:
    condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
    value = row.get("formula", row.get("composition", condition.get("formula")))
    if value in (None, ""):
        raise ValueError(f"candidate {row.get('candidate_id')} is missing formula/composition")
    return str(value)


def _condition(row: dict[str, Any], formula: str) -> dict[str, Any]:
    condition = dict(row.get("condition", {})) if isinstance(row.get("condition"), dict) else {}
    condition.setdefault("formula", formula)
    condition.setdefault("mode", "csp")
    if "generation" not in condition or not isinstance(condition.get("generation"), dict):
        condition["generation"] = {}
    return condition


def _generation_condition(row: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    generation = dict(condition.get("generation", {})) if isinstance(condition.get("generation"), dict) else {}
    for key in ("source_checkpoint", "source_model", "temperature", "top_k", "K"):
        value = row.get(key, metadata.get(key))
        if value not in (None, ""):
            generation[key] = value
    return {str(key): value for key, value in sorted(generation.items()) if value not in (None, "")}


def _spacegroup(row: dict[str, Any], condition: dict[str, Any]) -> int | None:
    for value in (
        row.get("space_group"),
        row.get("spacegroup"),
        condition.get("spacegroup"),
        condition.get("space_group"),
    ):
        if value not in (None, ""):
            return int(float(str(value)))
    return None


def _raw_sequence_fields(row: dict[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("raw_sequence_fields"), dict):
        return dict(row["raw_sequence_fields"])
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if isinstance(metadata.get("raw_sequence_fields"), dict):
        return dict(metadata["raw_sequence_fields"])
    return {field: metadata.get(f"raw_{field}") for field in ("g", "W", "A", "X", "L")}


def _literal(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    import ast

    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except Exception:
            continue
    return text


def _lattice_matrix_from_parameters(values: list[float]) -> list[list[float]]:
    a, b, c, alpha, beta, gamma = values
    alpha_r = math.radians(alpha)
    beta_r = math.radians(beta)
    gamma_r = math.radians(gamma)
    ax = a
    bx = b * math.cos(gamma_r)
    by = b * math.sin(gamma_r)
    cx = c * math.cos(beta_r)
    cy = c * (math.cos(alpha_r) - math.cos(beta_r) * math.cos(gamma_r)) / math.sin(gamma_r)
    cz = math.sqrt(max(0.0, c * c - cx * cx - cy * cy))
    return [[ax, 0.0, 0.0], [bx, by, 0.0], [cx, cy, cz]]


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _gpu_devices(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    main()
