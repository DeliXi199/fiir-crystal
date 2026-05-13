"""Unified SLURM scheduling policies for FIIR workflows.

This module provides one standard-library-only access point for CPU and GPU
SLURM planning. It does not submit jobs by itself; callers can inspect the
returned plan and decide whether to pass the generated arguments to `sbatch`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import shlex
import subprocess
from typing import Any, Iterable, Sequence

from fiir_crystal.slurm_gpu_policy import (
    DEFAULT_FLEXIBLE_QUEUE_CPUS,
    DEFAULT_FLEXIBLE_QUEUE_GPUS,
    DEFAULT_FLEXIBLE_QUEUE_MEMORY_MB,
    DEFAULT_GPU_PRECISION_PROFILE,
    DEFAULT_GPU_WEIGHTS,
    FP64_GPU_WEIGHTS,
    GPU_WEIGHT_PROFILES,
    GpuNode,
    GpuSchedulingConfig,
    build_sbatch_plan as build_gpu_sbatch_plan,
    config_to_dict as gpu_config_to_dict,
    discover_gpu_nodes,
    gpu_weights_for_profile,
    normalize_precision_profile,
    parse_gpu_weights,
    parse_gres,
    parse_partition_list,
    parse_scontrol_nodes,
    parse_sinfo_cpu_counts,
    parse_sinfo_nodes,
    parse_slurm_time_limit_minutes,
    parse_tres,
    plan_gpu_job,
    effective_queue_mode,
    flexible_queue_partitions,
    queueable_gpu_nodes,
    select_best_gpu_node,
)


CPU_PARTITION_ORDER_DEFAULT = ("regular256", "regular128", "regular6430", "regular", "test")


@dataclass(frozen=True)
class CpuSchedulingConfig:
    """Configuration for CPU-only SLURM jobs."""

    partition_order: tuple[str, ...] = CPU_PARTITION_ORDER_DEFAULT
    expected_minutes: int = 30
    short_task_minutes: int = 30
    test_partition: str = "test"
    force_partition: str = ""
    default_partition_cores: int = 64
    partition_core_overrides: dict[str, int] = field(default_factory=lambda: {"regular": 56})
    exclusive: bool = True
    queue_all_when_no_idle: bool = True


@dataclass(frozen=True)
class CpuNode:
    """A compact view of one CPU-capable SLURM node."""

    name: str
    partitions: tuple[str, ...]
    state: str
    total_cpus: int
    allocated_cpus: int = 0
    total_memory_mb: int = 0
    free_memory_mb: int = 0
    gres: str = "(null)"

    @property
    def idle_cpus(self) -> int:
        return max(0, self.total_cpus - self.allocated_cpus)

    @property
    def is_idle(self) -> bool:
        return "IDLE" in self.state.upper() and self.idle_cpus > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "partitions": list(self.partitions),
            "state": self.state,
            "total_cpus": self.total_cpus,
            "allocated_cpus": self.allocated_cpus,
            "idle_cpus": self.idle_cpus,
            "total_memory_mb": self.total_memory_mb,
            "free_memory_mb": self.free_memory_mb,
            "gres": self.gres,
            "is_idle": self.is_idle,
        }


@dataclass(frozen=True)
class CpuSelection:
    """Selected CPU partition and optional backing idle node."""

    partition_arg: str
    selected_partition: str
    selected_node: CpuNode | None
    core_budget: int | None
    reason: str
    candidates: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "partition_arg": self.partition_arg,
            "selected_partition": self.selected_partition,
            "selected_node": self.selected_node.to_dict() if self.selected_node else None,
            "core_budget": self.core_budget,
            "reason": self.reason,
            "candidates": list(self.candidates),
        }


def discover_cpu_nodes() -> list[CpuNode]:
    """Query SLURM and return CPU node state."""

    scontrol_result = _run_command(["scontrol", "show", "node"])
    if scontrol_result.returncode == 0:
        nodes = parse_scontrol_cpu_nodes(scontrol_result.stdout)
        if nodes:
            return nodes

    sinfo_result = _run_command(["sinfo", "-N", "-h", "-o", "%N|%P|%T|%C|%m|%G"])
    if sinfo_result.returncode == 0:
        nodes = parse_sinfo_cpu_nodes(sinfo_result.stdout)
        if nodes:
            return nodes

    return []


def parse_scontrol_cpu_nodes(text: str) -> list[CpuNode]:
    """Parse `scontrol show node` output for CPU scheduling."""

    nodes: list[CpuNode] = []
    for block in _split_scontrol_blocks(text):
        fields = _parse_key_values(block)
        name = fields.get("NodeName", "")
        if not name:
            continue
        total_cpus = _positive_int(fields.get("CPUTot")) or _positive_int(
            parse_tres(fields.get("CfgTRES", "")).get("cpu")
        )
        if total_cpus <= 0:
            continue
        total_memory_mb = _memory_to_mb(fields.get("RealMemory", ""))
        free_memory_mb = _memory_to_mb(fields.get("FreeMem", "")) or total_memory_mb
        nodes.append(
            CpuNode(
                name=name,
                partitions=parse_partition_list([fields.get("Partitions", "")]),
                state=fields.get("State", ""),
                total_cpus=total_cpus,
                allocated_cpus=_positive_int(fields.get("CPUAlloc")),
                total_memory_mb=total_memory_mb,
                free_memory_mb=free_memory_mb,
                gres=fields.get("Gres", "(null)"),
            )
        )
    return sorted(nodes, key=lambda node: node.name)


def parse_sinfo_cpu_nodes(text: str) -> list[CpuNode]:
    """Parse `sinfo -N` pipe-delimited output for CPU scheduling."""

    by_node: dict[str, dict[str, Any]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "|" not in line:
            continue
        pieces = line.split("|")
        if len(pieces) < 6:
            continue
        name, partition, state, cpus, memory, gres = pieces[:6]
        allocated, _idle, _other, total = parse_sinfo_cpu_counts(cpus)
        if total <= 0:
            continue
        entry = by_node.setdefault(
            name,
            {
                "partitions": [],
                "state": state,
                "total_cpus": total,
                "allocated_cpus": allocated,
                "memory": _memory_to_mb(memory),
                "gres": gres,
            },
        )
        normalized = partition.strip().rstrip("*")
        if normalized and normalized not in entry["partitions"]:
            entry["partitions"].append(normalized)

    nodes = [
        CpuNode(
            name=name,
            partitions=tuple(fields["partitions"]),
            state=str(fields["state"]),
            total_cpus=int(fields["total_cpus"]),
            allocated_cpus=int(fields["allocated_cpus"]),
            total_memory_mb=int(fields["memory"]),
            free_memory_mb=int(fields["memory"]),
            gres=str(fields["gres"]),
        )
        for name, fields in by_node.items()
    ]
    return sorted(nodes, key=lambda node: node.name)


def select_cpu_partition(
    nodes: Sequence[CpuNode], config: CpuSchedulingConfig | None = None
) -> CpuSelection:
    """Select a CPU partition using the CrystalFormer-compatible policy."""

    config = config or CpuSchedulingConfig()
    partition_order = normalize_partitions(config.partition_order)
    test_partition = normalize_partition_name(config.test_partition)
    force_partition = normalize_partition_name(config.force_partition)
    candidates = _cpu_candidates(nodes, partition_order)

    if force_partition:
        node = _best_idle_cpu_node(nodes, force_partition)
        return CpuSelection(
            partition_arg=force_partition,
            selected_partition=force_partition,
            selected_node=node,
            core_budget=partition_core_budget(force_partition, config, node),
            reason="forced",
            candidates=candidates,
        )

    if (
        config.expected_minutes <= config.short_task_minutes
        and test_partition
        and _has_idle_cpu_node(nodes, test_partition)
    ):
        node = _best_idle_cpu_node(nodes, test_partition)
        return CpuSelection(
            partition_arg=test_partition,
            selected_partition=test_partition,
            selected_node=node,
            core_budget=partition_core_budget(test_partition, config, node),
            reason="short_job_idle_test",
            candidates=candidates,
        )

    for partition in partition_order:
        if _has_idle_cpu_node(nodes, partition):
            node = _best_idle_cpu_node(nodes, partition)
            return CpuSelection(
                partition_arg=partition,
                selected_partition=partition,
                selected_node=node,
                core_budget=partition_core_budget(partition, config, node),
                reason="first_idle_in_policy_order",
                candidates=candidates,
            )

    if not config.queue_all_when_no_idle:
        return CpuSelection(
            partition_arg="",
            selected_partition="",
            selected_node=None,
            core_budget=None,
            reason="no_idle_cpu_partition",
            candidates=candidates,
        )

    return CpuSelection(
        partition_arg=",".join(partition_order),
        selected_partition="",
        selected_node=None,
        core_budget=None,
        reason="no_idle_queue_all_policy_partitions",
        candidates=candidates,
    )


def partition_core_budget(
    partition: str, config: CpuSchedulingConfig, node: CpuNode | None = None
) -> int:
    if node and node.total_cpus > 0:
        return node.total_cpus
    normalized = normalize_partition_name(partition)
    return config.partition_core_overrides.get(normalized, config.default_partition_cores)


def build_cpu_sbatch_plan(
    selection: CpuSelection,
    *,
    job_name: str | None = None,
    account: str | None = None,
    time_limit: str | None = None,
    log_dir: str = "logs/slurm",
    submit_script: str | None = None,
    exclusive: bool = True,
) -> dict[str, Any]:
    """Build deterministic sbatch arguments for a CPU-only job."""

    if not selection.partition_arg:
        raise ValueError("CPU selection has no partition argument")
    args = ["--nodes", "1"]
    if exclusive:
        args.append("--exclusive")
    args.extend(["--partition", selection.partition_arg])
    if job_name:
        args.extend(["--job-name", job_name])
    if account:
        args.extend(["--account", account])
    if selection.core_budget is not None:
        args.extend(["--ntasks-per-node", str(selection.core_budget)])
        export_arg = f"ALL,FIIR_TOTAL_CPU_CORES={selection.core_budget}"
    else:
        export_arg = "ALL"
    args.extend(["--export", export_arg])
    if time_limit:
        args.extend(["--time", time_limit])
    args.extend(["--output", f"{log_dir}/%x_%j.log", "--error", f"{log_dir}/%x_%j.err"])
    command = ["sbatch", *args]
    if submit_script:
        command.append(submit_script)
    return {
        "sbatch_args": args,
        "sbatch_command": command,
        "sbatch_command_quoted": " ".join(shlex.quote(part) for part in command),
        "request": {
            "partition": selection.partition_arg,
            "node": selection.selected_node.name if selection.selected_node else None,
            "cpus": selection.core_budget,
            "exclusive": exclusive,
            "uses_all_currently_free_cpus": selection.core_budget is not None,
        },
    }


def plan_cpu_job(
    nodes: Sequence[CpuNode],
    config: CpuSchedulingConfig | None = None,
    **sbatch_kwargs: Any,
) -> dict[str, Any]:
    """Return a complete CPU scheduling plan."""

    config = config or CpuSchedulingConfig()
    selection = select_cpu_partition(nodes, config)
    if not selection.partition_arg:
        return {
            "kind": "cpu",
            "ready": False,
            "reason": selection.reason,
            "config": cpu_config_to_dict(config),
            "selection": selection.to_dict(),
            "sbatch": None,
        }
    sbatch = build_cpu_sbatch_plan(selection, exclusive=config.exclusive, **sbatch_kwargs)
    return {
        "kind": "cpu",
        "ready": True,
        "reason": selection.reason,
        "config": cpu_config_to_dict(config),
        "selection": selection.to_dict(),
        "sbatch": sbatch,
    }


def plan_slurm_job(
    *,
    kind: str,
    cpu_nodes: Sequence[CpuNode] | None = None,
    gpu_nodes: Sequence[GpuNode] | None = None,
    cpu_config: CpuSchedulingConfig | None = None,
    gpu_config: GpuSchedulingConfig | None = None,
    **sbatch_kwargs: Any,
) -> dict[str, Any]:
    """Plan either a CPU or GPU SLURM job through one access point."""

    if kind == "cpu":
        return plan_cpu_job(
            list(cpu_nodes) if cpu_nodes is not None else discover_cpu_nodes(),
            cpu_config or CpuSchedulingConfig(),
            **sbatch_kwargs,
        )
    if kind == "gpu":
        return {
            "kind": "gpu",
            **plan_gpu_job(
                list(gpu_nodes) if gpu_nodes is not None else discover_gpu_nodes(),
                gpu_config or GpuSchedulingConfig(),
                **sbatch_kwargs,
            ),
        }
    raise ValueError(f"unknown SLURM job kind: {kind}")


def cpu_config_to_dict(config: CpuSchedulingConfig) -> dict[str, Any]:
    return {
        "partition_order": list(config.partition_order),
        "expected_minutes": config.expected_minutes,
        "short_task_minutes": config.short_task_minutes,
        "test_partition": config.test_partition,
        "force_partition": config.force_partition,
        "default_partition_cores": config.default_partition_cores,
        "partition_core_overrides": dict(config.partition_core_overrides),
        "exclusive": config.exclusive,
        "queue_all_when_no_idle": config.queue_all_when_no_idle,
    }


def cpu_plan_shell_vars(plan: dict[str, Any]) -> dict[str, str]:
    """Return shell-friendly values for `submit_crystalformer_bulk.sh`."""

    selection = plan.get("selection") or {}
    sbatch = plan.get("sbatch") or {}
    request = sbatch.get("request") or {}
    return {
        "FIIR_SELECTED_PARTITION_ARG": str(selection.get("partition_arg") or ""),
        "FIIR_SELECTED_REASON": str(plan.get("reason") or ""),
        "FIIR_SELECTED_CORE_BUDGET": ""
        if request.get("cpus") is None
        else str(request.get("cpus")),
        "FIIR_EXPORT_ARG": _export_arg_from_sbatch(sbatch.get("sbatch_args") or []),
        "FIIR_NTASKS_PER_NODE": ""
        if request.get("cpus") is None
        else str(request.get("cpus")),
    }


def shell_assignments(values: dict[str, str]) -> str:
    return "\n".join(f"{key}={shlex.quote(value)}" for key, value in sorted(values.items()))


def normalize_partition_name(partition: str) -> str:
    return partition.strip().rstrip("*")


def normalize_partitions(partitions: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for partition in partitions:
        for item in str(partition).split(","):
            value = normalize_partition_name(item)
            if value and value not in normalized:
                normalized.append(value)
    return tuple(normalized)


def concurrency_warning(expected_minutes: int, short_task_minutes: int, concurrency: str) -> str:
    if concurrency.lower() in {"", "auto", "none"}:
        return ""
    if not concurrency.isdigit():
        return ""
    if expected_minutes > short_task_minutes and int(concurrency) > 8:
        return (
            "long_job_high_concurrency_may_oversubscribe_jax_threads:"
            f"FIIR_MAX_CONCURRENT_GENERATIONS={concurrency}; prefer 8 unless benchmarked"
        )
    return ""


def _cpu_candidates(nodes: Sequence[CpuNode], partition_order: Sequence[str]) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for partition in partition_order:
        idle_nodes = [node for node in nodes if partition in node.partitions and node.is_idle]
        candidates.append(
            {
                "partition": partition,
                "idle_node_count": len(idle_nodes),
                "best_idle_node": _best_idle_cpu_node(nodes, partition).to_dict()
                if idle_nodes
                else None,
            }
        )
    return tuple(candidates)


def _has_idle_cpu_node(nodes: Sequence[CpuNode], partition: str) -> bool:
    return _best_idle_cpu_node(nodes, partition) is not None


def _best_idle_cpu_node(nodes: Sequence[CpuNode], partition: str) -> CpuNode | None:
    eligible = [node for node in nodes if partition in node.partitions and node.is_idle]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda node: (-node.idle_cpus, -node.free_memory_mb, node.name),
    )[0]


def _export_arg_from_sbatch(args: Sequence[str]) -> str:
    for index, item in enumerate(args):
        if item == "--export" and index + 1 < len(args):
            return str(args[index + 1])
    return "ALL"


def _split_scontrol_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("NodeName=") and current:
            blocks.append("\n".join(current))
            current = [line]
        elif line.strip() or current:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _parse_key_values(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]*)", text)
    }


def _memory_to_mb(value: str | None) -> int:
    if not value:
        return 0
    text = str(value).strip()
    match = re.match(r"^(\d+)([KMGTP]?)", text, re.IGNORECASE)
    if not match:
        return 0
    number = int(match.group(1))
    unit = match.group(2).upper()
    if unit == "K":
        return max(1, number // 1024)
    if unit == "G":
        return number * 1024
    if unit == "T":
        return number * 1024 * 1024
    return number


def _positive_int(value: str | int | None) -> int:
    if value is None:
        return 0
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else 0


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(command, returncode=127, stdout="", stderr=str(exc))


__all__ = [
    "CPU_PARTITION_ORDER_DEFAULT",
    "DEFAULT_FLEXIBLE_QUEUE_CPUS",
    "DEFAULT_FLEXIBLE_QUEUE_GPUS",
    "DEFAULT_FLEXIBLE_QUEUE_MEMORY_MB",
    "DEFAULT_GPU_PRECISION_PROFILE",
    "DEFAULT_GPU_WEIGHTS",
    "FP64_GPU_WEIGHTS",
    "GPU_WEIGHT_PROFILES",
    "CpuNode",
    "CpuSchedulingConfig",
    "CpuSelection",
    "GpuNode",
    "GpuSchedulingConfig",
    "build_cpu_sbatch_plan",
    "build_gpu_sbatch_plan",
    "concurrency_warning",
    "cpu_config_to_dict",
    "cpu_plan_shell_vars",
    "discover_cpu_nodes",
    "discover_gpu_nodes",
    "gpu_config_to_dict",
    "gpu_weights_for_profile",
    "normalize_precision_profile",
    "normalize_partition_name",
    "normalize_partitions",
    "parse_gpu_weights",
    "parse_gres",
    "parse_partition_list",
    "parse_scontrol_cpu_nodes",
    "parse_scontrol_nodes",
    "parse_sinfo_cpu_nodes",
    "parse_sinfo_nodes",
    "plan_cpu_job",
    "plan_gpu_job",
    "plan_slurm_job",
    "effective_queue_mode",
    "flexible_queue_partitions",
    "queueable_gpu_nodes",
    "select_best_gpu_node",
    "select_cpu_partition",
    "shell_assignments",
]
