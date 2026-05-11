"""SLURM GPU node selection policy.

The policy is intentionally standard-library only. It inspects local SLURM
state, ranks nodes by currently available GPU TF32 compute capacity, and
returns a deterministic sbatch plan without submitting work unless a caller
explicitly does so. CPU and memory constraints are used as eligibility filters
and request sizing, not as default ranking signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


TF32_GPU_WEIGHTS: dict[str, int] = {
    # Relative dense TF32 throughput, normalized around RTX 4090 = 100.
    # These weights are used only for scheduling priority, not scientific
    # scoring. CPU and memory remain eligibility filters and request sizing.
    "h200": 599,
    "h800": 458,
    "rtx4090": 100,
    "h20": 90,
    "generic": 80,
    "amd80g": 70,
    "amd40g": 50,
    "intel80g": 40,
}

DEFAULT_GPU_WEIGHTS: dict[str, int] = dict(TF32_GPU_WEIGHTS)

CUDA_PARTITION_HINTS = ("h200", "h20", "h800", "gpu4090", "test")
NON_CUDA_PARTITION_HINTS = ("amd", "intel")
BLOCKED_STATE_MARKERS = ("DOWN", "DRAIN", "FAIL", "MAINT", "NO_RESP", "POWER", "RESV")


@dataclass(frozen=True)
class GpuNode:
    """A compact scheduling view of one SLURM node."""

    name: str
    partitions: tuple[str, ...]
    state: str
    total_cpus: int
    allocated_cpus: int
    total_memory_mb: int
    free_memory_mb: int
    gres: str
    gpu_type: str
    total_gpus: int
    allocated_gpus: int = 0
    features: tuple[str, ...] = ()

    @property
    def idle_cpus(self) -> int:
        return max(0, self.total_cpus - self.allocated_cpus)

    @property
    def free_gpus(self) -> int:
        return max(0, self.total_gpus - self.allocated_gpus)

    @property
    def is_fully_idle(self) -> bool:
        return (
            self.free_gpus == self.total_gpus
            and self.idle_cpus == self.total_cpus
            and _state_allows_new_work(self.state)
            and "IDLE" in self.state.upper()
        )

    @property
    def gpu_model_key(self) -> str:
        return infer_gpu_model_key(self.gpu_type, self.partitions)

    def gres_request(self, count: int | None = None) -> str:
        gpu_count = self.free_gpus if count is None else count
        if self.gpu_type:
            return f"gpu:{self.gpu_type}:{gpu_count}"
        return f"gpu:{gpu_count}"

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
            "gpu_type": self.gpu_type,
            "gpu_model_key": self.gpu_model_key,
            "total_gpus": self.total_gpus,
            "allocated_gpus": self.allocated_gpus,
            "free_gpus": self.free_gpus,
            "features": list(self.features),
            "is_fully_idle": self.is_fully_idle,
        }


@dataclass(frozen=True)
class GpuSchedulingConfig:
    """Configuration for selecting a GPU node."""

    accelerator: str = "cuda"
    allowed_partitions: tuple[str, ...] = ()
    min_gpus: int = 1
    min_cpus: int = 1
    min_memory_mb: int = 0
    layout: str = "single-task"
    exclusive_when_full_node: bool = True
    gpu_weights: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_GPU_WEIGHTS))


@dataclass(frozen=True)
class GpuSelection:
    """Selected node plus scored alternatives."""

    node: GpuNode
    partition: str
    score: float
    reason: str
    candidates: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_node": self.node.to_dict(),
            "selected_partition": self.partition,
            "score": self.score,
            "reason": self.reason,
            "candidates": list(self.candidates),
        }


def discover_gpu_nodes() -> list[GpuNode]:
    """Query SLURM and return GPU node state.

    `scontrol show node` is preferred because it exposes allocated GPU TRES.
    If it is unavailable, a conservative `sinfo` fallback only treats fully
    idle GPU nodes as having free GPUs.
    """

    scontrol_result = _run_command(["scontrol", "show", "node"])
    if scontrol_result.returncode == 0:
        nodes = parse_scontrol_nodes(scontrol_result.stdout)
        if nodes:
            return nodes

    sinfo_result = _run_command(["sinfo", "-N", "-h", "-o", "%N|%P|%T|%C|%m|%G|%f"])
    if sinfo_result.returncode == 0:
        nodes = parse_sinfo_nodes(sinfo_result.stdout)
        if nodes:
            return nodes

    details = (scontrol_result.stderr or sinfo_result.stderr or "").strip()
    raise RuntimeError(f"could not query SLURM GPU nodes: {details}")


def parse_scontrol_nodes(text: str) -> list[GpuNode]:
    """Parse `scontrol show node` text into `GpuNode` records."""

    nodes: list[GpuNode] = []
    for block in _split_scontrol_blocks(text):
        fields = _parse_key_values(block)
        name = fields.get("NodeName", "")
        if not name:
            continue
        gres = fields.get("Gres", "")
        gpu_type, gres_gpus = parse_gres(gres)
        cfg_tres = parse_tres(fields.get("CfgTRES", ""))
        alloc_tres = parse_tres(fields.get("AllocTRES", ""))
        total_gpus = _positive_int(cfg_tres.get("gres/gpu")) or gres_gpus
        if total_gpus <= 0:
            continue
        total_cpus = _optional_int(fields.get("CPUTot")) or _positive_int(cfg_tres.get("cpu"))
        allocated_cpus = _optional_int(fields.get("CPUAlloc")) or _positive_int(alloc_tres.get("cpu"))
        total_memory_mb = _memory_to_mb(fields.get("RealMemory", "")) or _memory_to_mb(
            cfg_tres.get("mem", "")
        )
        free_memory_mb = _memory_to_mb(fields.get("FreeMem", ""))
        if not free_memory_mb:
            allocated_mem = _memory_to_mb(fields.get("AllocMem", "")) or _memory_to_mb(
                alloc_tres.get("mem", "")
            )
            free_memory_mb = max(0, total_memory_mb - allocated_mem)
        partitions = _split_csv(fields.get("Partitions", ""))
        features = _split_csv(fields.get("ActiveFeatures", ""))
        nodes.append(
            GpuNode(
                name=name,
                partitions=partitions,
                state=fields.get("State", ""),
                total_cpus=total_cpus,
                allocated_cpus=allocated_cpus,
                total_memory_mb=total_memory_mb,
                free_memory_mb=free_memory_mb,
                gres=gres,
                gpu_type=gpu_type,
                total_gpus=total_gpus,
                allocated_gpus=_positive_int(alloc_tres.get("gres/gpu")),
                features=features,
            )
        )
    return sorted(nodes, key=lambda node: node.name)


def parse_sinfo_nodes(text: str) -> list[GpuNode]:
    """Parse conservative `sinfo -N` pipe-delimited output."""

    by_node: dict[str, dict[str, Any]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        name, partition, state, cpus, memory, gres = parts[:6]
        features = parts[6] if len(parts) > 6 else ""
        gpu_type, total_gpus = parse_gres(gres)
        if total_gpus <= 0:
            continue
        cpu_alloc, cpu_idle, _cpu_other, cpu_total = parse_sinfo_cpu_counts(cpus)
        existing = by_node.setdefault(
            name,
            {
                "partitions": [],
                "state": state,
                "total_cpus": cpu_total,
                "allocated_cpus": cpu_alloc,
                "idle_cpus": cpu_idle,
                "memory": _memory_to_mb(memory),
                "gres": gres,
                "gpu_type": gpu_type,
                "total_gpus": total_gpus,
                "features": [],
            },
        )
        if partition not in existing["partitions"]:
            existing["partitions"].append(partition)
        for feature in _split_csv(features):
            if feature not in existing["features"]:
                existing["features"].append(feature)

    nodes: list[GpuNode] = []
    for name, fields in by_node.items():
        state = str(fields["state"])
        is_idle = "IDLE" in state.upper() or state.lower().startswith("idle")
        allocated_gpus = 0 if is_idle else int(fields["total_gpus"])
        nodes.append(
            GpuNode(
                name=name,
                partitions=tuple(sorted(fields["partitions"])),
                state=state,
                total_cpus=int(fields["total_cpus"]),
                allocated_cpus=int(fields["allocated_cpus"]),
                total_memory_mb=int(fields["memory"]),
                free_memory_mb=int(fields["memory"]),
                gres=str(fields["gres"]),
                gpu_type=str(fields["gpu_type"]),
                total_gpus=int(fields["total_gpus"]),
                allocated_gpus=allocated_gpus,
                features=tuple(sorted(fields["features"])),
            )
        )
    return sorted(nodes, key=lambda node: node.name)


def select_best_gpu_node(
    nodes: Sequence[GpuNode], config: GpuSchedulingConfig | None = None
) -> GpuSelection | None:
    """Select the strongest currently usable GPU node."""

    config = config or GpuSchedulingConfig()
    scored: list[tuple[float, GpuNode, str]] = []
    for node in nodes:
        if not node_is_eligible(node, config):
            continue
        partition = select_partition(node, config.allowed_partitions)
        if not partition:
            continue
        scored.append((score_node(node, config), node, partition))
    if not scored:
        return None

    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1].free_gpus,
            item[2],
            item[1].name,
        )
    )
    score, node, partition = scored[0]
    candidates = tuple(
        {
            "node": candidate.to_dict(),
            "partition": candidate_partition,
            "score": candidate_score,
        }
        for candidate_score, candidate, candidate_partition in scored
    )
    return GpuSelection(
        node=node,
        partition=partition,
        score=score,
        reason="highest_tf32_gpu_compute_capacity",
        candidates=candidates,
    )


def node_is_eligible(node: GpuNode, config: GpuSchedulingConfig) -> bool:
    if not _state_allows_new_work(node.state):
        return False
    if node.free_gpus < config.min_gpus:
        return False
    if node.idle_cpus < config.min_cpus:
        return False
    if node.free_memory_mb < config.min_memory_mb:
        return False
    if config.allowed_partitions and not set(node.partitions).intersection(config.allowed_partitions):
        return False
    if config.accelerator == "cuda" and not node_is_cuda_compatible(node):
        return False
    return True


def node_is_cuda_compatible(node: GpuNode) -> bool:
    model = node.gpu_model_key
    if model in {"amd40g", "amd80g", "intel80g"}:
        return False
    partitions = tuple(partition.lower() for partition in node.partitions)
    if any(marker in partition for partition in partitions for marker in NON_CUDA_PARTITION_HINTS):
        return False
    if model in {"h200", "h800", "h20", "rtx4090"}:
        return True
    return any(any(hint in partition for hint in CUDA_PARTITION_HINTS) for partition in partitions)


def score_node(node: GpuNode, config: GpuSchedulingConfig) -> float:
    gpu_weight = config.gpu_weights.get(node.gpu_model_key, config.gpu_weights.get("generic", 80))
    return node.free_gpus * gpu_weight * 1_000_000


def build_sbatch_plan(
    selection: GpuSelection,
    *,
    job_name: str = "fiir-gpu-job",
    account: str | None = None,
    time_limit: str | None = None,
    log_dir: str = "logs/slurm",
    layout: str = "single-task",
    exclusive_when_full_node: bool = True,
    submit_script: str | None = None,
) -> dict[str, Any]:
    """Build deterministic sbatch args that request all free GPUs/CPUs."""

    node = selection.node
    gpu_count = node.free_gpus
    cpu_count = node.idle_cpus
    if gpu_count < 1 or cpu_count < 1:
        raise ValueError("selected node has no free GPU or CPU resources")
    args = [
        "--nodes",
        "1",
        "--partition",
        selection.partition,
        "--nodelist",
        node.name,
        "--job-name",
        job_name,
        "--gres",
        node.gres_request(gpu_count),
    ]
    if account:
        args.extend(["--account", account])
    if time_limit:
        args.extend(["--time", time_limit])
    exclusive = node.is_fully_idle and exclusive_when_full_node
    if exclusive:
        args.append("--exclusive")
    if layout == "one-task-per-gpu":
        cpus_per_task = max(1, cpu_count // gpu_count)
        args.extend(["--ntasks-per-node", str(gpu_count), "--cpus-per-task", str(cpus_per_task)])
        unassigned_cpus = cpu_count - (cpus_per_task * gpu_count)
    elif layout == "single-task":
        cpus_per_task = cpu_count
        unassigned_cpus = 0
        args.extend(["--ntasks", "1", "--cpus-per-task", str(cpu_count)])
    else:
        raise ValueError(f"unknown GPU task layout: {layout}")

    env_items = {
        "FIIR_GPU_NODE": node.name,
        "FIIR_GPU_PARTITION": selection.partition,
        "FIIR_TOTAL_GPUS": str(gpu_count),
        "FIIR_TOTAL_CPU_CORES": str(cpu_count),
        "FIIR_GPU_MODEL": node.gpu_model_key,
        "FIIR_GPU_GRES": node.gres_request(gpu_count),
    }
    args.extend(["--export", "ALL," + ",".join(f"{key}={value}" for key, value in env_items.items())])
    args.extend(["--output", f"{log_dir}/%x_%j.log", "--error", f"{log_dir}/%x_%j.err"])
    command = ["sbatch", *args]
    if submit_script:
        command.append(submit_script)
    return {
        "sbatch_args": args,
        "sbatch_command": command,
        "sbatch_command_quoted": " ".join(shlex.quote(part) for part in command),
        "request": {
            "node": node.name,
            "partition": selection.partition,
            "gpus": gpu_count,
            "cpus": cpu_count,
            "gres": node.gres_request(gpu_count),
            "layout": layout,
            "cpus_per_task": cpus_per_task,
            "unassigned_cpu_cores": unassigned_cpus,
            "exclusive": exclusive,
            "uses_all_currently_free_gpus": True,
            "uses_all_currently_free_cpus": layout == "single-task" or unassigned_cpus == 0,
        },
    }


def plan_gpu_job(
    nodes: Sequence[GpuNode],
    config: GpuSchedulingConfig | None = None,
    **sbatch_kwargs: Any,
) -> dict[str, Any]:
    """Return a complete scheduler plan from pre-parsed nodes."""

    config = config or GpuSchedulingConfig()
    selection = select_best_gpu_node(nodes, config)
    if selection is None:
        return {
            "ready": False,
            "reason": "no_eligible_gpu_node_with_free_resources",
            "config": config_to_dict(config),
            "selection": None,
            "sbatch": None,
        }
    sbatch = build_sbatch_plan(
        selection,
        layout=config.layout,
        exclusive_when_full_node=config.exclusive_when_full_node,
        **sbatch_kwargs,
    )
    return {
        "ready": True,
        "reason": selection.reason,
        "config": config_to_dict(config),
        "selection": selection.to_dict(),
        "sbatch": sbatch,
    }


def config_to_dict(config: GpuSchedulingConfig) -> dict[str, Any]:
    return {
        "accelerator": config.accelerator,
        "allowed_partitions": list(config.allowed_partitions),
        "min_gpus": config.min_gpus,
        "min_cpus": config.min_cpus,
        "min_memory_mb": config.min_memory_mb,
        "layout": config.layout,
        "exclusive_when_full_node": config.exclusive_when_full_node,
        "gpu_weights": dict(config.gpu_weights),
    }


def select_partition(node: GpuNode, allowed_partitions: Sequence[str] = ()) -> str:
    partitions = [partition for partition in node.partitions if partition and partition != "(null)"]
    if allowed_partitions:
        allowed = set(allowed_partitions)
        partitions = [partition for partition in partitions if partition in allowed]
    if not partitions:
        return ""
    return sorted(partitions, key=lambda item: (_partition_rank(item), item))[0]


def infer_gpu_model_key(gpu_type: str, partitions: Sequence[str]) -> str:
    lower_type = gpu_type.lower()
    lower_partitions = tuple(partition.lower() for partition in partitions)
    joined = " ".join((lower_type, *lower_partitions))
    if "h200" in joined:
        return "h200"
    if "h800" in joined:
        return "h800"
    if "h20" in joined:
        return "h20"
    if "4090" in joined:
        return "rtx4090"
    if "amd" in joined and "80" in joined:
        return "amd80g"
    if "amd" in joined and "40" in joined:
        return "amd40g"
    if "intel" in joined:
        return "intel80g"
    return "generic"


def parse_gres(value: str) -> tuple[str, int]:
    if not value or value == "(null)" or not value.startswith("gpu"):
        return "", 0
    first = value.split(",", 1)[0].split("(", 1)[0]
    parts = first.split(":")
    if len(parts) == 2 and parts[1].isdigit():
        return "", int(parts[1])
    if len(parts) >= 3 and parts[-1].isdigit():
        return parts[1], int(parts[-1])
    match = re.search(r"(\d+)$", first)
    return (parts[1] if len(parts) > 1 else "", int(match.group(1)) if match else 0)


def parse_tres(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not value:
        return result
    for part in value.split(","):
        if "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        result[key] = raw_value
    return result


def parse_sinfo_cpu_counts(value: str) -> tuple[int, int, int, int]:
    pieces = value.split("/")
    if len(pieces) != 4:
        return 0, 0, 0, 0
    return tuple(_positive_int(piece) for piece in pieces)  # type: ignore[return-value]


def parse_partition_list(values: Iterable[str]) -> tuple[str, ...]:
    partitions: list[str] = []
    for value in values:
        for item in value.split(","):
            normalized = item.strip().rstrip("*")
            if normalized and normalized not in partitions:
                partitions.append(normalized)
    return tuple(partitions)


def parse_gpu_weights(values: Iterable[str]) -> dict[str, int]:
    weights = dict(DEFAULT_GPU_WEIGHTS)
    for value in values:
        if "=" not in value:
            raise ValueError(f"GPU weight must be name=value: {value}")
        name, raw_weight = value.split("=", 1)
        weights[name.strip().lower()] = int(raw_weight)
    return weights


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
    return {match.group(1): match.group(2) for match in re.finditer(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]*)", text)}


def _split_csv(value: str) -> tuple[str, ...]:
    if not value or value == "(null)":
        return ()
    return tuple(item.strip().rstrip("*") for item in value.split(",") if item.strip())


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


def _optional_int(value: str | None) -> int:
    if value is None:
        return 0
    return _positive_int(value)


def _positive_int(value: str | int | None) -> int:
    if value is None:
        return 0
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else 0


def _state_allows_new_work(state: str) -> bool:
    upper = state.upper()
    if any(marker in upper for marker in BLOCKED_STATE_MARKERS):
        return False
    return "IDLE" in upper or "MIX" in upper


def _partition_rank(partition: str) -> int:
    lower = partition.lower()
    ranks = (
        ("h200", 0),
        ("h20", 1),
        ("h800", 2),
        ("gpu4090_8", 3),
        ("gpu4090_128", 4),
        ("gpu4090", 5),
        ("test", 6),
        ("amdgpu80g", 7),
        ("amdgpu40g", 8),
        ("intelgpu80g", 9),
    )
    for marker, rank in ranks:
        if marker in lower:
            return rank
    if "llm" in lower:
        return 50
    return 20


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(command, returncode=127, stdout="", stderr=str(exc))
