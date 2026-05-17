from __future__ import annotations

import json
from pathlib import Path

from fiir_crystal.slurm_gpu_policy import (
    DEFAULT_GPU_WEIGHTS,
    FP64_GPU_WEIGHTS,
    GpuSchedulingConfig,
    build_sbatch_plan,
    parse_gpu_weights,
    parse_scontrol_nodes,
    parse_slurm_time_limit_minutes,
    plan_gpu_job,
    score_node,
    select_best_gpu_node,
)
from scripts.slurm.plan_gpu_job import main as plan_gpu_main


SCONTROL_SAMPLE = """
NodeName=gpu005 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.18
   Gres=gpu:4
   State=IDLE ThreadsPerCore=2
   Partitions=amdgpu40g,gpu40gllm
   RealMemory=512000 AllocMem=0 FreeMem=477951
   CfgTRES=cpu=64,mem=500G,billing=64,gres/gpu=4
   AllocTRES=

NodeName=gpu40902 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=0 CPUEfctv=32 CPUTot=32 CPULoad=0.02
   Gres=gpu:rtx4090:8
   State=IDLE ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=500000 AllocMem=0 FreeMem=494715
   CfgTRES=cpu=32,mem=500000M,billing=32,gres/gpu=8
   AllocTRES=

NodeName=gpuh202 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=32 CPUEfctv=192 CPUTot=192 CPULoad=2.72
   Gres=gpu:H20:8
   State=MIXED ThreadsPerCore=2
   Partitions=h20,h20llm
   RealMemory=2000000 AllocMem=0 FreeMem=1522117
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=32,gres/gpu=8

NodeName=gpuh2002 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=64 CPUEfctv=192 CPUTot=192 CPULoad=8.00
   Gres=gpu:8
   State=MIXED ThreadsPerCore=2
   Partitions=h200
   RealMemory=2000000 AllocMem=0 FreeMem=1500000
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=64,gres/gpu=2
"""


def test_parse_scontrol_nodes_tracks_free_gpu_cpu_resources() -> None:
    nodes = parse_scontrol_nodes(SCONTROL_SAMPLE)
    by_name = {node.name: node for node in nodes}

    assert by_name["gpu40902"].gpu_type == "rtx4090"
    assert by_name["gpu40902"].free_gpus == 8
    assert by_name["gpu40902"].idle_cpus == 32
    assert by_name["gpu40902"].is_fully_idle is True

    assert by_name["gpuh202"].gpu_model_key == "h20"
    assert by_name["gpuh202"].free_gpus == 0
    assert by_name["gpuh202"].idle_cpus == 160

    assert by_name["gpuh2002"].gpu_model_key == "h200"
    assert by_name["gpuh2002"].free_gpus == 6
    assert by_name["gpuh2002"].idle_cpus == 128


def test_cuda_policy_ignores_amd_and_selects_highest_tf32_gpu_compute() -> None:
    nodes = parse_scontrol_nodes(SCONTROL_SAMPLE)
    selection = select_best_gpu_node(nodes, GpuSchedulingConfig(accelerator="cuda"))

    assert selection is not None
    assert selection.node.name == "gpuh2002"
    assert selection.partition == "h200"
    assert selection.reason == "highest_tf32_gpu_compute_capacity"
    candidate_names = [item["node"]["name"] for item in selection.candidates]
    assert "gpu005" not in candidate_names
    assert "gpuh202" not in candidate_names
    assert candidate_names[:2] == ["gpuh2002", "gpu40902"]


def test_gpu_score_uses_only_available_gpu_count_times_tf32_weight() -> None:
    node = parse_scontrol_nodes(SCONTROL_SAMPLE)[0]
    assert score_node(node, GpuSchedulingConfig()) == (
        node.free_gpus * DEFAULT_GPU_WEIGHTS[node.gpu_model_key] * 1_000_000
    )


