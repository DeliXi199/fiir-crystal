#!/usr/bin/env python
"""Plan CPU or GPU SLURM jobs through the unified FIIR scheduler."""

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
    CPU_PARTITION_ORDER_DEFAULT,
    GPU_WEIGHT_PROFILES,
    CpuSchedulingConfig,
    GpuSchedulingConfig,
    concurrency_warning,
    cpu_plan_shell_vars,
    normalize_partitions,
    parse_gpu_weights,
    parse_partition_list,
    parse_scontrol_cpu_nodes,
    parse_scontrol_nodes,
    parse_sinfo_cpu_nodes,
    parse_sinfo_nodes,
    parse_slurm_time_limit_minutes,
    plan_slurm_job,
    shell_assignments,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan a FIIR SLURM job with either the CPU or GPU scheduling policy."
    )
    parser.add_argument("--kind", choices=("cpu", "gpu"), required=True)
    parser.add_argument("--job-name")
    parser.add_argument("--account")
    parser.add_argument("--time")
    parser.add_argument("--log-dir", default="logs/slurm")
    parser.add_argument("--submit-script")
    parser.add_argument("--output-json")
    parser.add_argument("--print-json", action="store_true")
    parser.add_argument("--shell-vars", action="store_true", help="Print CPU wrapper shell assignments.")
    parser.add_argument("--run-sbatch", action="store_true", help="Submit with sbatch. Off by default.")

    cpu = parser.add_argument_group("CPU policy")
    cpu.add_argument("--partition-order", default=" ".join(CPU_PARTITION_ORDER_DEFAULT))
    cpu.add_argument("--expected-minutes", type=int, default=30)
    cpu.add_argument("--short-task-minutes", type=int, default=30)
    cpu.add_argument("--test-partition", default="test")
    cpu.add_argument("--force-partition", default="")
    cpu.add_argument("--max-concurrent-generations", default="auto")

    gpu = parser.add_argument_group("GPU policy")
    gpu.add_argument("--partition", action="append", default=[], help="Allowed GPU partition; repeat or comma-separate.")
    gpu.add_argument("--accelerator", choices=("cuda", "any"), default="cuda")
    gpu.add_argument("--min-gpus", type=int, default=1)
    gpu.add_argument("--min-cpus", type=int, default=1)
    gpu.add_argument("--min-memory-mb", type=int, default=0)
    gpu.add_argument("--layout", choices=("single-task", "one-task-per-gpu"), default="single-task")
    gpu.add_argument(
        "--precision-profile",
        choices=tuple(sorted(GPU_WEIGHT_PROFILES)),
        default="tf32",
        help="GPU ranking profile for the task precision.",
    )
    gpu.add_argument("--gpu-weight", action="append", default=[], help="Override a GPU weight as name=value.")
    gpu.add_argument(
        "--gpu-queue-mode",
        choices=("auto", "pinned", "flexible"),
        default="auto",
        help=(
            "GPU queue mode. auto pins the best currently free eligible node and "
            "falls back to flexible multi-partition queueing only when no eligible node is free."
        ),
    )

    fixtures = parser.add_argument_group("fixtures")
    fixtures.add_argument("--scontrol-output")
    fixtures.add_argument("--sinfo-output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.run_sbatch and not args.submit_script:
        raise SystemExit("--run-sbatch requires --submit-script")

    plan = _build_plan(args)
    warning = (
        concurrency_warning(
            args.expected_minutes,
            args.short_task_minutes,
            args.max_concurrent_generations,
        )
        if args.kind == "cpu"
        else ""
    )
    if warning:
        plan["concurrency_warning"] = warning
    if args.output_json:
        write_json(args.output_json, plan)

    if args.shell_vars:
        if args.kind != "cpu":
            raise SystemExit("--shell-vars is currently intended for CPU submit wrappers")
        values = cpu_plan_shell_vars(plan)
        values["FIIR_CONCURRENCY_WARNING"] = warning
        print(shell_assignments(values))
    elif args.print_json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        _print_summary(plan, args.output_json)

    if args.run_sbatch:
        sbatch_command = plan.get("sbatch", {}).get("sbatch_command")
        if not plan.get("ready") or not sbatch_command:
            raise SystemExit("no eligible SLURM plan is ready for sbatch submission")
        completed = subprocess.run(sbatch_command, text=True, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
    elif not plan.get("ready"):
        raise SystemExit(1)
    return plan


def _build_plan(args: argparse.Namespace) -> dict[str, Any]:
    if args.kind == "cpu":
        nodes = _load_cpu_nodes(args)
        config = CpuSchedulingConfig(
            partition_order=normalize_partitions(args.partition_order.split()),
            expected_minutes=args.expected_minutes,
            short_task_minutes=args.short_task_minutes,
            test_partition=args.test_partition,
            force_partition=args.force_partition,
        )
        return plan_slurm_job(
            kind="cpu",
            cpu_nodes=nodes,
            cpu_config=config,
            job_name=args.job_name,
            account=args.account,
            time_limit=args.time,
            log_dir=args.log_dir,
            submit_script=args.submit_script,
        )

    if args.min_gpus < 1:
        raise SystemExit("--min-gpus must be at least 1")
    if args.min_cpus < 1:
        raise SystemExit("--min-cpus must be at least 1")
    nodes = _load_gpu_nodes(args)
    config = GpuSchedulingConfig(
        accelerator=args.accelerator,
        precision_profile=args.precision_profile,
        allowed_partitions=parse_partition_list(args.partition),
        min_gpus=args.min_gpus,
        min_cpus=args.min_cpus,
        min_memory_mb=args.min_memory_mb,
        layout=args.layout,
        gpu_weights=parse_gpu_weights(args.gpu_weight, precision_profile=args.precision_profile),
        time_limit_minutes=parse_slurm_time_limit_minutes(args.time),
        queue_mode=args.gpu_queue_mode,
    )
    return plan_slurm_job(
        kind="gpu",
        gpu_nodes=nodes,
        gpu_config=config,
        job_name=args.job_name or "fiir-gpu-job",
        account=args.account,
        time_limit=args.time,
        log_dir=args.log_dir,
        submit_script=args.submit_script,
    )


def _load_cpu_nodes(args: argparse.Namespace):
    if args.scontrol_output:
        return parse_scontrol_cpu_nodes(Path(args.scontrol_output).read_text(encoding="utf-8"))
    if args.sinfo_output:
        return parse_sinfo_cpu_nodes(Path(args.sinfo_output).read_text(encoding="utf-8"))
    return None


def _load_gpu_nodes(args: argparse.Namespace):
    if args.scontrol_output:
        return parse_scontrol_nodes(Path(args.scontrol_output).read_text(encoding="utf-8"))
    if args.sinfo_output:
        return parse_sinfo_nodes(Path(args.sinfo_output).read_text(encoding="utf-8"))
    return None


def _print_summary(plan: dict[str, Any], output_json: str | None) -> None:
    print("FIIR SLURM scheduling policy:")
    print(f"  kind: {plan.get('kind')}")
    print(f"  ready: {plan['ready']}")
    print(f"  reason: {plan['reason']}")
    if plan.get("concurrency_warning"):
        print(f"  concurrency_warning: {plan['concurrency_warning']}")
    if not plan["ready"]:
        return
    selection = plan["selection"]
    request = plan["sbatch"]["request"]
    if plan.get("kind") == "cpu":
        print(f"  selected_partition: {selection['partition_arg']}")
        print(f"  selected_core_budget: {request['cpus'] if request['cpus'] is not None else 'auto'}")
    else:
        node = selection["selected_node"]
        print(f"  selected_node: {node['name'] if node else 'slurm_assigned_at_runtime'}")
        print(f"  selected_partition: {selection['selected_partition']}")
        print(f"  gpu_model: {node['gpu_model_key'] if node else 'slurm_assigned_at_runtime'}")
        print(f"  precision_profile: {plan['config']['precision_profile']}")
        print(f"  gpu_queue_mode: {plan['config']['effective_queue_mode']}")
        if selection["selected_partition"] == plan["config"]["test_partition"]:
            print(
                "  test_partition_time_guard: "
                f"eligible only up to {plan['config']['test_partition_max_minutes']} minutes; "
                "selection still uses the normal GPU resource score"
            )
        print(f"  requested_gpus: {request['gpus']}")
        print(f"  requested_cpus: {request['cpus']}")
        print(f"  requested_gres: {request['gres']}")
    print(f"  exclusive: {request['exclusive']}")
    if output_json:
        print(f"  output_json: {output_json}")
    print("sbatch command:")
    print(f"  {plan['sbatch']['sbatch_command_quoted']}")


if __name__ == "__main__":
    main()
