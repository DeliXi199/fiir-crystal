#!/usr/bin/env python
"""Run local-only optional MLIP inference on existing FIIR candidates.

This script is an external workflow boundary, not part of the stdlib-only
``fiir_crystal`` core. It imports optional MLIP packages only when real
execution is requested. Dry-run mode writes provenance-shaped rows without
loading CHGNet, MatGL, torch, DGL, or model checkpoints.
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
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT in sys.path:
    sys.path.remove(PROJECT_ROOT_TEXT)
sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.io import read_jsonl, write_json, write_jsonl
from scripts.run_mace_offline_validation import (
    _atoms_from_candidate,
    _candidate_id,
    _condition,
    _formula,
    _generation_condition,
    _gpu_devices,
    _max_vector_norm,
    _raw_sequence_fields,
    _select_rows,
    _spacegroup,
    _string_or_none,
    _stress_max,
    _literal,
    _lattice_matrix_from_parameters,
)


MLIP_DEFAULTS = {
    "chgnet": {
        "model_name": "0.3.0",
        "validator_name": "chgnet_0_3_0",
        "output_dir": Path("outputs/mlip_validation_chgnet"),
        "single_source": "local_mlip_chgnet_single_point",
        "relax_source": "local_mlip_chgnet_relaxation",
    },
    "matgl": {
        "model_name": "matgl_m3gnet",
        "validator_name": "matgl_m3gnet",
        "output_dir": Path("outputs/mlip_validation_matgl"),
        "single_source": "local_mlip_matgl_single_point",
        "relax_source": "local_mlip_matgl_relaxation",
    },
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run optional local CHGNet/MatGL inference over existing CrystalFormer candidate JSONL files."
    )
    parser.add_argument("--mlip-kind", choices=tuple(MLIP_DEFAULTS), required=True)
    parser.add_argument("--candidates-jsonl", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--output-jsonl")
    parser.add_argument("--output-summary")
    parser.add_argument("--report")
    parser.add_argument("--model-name")
    parser.add_argument("--model-path")
    parser.add_argument("--validator-name")
    parser.add_argument("--validation-source")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpu-devices", default=os.environ.get("CUDA_VISIBLE_DEVICES", ""))
    parser.add_argument("--relax", action="store_true")
    parser.add_argument("--relax-cell", action="store_true")
    parser.add_argument("--relax-steps", type=int, default=100)
    parser.add_argument("--fmax", type=float, default=0.05)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _finalize_args(parse_args(argv))
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.shard_count < 1:
        raise SystemExit("--shard-count must be positive")
    if args.shard_index is not None and not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("--shard-index must be in [0, shard_count)")
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    if args.relax_steps < 1:
        raise SystemExit("--relax-steps must be positive")
    if args.fmax <= 0:
        raise SystemExit("--fmax must be positive")
    if args.workers > 1 and args.shard_index is None:
        return _run_worker_pool(args)
    return _run_single(args)


def _finalize_args(args: argparse.Namespace) -> argparse.Namespace:
    defaults = MLIP_DEFAULTS[args.mlip_kind]
    output_dir = Path(args.output_dir) if args.output_dir else defaults["output_dir"]
    args.output_dir = str(output_dir)
    args.output_jsonl = args.output_jsonl or str(output_dir / f"{args.mlip_kind}_validation_results.jsonl")
    args.output_summary = args.output_summary or str(output_dir / f"{args.mlip_kind}_validation_summary.json")
    args.report = args.report or str(output_dir / "report.md")
    args.model_name = args.model_name or str(defaults["model_name"])
    args.validator_name = args.validator_name or str(defaults["validator_name"])
    args.validation_source = args.validation_source or str(
        defaults["relax_source"] if args.relax else defaults["single_source"]
    )
    if args.model_path is None:
        env_key = f"FIIR_{args.mlip_kind.upper()}_MODEL_PATH"
        args.model_path = os.environ.get(env_key)
    return args


def _run_single(args: argparse.Namespace) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    start_time = time.monotonic()
    candidates_path = Path(args.candidates_jsonl)
    output_jsonl = Path(args.output_jsonl)
    output_summary = Path(args.output_summary)
    report = Path(args.report)
    rows = _select_rows(read_jsonl(candidates_path), args.limit, args.shard_index, args.shard_count)

    if args.dry_run:
        results = [_planned_row(row, args, candidates_path) for row in rows]
    else:
        runtime = _load_runtime(args)
        results = [
            _evaluate_row(
                row,
                args=args,
                candidates_path=candidates_path,
                runtime=runtime,
            )
            for row in rows
        ]

    results = sorted(results, key=lambda row: (str(row.get("formula")), str(row.get("candidate_id"))))
    summary = _summary(
        args=args,
        candidates_path=candidates_path,
        rows=results,
        started=started,
        elapsed_seconds=time.monotonic() - start_time,
    )
    _write_outputs(output_jsonl, output_summary, report, results, summary)
    _print_summary(summary, output_jsonl, output_summary, report)
    if args.strict and summary["failed_count"]:
        raise SystemExit(f"strict {args.mlip_kind} validation found failed rows")
    return {"summary": summary, "rows": results}


def _run_worker_pool(args: argparse.Namespace) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    start_time = time.monotonic()
    output_jsonl = Path(args.output_jsonl)
    output_summary = Path(args.output_summary)
    report = Path(args.report)
    shard_dir = output_jsonl.parent / f"{args.mlip_kind}_worker_shards"
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
        raise SystemExit(
            f"{args.mlip_kind} worker pool failed"
            if failures
            else f"strict {args.mlip_kind} validation found failed rows"
        )
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
        "--mlip-kind",
        args.mlip_kind,
        "--candidates-jsonl",
        args.candidates_jsonl,
        "--output-dir",
        args.output_dir,
        "--output-jsonl",
        str(output_jsonl),
        "--output-summary",
        str(output_summary),
        "--report",
        str(report),
        "--model-name",
        args.model_name,
        "--validator-name",
        args.validator_name,
        "--validation-source",
        args.validation_source,
        "--device",
        args.device,
        "--shard-index",
        str(index),
        "--shard-count",
        str(args.workers),
        "--workers",
        "1",
    ]
    if args.model_path:
        command.extend(["--model-path", args.model_path])
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.relax:
        command.append("--relax")
        command.extend(["--relax-steps", str(args.relax_steps), "--fmax", str(args.fmax)])
    if args.relax_cell:
        command.append("--relax-cell")
    if args.strict:
        command.append("--strict")
    if args.dry_run:
        command.append("--dry-run")
    return command


def _load_runtime(args: argparse.Namespace) -> dict[str, Any]:
    if args.mlip_kind == "chgnet":
        return _load_chgnet_runtime(args)
    if args.mlip_kind == "matgl":
        return _load_matgl_runtime(args)
    raise SystemExit(f"unsupported MLIP kind: {args.mlip_kind}")


def _load_chgnet_runtime(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import chgnet  # type: ignore[import-not-found]
        import torch  # type: ignore[import-not-found]
        from chgnet.model.model import CHGNet  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise SystemExit(f"CHGNet runtime dependencies are unavailable: {exc}") from exc

    actual_device = args.device
    if actual_device == "auto":
        actual_device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CHGNet.load(
        model_name=args.model_name,
        use_device=actual_device,
        check_cuda_mem=False,
        verbose=False,
    )
    return {
        "kind": "chgnet",
        "model": model,
        "actual_device": actual_device,
        "package_versions": {
            "chgnet": str(getattr(chgnet, "__version__", "unknown")),
            "torch": str(getattr(torch, "__version__", "unknown")),
        },
    }


def _load_matgl_runtime(args: argparse.Namespace) -> dict[str, Any]:
    if not args.model_path:
        raise SystemExit(
            "MatGL execution requires --model-path or FIIR_MATGL_MODEL_PATH to avoid implicit model downloads."
        )
    model_path = Path(args.model_path).expanduser()
    if not model_path.exists():
        raise SystemExit(f"MatGL model path does not exist: {model_path}")
    matgl_home = _prepare_matgl_home(args)
    try:
        import matgl  # type: ignore[import-not-found]
        import torch  # type: ignore[import-not-found]
        from matgl.ext.ase import PESCalculator  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise SystemExit(f"MatGL runtime dependencies are unavailable: {exc}") from exc

    actual_device = args.device
    if actual_device == "auto":
        actual_device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        potential = matgl.load_model(str(model_path), device=actual_device)
    except TypeError:
        potential = matgl.load_model(str(model_path))
    if hasattr(potential, "to"):
        potential = potential.to(actual_device)
    try:
        calc = PESCalculator(potential)
    except TypeError:
        calc = PESCalculator(potential=potential)
    return {
        "kind": "matgl",
        "calc": calc,
        "actual_device": actual_device,
        "matgl_home": str(matgl_home),
        "package_versions": {
            "matgl": str(getattr(matgl, "__version__", "unknown")),
            "torch": str(getattr(torch, "__version__", "unknown")),
        },
    }


def _prepare_matgl_home(args: argparse.Namespace) -> Path:
    """Give MatGL a writable home/cache without relying on the login HOME."""

    matgl_home_env = os.environ.get("FIIR_MATGL_HOME")
    matgl_home = Path(matgl_home_env).expanduser() if matgl_home_env else Path(args.output_dir) / "matgl_home"
    matgl_home.mkdir(parents=True, exist_ok=True)
    if "FIIR_ORIGINAL_HOME" not in os.environ and os.environ.get("HOME"):
        os.environ["FIIR_ORIGINAL_HOME"] = str(os.environ["HOME"])
    os.environ["HOME"] = str(matgl_home)
    return matgl_home


def _evaluate_row(
    row: dict[str, Any],
    *,
    args: argparse.Namespace,
    candidates_path: Path,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    if runtime["kind"] == "chgnet":
        return _evaluate_chgnet_row(row, args=args, candidates_path=candidates_path, runtime=runtime)
    if runtime["kind"] == "matgl":
        return _evaluate_matgl_row(row, args=args, candidates_path=candidates_path, runtime=runtime)
    raise RuntimeError(f"unsupported runtime kind: {runtime['kind']}")


def _evaluate_chgnet_row(
    row: dict[str, Any],
    *,
    args: argparse.Namespace,
    candidates_path: Path,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    base = _base_validation_row(row, args, candidates_path)
    try:
        structure = _pymatgen_structure_from_candidate(row)
        if args.relax:
            from chgnet.model.dynamics import StructOptimizer  # type: ignore[import-not-found]

            optimizer = StructOptimizer(model=runtime["model"], use_device=runtime["actual_device"])
            result = optimizer.relax(
                structure,
                fmax=args.fmax,
                steps=args.relax_steps,
                relax_cell=bool(args.relax_cell),
                loginterval=0,
                verbose=False,
            )
            if isinstance(result, dict) and result.get("final_structure") is not None:
                structure = result["final_structure"]
            base["relaxed"] = True
        prediction = runtime["model"].predict_structure(structure)
        energy = _tensor_scalar(prediction.get("e"))
        forces = _tensor_nested(prediction.get("f"))
        stress = _tensor_nested(prediction.get("s"))
        force_max = _max_vector_norm(forces) if forces is not None else None
        stress_max = _max_abs_nested(stress)
        base.update(
            {
                "validation_status": "completed",
                "force_max": force_max,
                "stress_max": stress_max,
                "relaxed": bool(base["relaxed"]),
                "relaxation_converged": _relaxation_converged(force_max, args) if args.relax else None,
            }
        )
        base["metadata"].update(
            {
                "chgnet_energy_eV_per_atom": energy,
                "num_atoms": len(structure),
                "device": runtime["actual_device"],
                "package_versions": runtime["package_versions"],
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
                "device": runtime["actual_device"],
                "package_versions": runtime["package_versions"],
                "elapsed_seconds": round(time.monotonic() - started, 6),
            }
        )
    return base


def _evaluate_matgl_row(
    row: dict[str, Any],
    *,
    args: argparse.Namespace,
    candidates_path: Path,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    base = _base_validation_row(row, args, candidates_path)
    try:
        atoms = _atoms_from_candidate(row)
        atoms.calc = runtime["calc"]
        if args.relax:
            _relax_atoms(atoms, args)
            base["relaxed"] = True
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
                "relaxation_converged": _relaxation_converged(force_max, args) if args.relax else None,
            }
        )
        base["metadata"].update(
            {
                "matgl_total_energy_eV": energy,
                "matgl_total_energy_eV_per_atom": energy / max(1, len(atoms)),
                "num_atoms": len(atoms),
                "device": runtime["actual_device"],
                "matgl_home": runtime.get("matgl_home"),
                "package_versions": runtime["package_versions"],
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
                "device": runtime["actual_device"],
                "matgl_home": runtime.get("matgl_home"),
                "package_versions": runtime["package_versions"],
                "elapsed_seconds": round(time.monotonic() - started, 6),
            }
        )
    return base


def _planned_row(
    row: dict[str, Any],
    args: argparse.Namespace,
    candidates_path: Path,
) -> dict[str, Any]:
    base = _base_validation_row(row, args, candidates_path)
    base["validation_status"] = "planned_not_executed"
    base["metadata"]["dry_run"] = True
    return base


def _base_validation_row(
    row: dict[str, Any],
    args: argparse.Namespace,
    candidates_path: Path,
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
        "validator": args.validator_name,
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
            "script": "scripts/run_mlip_offline_validation.py",
            "mlip_kind": args.mlip_kind,
            "local_only": True,
            "runs_mlip": not args.dry_run,
            "runs_dft": False,
            "runs_training": False,
            "runs_generation": False,
            "calls_external_apis": False,
            "downloads": False,
            "candidate_source_path": str(candidates_path),
            "model_name": args.model_name,
            "model_path": args.model_path,
            "model_sha256": _sha256_or_none(args.model_path),
            "validator_name": args.validator_name,
            "relax_requested": bool(args.relax),
            "relax_cell_requested": bool(args.relax_cell),
            "energy_above_hull_status": "unavailable_without_local_hull_reference",
        },
    }


def _pymatgen_structure_from_candidate(row: dict[str, Any]) -> Any:
    try:
        from pymatgen.core import Lattice, Structure  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise RuntimeError(f"pymatgen is unavailable: {exc}") from exc

    species = [str(item) for item in row.get("species", []) if str(item)]
    coords = row.get("frac_coords", [])
    lattice = row.get("lattice_matrix", [])
    if not species or not coords or not lattice:
        species, coords, lattice = _structure_from_raw_sequence(row)
    if not species or not coords or not lattice:
        raise ValueError("candidate does not contain species, fractional coordinates, and lattice")
    if len(species) != len(coords):
        raise ValueError(f"species/coordinate length mismatch: {len(species)} != {len(coords)}")
    return Structure(Lattice(lattice), species, coords, coords_are_cartesian=False)


def _structure_from_raw_sequence(row: dict[str, Any]) -> tuple[list[str], list[list[float]], list[list[float]]]:
    try:
        from ase.data import chemical_symbols  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise RuntimeError(f"ASE is unavailable for raw sequence decoding: {exc}") from exc

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


def _relax_atoms(atoms: Any, args: argparse.Namespace) -> bool:
    from ase.optimize import FIRE  # type: ignore[import-not-found]

    target = atoms
    if args.relax_cell:
        from ase.filters import FrechetCellFilter  # type: ignore[import-not-found]

        target = FrechetCellFilter(atoms)
    optimizer = FIRE(target, logfile=None)
    return bool(optimizer.run(fmax=args.fmax, steps=args.relax_steps))


def _relaxation_converged(force_max: float | None, args: argparse.Namespace) -> bool | None:
    if force_max is None:
        return None
    return bool(force_max <= args.fmax)


def _summary(
    *,
    args: argparse.Namespace,
    candidates_path: Path,
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
        "workflow": f"{args.mlip_kind}_offline_validation",
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
        "mlip_kind": args.mlip_kind,
        "model_name": args.model_name,
        "model_path": args.model_path,
        "model_sha256": _sha256_or_none(args.model_path),
        "validator_name": args.validator_name,
        "validation_source": args.validation_source,
        "device": args.device,
        "limit": args.limit,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "worker_count": args.workers,
        "relax": bool(args.relax),
        "relax_cell": bool(args.relax_cell),
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
            f"{args.mlip_kind} energy/force inference is local MLIP evidence.",
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
    title = str(summary["mlip_kind"]).upper()
    lines = [
        f"# {title} Offline Validation Report",
        "",
        "## Boundary",
        "- Reads existing candidate JSONL files only.",
        "- Runs local MLIP inference only when dry_run is false.",
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
        f"- validator_name: {summary['validator_name']}",
        f"- output_jsonl: `{summary['output_jsonl']}`",
        "",
        "## Notes",
    ]
    lines.extend(f"- {note}" for note in summary["notes"])
    lines.append("")
    return "\n".join(lines)


def _print_summary(summary: dict[str, Any], output_jsonl: Path, output_summary: Path, report: Path) -> None:
    print(f"{summary['mlip_kind']} offline validation complete")
    print(f"  row_count: {summary['row_count']}")
    print(f"  completed_count: {summary['completed_count']}")
    print(f"  failed_count: {summary['failed_count']}")
    print(f"  f3_available_candidate_count: {summary['f3_available_candidate_count']}")
    print(f"  output_jsonl: {output_jsonl}")
    print(f"  summary: {output_summary}")
    print(f"  report: {report}")


def _tensor_scalar(value: Any) -> float | None:
    data = _to_plain_data(value)
    values = list(_flatten(data))
    if not values:
        return None
    try:
        return float(values[0])
    except (TypeError, ValueError):
        return None


def _tensor_nested(value: Any) -> Any:
    data = _to_plain_data(value)
    return None if data is None else data


def _to_plain_data(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return value


def _flatten(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        flattened: list[float] = []
        for item in value:
            flattened.extend(_flatten(item))
        return flattened
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def _max_abs_nested(value: Any) -> float | None:
    values = _flatten(value)
    return None if not values else max(abs(item) for item in values)


def _sha256_or_none(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    path = Path(value).expanduser()
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