def test_fp64_profile_can_choose_fewer_stronger_double_precision_gpus() -> None:
    text = """
NodeName=gpu40902 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=0 CPUEfctv=32 CPUTot=32 CPULoad=0.02
   Gres=gpu:rtx4090:8
   State=IDLE ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=500000 AllocMem=0 FreeMem=494715
   CfgTRES=cpu=32,mem=500000M,billing=32,gres/gpu=8
   AllocTRES=

NodeName=gpuh2002 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=160 CPUEfctv=192 CPUTot=192 CPULoad=8.00
   Gres=gpu:8
   State=MIXED ThreadsPerCore=2
   Partitions=h200
   RealMemory=2000000 AllocMem=0 FreeMem=1500000
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=160,gres/gpu=7
"""
    nodes = parse_scontrol_nodes(text)

    tf32_selection = select_best_gpu_node(nodes, GpuSchedulingConfig(precision_profile="tf32"))
    fp64_selection = select_best_gpu_node(nodes, GpuSchedulingConfig(precision_profile="fp64"))

    assert tf32_selection is not None
    assert fp64_selection is not None
    assert tf32_selection.node.name == "gpu40902"
    assert tf32_selection.score == 8 * DEFAULT_GPU_WEIGHTS["rtx4090"] * 1_000_000
    assert tf32_selection.reason == "highest_tf32_gpu_compute_capacity"
    assert fp64_selection.node.name == "gpuh2002"
    assert fp64_selection.score == 1 * FP64_GPU_WEIGHTS["h200"] * 1_000_000
    assert fp64_selection.reason == "highest_fp64_gpu_compute_capacity"


def test_gpu_weight_overrides_apply_after_precision_profile() -> None:
    weights = parse_gpu_weights(["rtx4090=5000"], precision_profile="fp64")

    assert weights["h200"] == FP64_GPU_WEIGHTS["h200"]
    assert weights["rtx4090"] == 5000


def test_cpu_and_memory_do_not_change_default_gpu_ranking() -> None:
    text = """
NodeName=gpu001 Arch=x86_64 CoresPerSocket=4
   CPUAlloc=0 CPUEfctv=8 CPUTot=8 CPULoad=0.01
   Gres=gpu:rtx4090:4
   State=IDLE ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=8000 AllocMem=0 FreeMem=4000
   CfgTRES=cpu=8,mem=8000M,billing=8,gres/gpu=4
   AllocTRES=

NodeName=gpu999 Arch=x86_64 CoresPerSocket=64
   CPUAlloc=0 CPUEfctv=128 CPUTot=128 CPULoad=0.01
   Gres=gpu:rtx4090:4
   State=IDLE ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=1000000 AllocMem=0 FreeMem=900000
   CfgTRES=cpu=128,mem=1000000M,billing=128,gres/gpu=4
   AllocTRES=
"""
    selection = select_best_gpu_node(parse_scontrol_nodes(text), GpuSchedulingConfig())

    assert selection is not None
    assert selection.node.name == "gpu001"
    assert selection.score == 4 * DEFAULT_GPU_WEIGHTS["rtx4090"] * 1_000_000


def test_sbatch_plan_requests_all_currently_free_resources() -> None:
    nodes = parse_scontrol_nodes(SCONTROL_SAMPLE)
    selection = select_best_gpu_node(nodes, GpuSchedulingConfig(accelerator="cuda"))
    assert selection is not None

    plan = build_sbatch_plan(
        selection,
        job_name="fiir-mlip-gpu",
        time_limit="00:30:00",
        log_dir="logs/slurm",
        submit_script="scripts/slurm/run_mlip_gpu_smoke.slurm",
    )

    request = plan["request"]
    assert request["node"] is None
    assert request["reference_node"] == "gpuh2002"
    assert request["gpus"] == 6
    assert request["cpus"] == 128
    assert request["memory_mb"] == 1_500_000
    assert request["gres"] == "gpu:6"
    assert request["exclusive"] is False
    assert request["uses_all_currently_free_gpus"] is True
    assert request["uses_all_currently_free_cpus"] is True
    assert "--nodelist" not in plan["sbatch_args"]
    assert "--cpus-per-task" in plan["sbatch_args"]
    assert "128" in plan["sbatch_args"]
    assert "--mem" in plan["sbatch_args"]
    assert "1500000M" in plan["sbatch_args"]
    assert "FIIR_TOTAL_GPUS=6" in " ".join(plan["sbatch_args"])


