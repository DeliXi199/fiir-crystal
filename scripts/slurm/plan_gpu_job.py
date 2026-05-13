#!/usr/bin/env python
"""Plan a resource-aware SLURM GPU job before submission.

By default this script only inspects SLURM and prints a deterministic sbatch
plan. It submits only when --run-sbatch is explicitly provided.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.io import write_json
from fiir_crystal.slurm_scheduling import (
    DEFAULT_FLEXIBLE_QUEUE_CPUS,
    DEFAULT_FLEXIBLE_QUEUE_GPUS,
    GPU_WEIGHT_PROFILES,
    GpuSchedulingConfig,
    discover_gpu_nodes,
    parse_gpu_weights,
    parse_partition_list,
    parse_scontrol_nodes,
    parse_sinfo_nodes,
    parse_slurm_time_limit_minutes,
    plan_gpu_job,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select the strongest currently available SLURM GPU node and build "
            "an sbatch plan. Pinned plans request all free CPUs/GPUs on the "
            "selected node; flexible queue plans use the configured queued shape."
        )
    )
    parser.add_argument("--partition", action="append", default=[], help="Allowed partition; repeat or comma-separate.")
    parser.add_argument("--accelerator", choices=("cuda", "any"), default="cuda")
    parser.add_argument("--min-gpus", type=int, default=1)
    parser.add_argument("--min-cpus", type=int, default=1)
    parser.add_argument("--min-memory-mb", type=int, default=0)
    parser.add_argument("--queue-min-gpus", type=int, default=DEFAULT_FLEXIBLE_QUEUE_GPUS)
    parser.add_argument("--queue-min-cpus", type=int, default=DEFAULT_FLEXIBLE_QUEUE_CPUS)
    parser.add_argument(
        "--layout",
        choices=("single-task", "one-task-per-gpu"),
        default="single-task",
        help="single-task requests all free CPUs in one task; one-task-per-gpu starts one task per free GPU.",
    )
    parser.add_argument(
        "--precision-profile",
        choices=tuple(sorted(GPU_WEIGHT_PROFILES)),
        default="tf32",
        help="GPU ranking profile for the task precision.",
    )
    parser.add_argument("--gpu-weight", action="append", default=[], help="Override a GPU weight as name=value.")
    parser.add_argument(
        "--gpu-queue-mode",
        choices=("auto", "pinned", "flexible"),
        default="auto",
        help=(
            "auto pins the best currently free eligible node and falls back to "
            "flexible multi-partition queueing only when no eligible node is free."
        ),
    )
    parser.add_argument("--job-name", default="fiir-gpu-job")
    parser.add_argument("--account")
    parser.add_argument("--time")
    parser.add_argument("--log-dir", default="logs/slurm")
    parser.add_argument("--submit-script", help="Optional batch script appended to the sbatch command.")
    parser.add_argument("--output-json", help="Write the full plan JSON.")
    parser.add_argument("--print-json", action="store_true", help="Print full plan JSON instead of a short summary.")
    parser.add_argument("--run-sbatch", action="store_true", help="Submit the selected plan with sbatch. Off by default.")
    parser.add_argument("--scontrol-output", help="Read fixture text instead of querying scontrol.")
    parser.add_argument("--sinfo-output", help="Read fixture text instead of querying sinfo.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.min_gpus < 1:
        raise SystemExit("--min-gpus must be at least 1")
    if args.min_cpus < 1:
        raise SystemExit("--min-cpus must be at least 1")
    if args.queue_min_gpus < 1:
        raise SystemExit("--queue-min-gpus must be at least 1")
    if args.queue_min_cpus < 1:
        raise SystemExit("--queue-min-cpus must be at least 1")
    if args.run_sbatch and not args.submit_script:
        raise SystemExit("--run-sbatch requires --submit-script")

    nodes = _load_nodes(args)
    config = GpuSchedulingConfig(
        accelerator=args.accelerator,
        precision_profile=args.precision_profile,
        allowed_partitions=parse_partition_list(args.partition),
        min_gpus=args.min_gpus,
        min_cpus=args.min_cpus,
        min_memory_mb=args.min_memory_mb,
        layout=args.layout,
        queue_min_gpus=args.queue_min_gpus,
        queue_min_cpus=args.queue_min_cpus,
        gpu_weights=parse_gpu_weights(args.gpu_weight, precision_profile=args.precision_profile),
        time_limit_minutes=parse_slurm_time_limit_minutes(args.time),
        queue_mode=args.gpu_queue_mode,
    )
    plan = plan_gpu_job(
        nodes,
        config,
        job_name=args.job_name,
        account=args.account,
        time_limit=args.time,
        log_dir=args.log_dir,
        submit_script=args.submit_script,
    )
    if args.output_json:
        write_json(args.output_json, plan)

    if args.print_json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        _print_summary(plan, args.output_json)

    if args.run_sbatch:
        sbatch_command = plan.get("sbatch", {}).get("sbatch_command")
        if not plan.get("ready") or not sbatch_command:
            raise SystemExit("no eligible GPU node is ready for sbatch submission")
        completed = subprocess.run(sbatch_command, text=True, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
    elif not plan.get("ready"):
        raise SystemExit(1)
    return plan


def _load_nodes(args: argparse.Namespace):
    if args.scontrol_output:
        return parse_scontrol_nodes(Path(args.scontrol_output).read_text(encoding="utf-8"))
    if args.sinfo_output:
        return parse_sinfo_nodes(Path(args.sinfo_output).read_text(encoding="utf-8"))
    return discover_gpu_nodes()


def _print_summary(plan: dict[str, Any], output_json: str | None) -> None:
    print("FIIR GPU scheduling policy:")
    print(f"  ready: {plan['ready']}")
    print(f"  reason: {plan['reason']}")
    if not plan["ready"]:
        return
    selected = plan["selection"]
    request = plan["sbatch"]["request"]
    node = selected["selected_node"]
    print(f"  selected_node: {node['name'] if node else 'slurm_assigned_at_runtime'}")
    print(f"  selected_partition: {selected['selected_partition']}")
    print(f"  gpu_model: {node['gpu_model_key'] if node else 'slurm_assigned_at_runtime'}")
    print(f"  precision_profile: {plan['config']['precision_profile']}")
    print(f"  gpu_queue_mode: {plan['config']['effective_queue_mode']}")
    if selected["selected_partition"] == plan["config"]["test_partition"]:
        print(
            "  test_partition_time_guard: "
            f"eligible only up to {plan['config']['test_partition_max_minutes']} minutes; "
            "selection still uses the normal GPU resource score"
        )
    print(f"  requested_gpus: {request['gpus']}")
    print(f"  requested_cpus: {request['cpus']}")
    print(f"  requested_gres: {request['gres']}")
    print(f"  layout: {request['layout']}")
    print(f"  exclusive: {request['exclusive']}")
    if output_json:
        print(f"  output_json: {output_json}")
    print("sbatch command:")
    print(f"  {plan['sbatch']['sbatch_command_quoted']}")


if __name__ == "__main__":
    main()
