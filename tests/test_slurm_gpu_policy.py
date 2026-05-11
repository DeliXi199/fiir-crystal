from __future__ import annotations

import json
from pathlib import Path

from fiir_crystal.slurm_gpu_policy import (
    GpuSchedulingConfig,
    build_sbatch_plan,
    parse_scontrol_nodes,
    plan_gpu_job,
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


def test_cuda_policy_ignores_amd_and_selects_strongest_remaining_capacity() -> None:
    nodes = parse_scontrol_nodes(SCONTROL_SAMPLE)
    selection = select_best_gpu_node(nodes, GpuSchedulingConfig(accelerator="cuda"))

    assert selection is not None
    assert selection.node.name == "gpuh2002"
    assert selection.partition == "h200"
    candidate_names = [item["node"]["name"] for item in selection.candidates]
    assert "gpu005" not in candidate_names
    assert "gpuh202" not in candidate_names
    assert candidate_names[:2] == ["gpuh2002", "gpu40902"]


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
    assert request["node"] == "gpuh2002"
    assert request["gpus"] == 6
    assert request["cpus"] == 128
    assert request["gres"] == "gpu:6"
    assert request["exclusive"] is False
    assert request["uses_all_currently_free_gpus"] is True
    assert request["uses_all_currently_free_cpus"] is True
    assert "--nodelist" in plan["sbatch_args"]
    assert "gpuh2002" in plan["sbatch_args"]
    assert "--cpus-per-task" in plan["sbatch_args"]
    assert "128" in plan["sbatch_args"]
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
    assert plan["request"]["exclusive"] is True
    assert "--exclusive" in plan["sbatch_args"]
    assert "gpu:rtx4090:8" in plan["sbatch_args"]


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
    assert saved["selection"]["selected_node"]["name"] == "gpu40902"
    assert saved["sbatch"]["request"]["gpus"] == 8
    assert saved["sbatch"]["request"]["cpus"] == 32
    assert saved["sbatch"]["request"]["exclusive"] is True