def test_partition_filter_can_choose_idle_4090_node() -> None:
    nodes = parse_scontrol_nodes(SCONTROL_SAMPLE)
    selection = select_best_gpu_node(
        nodes,
        GpuSchedulingConfig(accelerator="cuda", allowed_partitions=("gpu4090_8",)),
    )

    assert selection is not None
    assert selection.node.name == "gpu40902"
    plan = build_sbatch_plan(selection)
    assert plan["request"]["gpus"] == 8
    assert plan["request"]["cpus"] == 32
    assert plan["request"]["exclusive"] is False
    assert "--exclusive" not in plan["sbatch_args"]
    assert "--nodelist" not in plan["sbatch_args"]
    assert "gpu:rtx4090:8" in plan["sbatch_args"]


def test_default_gpu_policy_blocks_bare_4090_but_keeps_named_4090_partitions() -> None:
    text = """
NodeName=gpu4090bare Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.01
   Gres=gpu:rtx4090:8
   State=IDLE ThreadsPerCore=1
   Partitions=gpu4090
   RealMemory=500000 AllocMem=0 FreeMem=490000
   CfgTRES=cpu=64,mem=500000M,billing=64,gres/gpu=8
   AllocTRES=

NodeName=gpu4090named Arch=x86_64 CoresPerSocket=16
   CPUAlloc=0 CPUEfctv=32 CPUTot=32 CPULoad=0.01
   Gres=gpu:rtx4090:4
   State=IDLE ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=500000 AllocMem=0 FreeMem=490000
   CfgTRES=cpu=32,mem=500000M,billing=32,gres/gpu=4
   AllocTRES=
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(accelerator="cuda", time_limit_minutes=120),
        time_limit="02:00:00",
    )

    assert plan["ready"] is True
    assert plan["config"]["blocked_partitions"] == ["gpu4090"]
    assert plan["selection"]["selected_node"]["name"] == "gpu4090named"
    assert plan["selection"]["selected_partition"] == "gpu4090_8"
    candidate_names = [item["node"]["name"] for item in plan["selection"]["candidates"]]
    assert "gpu4090bare" not in candidate_names
    assert plan["sbatch"]["request"]["partition"] == "gpu4090_8"


def test_pinned_memory_request_is_capped_at_real_memory() -> None:
    text = """
NodeName=gpu40903 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=128 CPUTot=128 CPULoad=0.86
   Gres=gpu:rtx4090:8
   State=IDLE ThreadsPerCore=2
   Partitions=gpu4090_128
   RealMemory=1000000 AllocMem=0 FreeMem=1018262
   CfgTRES=cpu=128,mem=1000000M,billing=128,gres/gpu=8
   AllocTRES=
"""
    selection = select_best_gpu_node(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(accelerator="cuda", allowed_partitions=("gpu4090_128",)),
    )
    assert selection is not None

    plan = build_sbatch_plan(selection)

    assert plan["request"]["memory_mb"] == 1_000_000
    assert "--mem" in plan["sbatch_args"]
    assert "1000000M" in plan["sbatch_args"]


def test_test_gpu_partition_has_time_guard() -> None:
    text = """
NodeName=test001 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.01
   Gres=gpu:rtx4090:2
   State=IDLE ThreadsPerCore=1
   Partitions=test
   RealMemory=256000 AllocMem=0 FreeMem=240000
   CfgTRES=cpu=64,mem=256000M,billing=64,gres/gpu=2
   AllocTRES=
"""
    nodes = parse_scontrol_nodes(text)

    missing_time = plan_gpu_job(nodes, GpuSchedulingConfig(accelerator="cuda"))
    assert missing_time["ready"] is False

    too_long = plan_gpu_job(
        nodes,
        GpuSchedulingConfig(accelerator="cuda", time_limit_minutes=31),
        time_limit="00:31:00",
    )
    assert too_long["ready"] is False

    short = plan_gpu_job(
        nodes,
        GpuSchedulingConfig(accelerator="cuda", time_limit_minutes=30),
        time_limit="00:30:00",
    )
    assert short["ready"] is True
    assert short["selection"]["selected_partition"] == "test"
    assert short["config"]["test_partition_max_minutes"] == 30
    assert "--time" in short["sbatch"]["sbatch_args"]
    assert "00:30:00" in short["sbatch"]["sbatch_args"]


def test_test_gpu_partition_is_fallback_even_when_it_has_higher_raw_score() -> None:
    text = """
