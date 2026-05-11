"""Dry-run skeleton for optional external MLIP validation.

This script prepares a local validation plan only. It does not import or run
MACE, CHGNet, MatGL, ASE, pymatgen, torch, DFT, or external APIs.
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import read_jsonl, write_json


DEFAULT_VALIDATORS = ("mace_mpa_0", "chgnet_0_3_0", "matgl_m3gnet")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a dry-run local MLIP validation plan without running MLIP."
    )
    parser.add_argument("--config", default="configs/mlip_validation.example.json")
    parser.add_argument("--candidate-index")
    parser.add_argument("--output-dir")
    parser.add_argument("--validator", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-mlip", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    config = _load_config(Path(args.config))
    candidate_index = Path(args.candidate_index or config.get("candidate_index", ""))
    output_dir = Path(args.output_dir or config.get("output_dir", "outputs/mlip_validation_dry_run"))
    validators = tuple(args.validator or config.get("validators", DEFAULT_VALIDATORS))
    limit = args.limit if args.limit is not None else _optional_int(config.get("limit"))

    if args.run_mlip:
        raise SystemExit(
            "--run-mlip is intentionally not implemented in FIIR core. "
            "Install MLIP tools in a separate environment and write local results for normalization."
        )
    if not candidate_index.exists():
        raise SystemExit(f"candidate index does not exist: {candidate_index}")
    if limit is not None and limit < 1:
        raise SystemExit("--limit must be positive")

    candidates = read_jsonl(candidate_index)
    selected = candidates[:limit] if limit is not None else candidates
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = _build_plan(
        config=config,
        candidate_index=candidate_index,
        output_dir=output_dir,
        validators=validators,
        candidates=selected,
    )
    summary = _summary(plan, config=config, candidate_index=candidate_index, output_dir=output_dir)
    files = {
        "plan": str(output_dir / "mlip_validation_plan.json"),
        "summary": str(output_dir / "mlip_validation_summary.json"),
        "report": str(output_dir / "report.md"),
    }
    write_json(files["plan"], plan)
    write_json(files["summary"], summary)
    Path(files["report"]).write_text(_render_report(summary), encoding="utf-8")

    print("Local MLIP validation dry-run plan complete")
    print(f"  run_mlip: {summary['run_mlip']}")
    print(f"  candidate_count: {summary['candidate_count']}")
    print(f"  planned_task_count: {summary['planned_task_count']}")
    print(f"  validators: {summary['validators']}")
    print(f"  plan: {files['plan']}")
    print(f"  summary: {files['summary']}")
    print(f"  report: {files['report']}")
    return {"summary": summary, "plan": plan, "files": files}


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"MLIP validation config must be a JSON object: {path}")
    return data


def _build_plan(
    *,
    config: dict[str, Any],
    candidate_index: Path,
    output_dir: Path,
    validators: tuple[str, ...],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for row in candidates:
        candidate_id = _candidate_id(row)
        formula = _formula(row)
        if not candidate_id:
            continue
        for validator in validators:
            tasks.append(
                {
                    "candidate_id": candidate_id,
                    "formula": formula,
                    "validator": validator,
                    "input_candidate_index": str(candidate_index),
                    "output_jsonl": str(output_dir / f"{validator}_validation_results.jsonl"),
                    "normalized_output_jsonl": str(output_dir / "normalized" / "validation_results.jsonl"),
                    "run_mlip": False,
                    "status": "planned_not_executed",
                }
            )
    return {
        "workflow": "local_mlip_validation_dry_run",
        "run_mlip": False,
        "no_network": True,
        "no_download": True,
        "no_training": True,
        "no_dft": True,
        "candidate_index": str(candidate_index),
        "output_dir": str(output_dir),
        "validators": list(validators),
        "normalization_command": _normalization_command(output_dir),
        "tasks": tasks,
        "config": config,
    }


def _summary(
    plan: dict[str, Any],
    *,
    config: dict[str, Any],
    candidate_index: Path,
    output_dir: Path,
) -> dict[str, Any]:
    formulas = sorted({str(task.get("formula")) for task in plan["tasks"] if task.get("formula")})
    validators = list(plan["validators"])
    return {
        "workflow": "local_mlip_validation_dry_run",
        "run_mlip": False,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "candidate_index": str(candidate_index),
        "output_dir": str(output_dir),
        "candidate_count": len({task["candidate_id"] for task in plan["tasks"]}),
        "planned_task_count": len(plan["tasks"]),
        "validators": validators,
        "formula_count": len(formulas),
        "formulas": formulas,
        "next_manual_steps": [
            "Create a separate MLIP environment outside fiir_crystal core.",
            "Install one validator at a time, starting with MACE.",
            "Write local validation result JSONL/CSV files into the planned output directory.",
            "Normalize those files with scripts/normalize_offline_validation_results.py.",
            "Import normalized rows into the existing offline validation check path before using F3.",
        ],
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "config": config,
    }


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Local MLIP Validation Dry-Run Plan",
        "",
        "## Boundary",
        "- This is a planning artifact only.",
        "- It does not run MACE, CHGNet, MatGL, ASE, pymatgen, torch, DFT, downloads, or external APIs.",
        "- MLIP tools must be installed in a separate environment and their outputs normalized before F3 import.",
        "",
        "## Summary",
        f"- candidate_count: {summary['candidate_count']}",
        f"- planned_task_count: {summary['planned_task_count']}",
        f"- validators: {summary['validators']}",
        f"- formulas: {summary['formulas']}",
        f"- output_dir: `{summary['output_dir']}`",
        "",
        "## Next Manual Steps",
    ]
    lines.extend(f"- {step}" for step in summary["next_manual_steps"])
    lines.append("")
    return "\n".join(lines)


def _normalization_command(output_dir: Path) -> str:
    return (
        "python scripts/normalize_offline_validation_results.py "
        f"--input {output_dir}/*_validation_results.jsonl "
        "--input-format jsonl "
        f"--output-jsonl {output_dir}/normalized/validation_results.jsonl "
        f"--output-summary {output_dir}/normalized/normalization_summary.json "
        f"--report {output_dir}/normalized/report.md"
    )


def _candidate_id(row: dict[str, Any]) -> str | None:
    value = row.get("candidate_id", row.get("sample_id", row.get("id")))
    return None if value in (None, "") else str(value)


def _formula(row: dict[str, Any]) -> str | None:
    condition = row.get("condition")
    if isinstance(condition, dict) and condition.get("formula") not in (None, ""):
        return str(condition["formula"])
    for key in ("formula", "composition"):
        if row.get(key) not in (None, ""):
            return str(row[key])
    return None


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return int(float(str(value)))


if __name__ == "__main__":
    main()