NodeName=test001 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.01
   Gres=gpu:rtx4090:2
   State=IDLE ThreadsPerCore=1
   Partitions=test
   RealMemory=256000 AllocMem=0 FreeMem=240000
   CfgTRES=cpu=64,mem=256000M,billing=64,gres/gpu=2
   AllocTRES=

NodeName=gpuh20small Arch=x86_64 CoresPerSocket=16
   CPUAlloc=28 CPUEfctv=32 CPUTot=32 CPULoad=8.00
   Gres=gpu:H20:8
   State=MIXED ThreadsPerCore=1
   Partitions=h20
   RealMemory=500000 AllocMem=0 FreeMem=100000
   CfgTRES=cpu=32,mem=500000M,billing=32,gres/gpu=8
   AllocTRES=cpu=28,gres/gpu=7
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(accelerator="cuda", time_limit_minutes=30),
        time_limit="00:30:00",
    )

    assert plan["ready"] is True
    assert plan["reason"] == "highest_tf32_gpu_compute_capacity"
    assert plan["selection"]["selected_node"]["name"] == "gpuh20small"
    assert plan["selection"]["selected_partition"] == "h20"
    candidate_names = [item["node"]["name"] for item in plan["selection"]["candidates"]]
    assert candidate_names == ["gpuh20small"]


def test_test_gpu_partition_is_used_for_short_job_when_no_non_test_gpu_is_free() -> None:
    text = """
NodeName=test001 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.01
   Gres=gpu:rtx4090:2
   State=IDLE ThreadsPerCore=1
   Partitions=test
   RealMemory=256000 AllocMem=0 FreeMem=240000
   CfgTRES=cpu=64,mem=256000M,billing=64,gres/gpu=2
   AllocTRES=

NodeName=gpu40902 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=32 CPUEfctv=32 CPUTot=32 CPULoad=2.00
   Gres=gpu:rtx4090:8
   State=ALLOCATED ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=500000 AllocMem=0 FreeMem=494715
   CfgTRES=cpu=32,mem=500000M,billing=32,gres/gpu=8
   AllocTRES=cpu=32,gres/gpu=8
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(accelerator="cuda", time_limit_minutes=30),
        time_limit="00:30:00",
    )

    assert plan["ready"] is True
    assert plan["reason"] == "short_gpu_job_test_fallback_after_no_non_test_gpu_free"
    assert plan["selection"]["selected_node"]["name"] == "test001"
    assert plan["selection"]["selected_partition"] == "test"


def test_long_gpu_job_auto_prefers_best_free_gpu_node_before_flexible_queue() -> None:
    plan = plan_gpu_job(
        parse_scontrol_nodes(SCONTROL_SAMPLE),
        GpuSchedulingConfig(accelerator="cuda", time_limit_minutes=240),
        time_limit="04:00:00",
    )

    assert plan["ready"] is True
    assert plan["reason"] == "highest_tf32_gpu_compute_capacity"
    assert plan["config"]["effective_queue_mode"] == "partition"
    assert plan["selection"]["selected_node"]["name"] == "gpuh2002"
    assert plan["selection"]["selected_partition"] == "h200"
    assert plan["sbatch"]["request"]["node"] is None
    assert plan["sbatch"]["request"]["reference_node"] == "gpuh2002"
    assert plan["sbatch"]["request"]["partition"] == "h200"
    assert "--nodelist" not in plan["sbatch"]["sbatch_args"]


def test_auto_batch_reserved_nodes_claim_free_nodes_then_queue_flexibly() -> None:
    text = """
NodeName=gpuh2001 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=120 CPUEfctv=192 CPUTot=192 CPULoad=64.00
   Gres=gpu:8
   State=MIXED ThreadsPerCore=2
   Partitions=h200
   RealMemory=2000000 AllocMem=0 FreeMem=1500000
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=120

NodeName=gpuh2002 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=120 CPUEfctv=192 CPUTot=192 CPULoad=64.00
   Gres=gpu:8
   State=MIXED ThreadsPerCore=2
   Partitions=h200
   RealMemory=2000000 AllocMem=0 FreeMem=1200000
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=120
"""
    nodes = parse_scontrol_nodes(text)
    base = {
        "accelerator": "cuda",
        "min_gpus": 8,
        "min_cpus": 32,
        "queue_min_gpus": 8,
        "queue_min_cpus": 32,
        "time_limit_minutes": 120,
    }

    first = plan_gpu_job(nodes, GpuSchedulingConfig(**base), time_limit="02:00:00")
    second = plan_gpu_job(
        nodes,
        GpuSchedulingConfig(**base, reserved_nodes=("gpuh2001",)),
        time_limit="02:00:00",
    )
    queued = plan_gpu_job(
        nodes,
        GpuSchedulingConfig(**base, reserved_nodes=("gpuh2001", "gpuh2002")),
        time_limit="02:00:00",
    )

    assert first["config"]["effective_queue_mode"] == "partition"
    assert first["selection"]["selected_node"]["name"] == "gpuh2001"
    assert second["config"]["reserved_nodes"] == ["gpuh2001"]
    assert second["config"]["effective_queue_mode"] == "partition"
    assert second["selection"]["selected_node"]["name"] == "gpuh2002"
    assert queued["config"]["reserved_nodes"] == ["gpuh2001", "gpuh2002"]
    assert queued["config"]["effective_queue_mode"] == "flexible"
    assert queued["selection"]["selected_node"] is None
    assert queued["selection"]["candidate_partitions"] == ["h200"]
    assert queued["sbatch"]["request"]["node"] is None
    assert queued["sbatch"]["request"]["memory_mb"] == 256_000
    assert "--nodelist" not in queued["sbatch"]["sbatch_args"]


def test_long_gpu_job_auto_falls_back_to_flexible_queue_when_no_free_long_gpu() -> None:
    text = """
NodeName=gpu40902 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=32 CPUEfctv=32 CPUTot=32 CPULoad=2.00
   Gres=gpu:rtx4090:8
   State=ALLOCATED ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=500000 AllocMem=0 FreeMem=494715
   CfgTRES=cpu=32,mem=500000M,billing=32,gres/gpu=8
   AllocTRES=cpu=32,gres/gpu=8

NodeName=gpuh202 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=192 CPUEfctv=192 CPUTot=192 CPULoad=2.72
   Gres=gpu:H20:8
   State=ALLOCATED ThreadsPerCore=2
   Partitions=h20,h20llm
   RealMemory=2000000 AllocMem=0 FreeMem=1522117
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=192,gres/gpu=8

NodeName=gpuh2002 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=192 CPUEfctv=192 CPUTot=192 CPULoad=8.00
   Gres=gpu:8
   State=ALLOCATED ThreadsPerCore=2
   Partitions=h200
   RealMemory=2000000 AllocMem=0 FreeMem=1500000
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=192,gres/gpu=8
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(accelerator="cuda", time_limit_minutes=240),
        time_limit="04:00:00",
    )

    assert plan["ready"] is True
    assert plan["reason"] == "no_free_gpu_resources_flexible_queue_across_candidate_partitions"
    assert plan["config"]["effective_queue_mode"] == "flexible"
    assert plan["selection"]["selected_node"] is None
    assert plan["selection"]["candidate_partitions"] == ["h200", "h20", "h20llm", "gpu4090_8"]
    assert plan["sbatch"]["request"]["queue_mode"] == "flexible"
    assert plan["sbatch"]["request"]["node"] is None
    assert plan["sbatch"]["request"]["partition"] == "h200,h20,h20llm,gpu4090_8"
    assert plan["sbatch"]["request"]["gpus"] == 8
    assert plan["sbatch"]["request"]["cpus"] == 32
    assert plan["sbatch"]["request"]["memory_mb"] == 256_000
    assert "--nodelist" not in plan["sbatch"]["sbatch_args"]
    assert "--partition" in plan["sbatch"]["sbatch_args"]
    assert "h200,h20,h20llm,gpu4090_8" in plan["sbatch"]["sbatch_args"]
    assert "--mem" in plan["sbatch"]["sbatch_args"]
    assert "256000M" in plan["sbatch"]["sbatch_args"]
    assert "FIIR_GPU_QUEUE_MODE=flexible" in " ".join(plan["sbatch"]["sbatch_args"])


def test_auto_fallback_uses_32_cpu_queue_shape_after_full_cpu_pinned_filter_fails() -> None:
    text = """
NodeName=gpu40902 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=32 CPUEfctv=32 CPUTot=32 CPULoad=2.00
   Gres=gpu:rtx4090:8
   State=ALLOCATED ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=500000 AllocMem=0 FreeMem=494715
   CfgTRES=cpu=32,mem=500000M,billing=32,gres/gpu=8
   AllocTRES=cpu=32,gres/gpu=8

NodeName=gpuh202 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=192 CPUEfctv=192 CPUTot=192 CPULoad=2.72
   Gres=gpu:H20:8
   State=ALLOCATED ThreadsPerCore=2
   Partitions=h20,h20llm
   RealMemory=2000000 AllocMem=0 FreeMem=1522117
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=cpu=192,gres/gpu=8
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(
            accelerator="cuda",
            min_gpus=8,
            min_cpus=192,
            queue_min_gpus=8,
            queue_min_cpus=32,
            time_limit_minutes=240,
        ),
        time_limit="04:00:00",
    )

    assert plan["ready"] is True
    assert plan["config"]["min_cpus"] == 192
    assert plan["config"]["queue_min_cpus"] == 32
    assert plan["config"]["queue_memory_mb"] == 256_000
    assert plan["config"]["effective_queue_mode"] == "flexible"
    assert plan["selection"]["candidate_partitions"] == ["h20", "h20llm", "gpu4090_8"]
    assert plan["sbatch"]["request"]["gpus"] == 8
    assert plan["sbatch"]["request"]["cpus"] == 32
    assert plan["sbatch"]["request"]["memory_mb"] == 256_000
    assert plan["sbatch"]["request"]["partition"] == "h20,h20llm,gpu4090_8"


def test_h20llm_partition_uses_h20_cuda_parameters() -> None:
    text = """
NodeName=gpuh20llm1 Arch=x86_64 CoresPerSocket=48
   CPUAlloc=0 CPUEfctv=192 CPUTot=192 CPULoad=0.01
   Gres=gpu:H20:8
   State=IDLE ThreadsPerCore=2
   Partitions=h20llm
   RealMemory=2000000 AllocMem=0 FreeMem=1900000
   CfgTRES=cpu=192,mem=2000000M,billing=192,gres/gpu=8
   AllocTRES=
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(
            accelerator="cuda",
            allowed_partitions=("h20llm",),
            time_limit_minutes=240,
        ),
        time_limit="04:00:00",
    )

    assert plan["ready"] is True
    assert plan["config"]["effective_queue_mode"] == "partition"
    assert plan["selection"]["selected_node"]["gpu_model_key"] == "h20"
    assert plan["selection"]["selected_partition"] == "h20llm"
    assert plan["sbatch"]["request"]["gres"] == "gpu:H20:8"
    assert "gpu:H20:8" in plan["sbatch"]["sbatch_args"]


def test_explicit_flexible_gpu_queue_filters_test_by_time_guard() -> None:
    text = """
NodeName=test001 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.01
   Gres=gpu:rtx4090:2
   State=IDLE ThreadsPerCore=1
   Partitions=test
   RealMemory=256000 AllocMem=0 FreeMem=240000
   CfgTRES=cpu=64,mem=256000M,billing=64,gres/gpu=2
   AllocTRES=

NodeName=gpu40902 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=32 CPUEfctv=32 CPUTot=32 CPULoad=2.00
   Gres=gpu:rtx4090:8
   State=ALLOCATED ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=512000 AllocMem=0 FreeMem=494715
   CfgTRES=cpu=32,mem=512000M,billing=32,gres/gpu=8
   AllocTRES=cpu=32,gres/gpu=8
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(
            accelerator="cuda",
            allowed_partitions=("gpu4090_8", "test"),
            queue_mode="flexible",
            time_limit_minutes=240,
        ),
        time_limit="04:00:00",
    )

    assert plan["ready"] is True
    assert plan["selection"]["candidate_partitions"] == ["gpu4090_8"]
    assert plan["sbatch"]["request"]["partition"] == "gpu4090_8"
    assert "--nodelist" not in plan["sbatch"]["sbatch_args"]


def test_flexible_gpu_queue_excludes_test_when_normal_gpu_partition_is_queueable() -> None:
    text = """
NodeName=test001 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.01
   Gres=gpu:rtx4090:2
   State=IDLE ThreadsPerCore=1
   Partitions=test
   RealMemory=256000 AllocMem=0 FreeMem=240000
   CfgTRES=cpu=64,mem=256000M,billing=64,gres/gpu=2
   AllocTRES=

NodeName=gpu40902 Arch=x86_64 CoresPerSocket=16
   CPUAlloc=32 CPUEfctv=32 CPUTot=32 CPULoad=2.00
   Gres=gpu:rtx4090:8
   State=ALLOCATED ThreadsPerCore=1
   Partitions=gpu4090_8
   RealMemory=512000 AllocMem=0 FreeMem=494715
   CfgTRES=cpu=32,mem=512000M,billing=32,gres/gpu=8
   AllocTRES=cpu=32,gres/gpu=8
"""
    plan = plan_gpu_job(
        parse_scontrol_nodes(text),
        GpuSchedulingConfig(
            accelerator="cuda",
            allowed_partitions=("gpu4090_8", "test"),
            queue_mode="flexible",
            queue_min_gpus=2,
            time_limit_minutes=30,
        ),
        time_limit="00:30:00",
    )

    assert plan["ready"] is True
    assert plan["selection"]["candidate_partitions"] == ["gpu4090_8"]
    assert plan["sbatch"]["request"]["partition"] == "gpu4090_8"
    assert "test" not in plan["sbatch"]["request"]["candidate_partitions"]


def test_parse_slurm_time_limit_minutes_ceilings_seconds() -> None:
    assert parse_slurm_time_limit_minutes(None) is None
    assert parse_slurm_time_limit_minutes("") is None
    assert parse_slurm_time_limit_minutes("30") == 30
    assert parse_slurm_time_limit_minutes("29:59") == 30
    assert parse_slurm_time_limit_minutes("00:30:01") == 31
    assert parse_slurm_time_limit_minutes("1-00:00:00") == 24 * 60


def test_no_cuda_candidate_returns_not_ready_for_amd_only() -> None:
    nodes = [node for node in parse_scontrol_nodes(SCONTROL_SAMPLE) if node.name == "gpu005"]
    plan = plan_gpu_job(nodes, GpuSchedulingConfig(accelerator="cuda"))

    assert plan["ready"] is False
    assert plan["reason"] == "no_eligible_gpu_node_with_free_resources"


def test_plan_gpu_job_cli_writes_json_from_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "scontrol.txt"
    output_json = tmp_path / "plan.json"
    fixture.write_text(SCONTROL_SAMPLE, encoding="utf-8")

    plan = plan_gpu_main(
        [
            "--scontrol-output",
            str(fixture),
            "--partition",
            "gpu4090_8",
            "--job-name",
            "fiir-gpu-smoke",
            "--time",
            "00:10:00",
            "--submit-script",
            "scripts/slurm/run_mlip_gpu_smoke.slurm",
            "--output-json",
            str(output_json),
        ]
    )

    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved == plan
    assert saved["ready"] is True
    assert saved["config"]["precision_profile"] == "tf32"
    assert saved["selection"]["selected_node"]["name"] == "gpu40902"
    assert saved["sbatch"]["request"]["gpus"] == 8
    assert saved["sbatch"]["request"]["cpus"] == 32
    assert saved["sbatch"]["request"]["exclusive"] is False
    assert saved["sbatch"]["request"]["node"] is None
    assert "--nodelist" not in saved["sbatch"]["sbatch_args"]
