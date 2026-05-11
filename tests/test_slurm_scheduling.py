from __future__ import annotations

import json
from pathlib import Path

from fiir_crystal.slurm_scheduling import (
    CpuSchedulingConfig,
    concurrency_warning,
    parse_scontrol_cpu_nodes,
    plan_cpu_job,
    plan_slurm_job,
)
from scripts.slurm.plan_slurm_job import main as plan_slurm_main


CPU_SCONTROL_SAMPLE = """
NodeName=node045 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.01
   Gres=(null)
   State=IDLE ThreadsPerCore=1
   Partitions=regular256,long
   RealMemory=256000 AllocMem=0 FreeMem=250000
   CfgTRES=cpu=64,mem=256000M,billing=64
   AllocTRES=

NodeName=node055 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.02
   Gres=(null)
   State=IDLE ThreadsPerCore=1
   Partitions=regular128
   RealMemory=128000 AllocMem=0 FreeMem=120000
   CfgTRES=cpu=64,mem=128000M,billing=64
   AllocTRES=

NodeName=test001 Arch=x86_64 CoresPerSocket=32
   CPUAlloc=0 CPUEfctv=64 CPUTot=64 CPULoad=0.02
   Gres=gpu:rtx4090:2
   State=IDLE ThreadsPerCore=1
   Partitions=test
   RealMemory=256000 AllocMem=0 FreeMem=240000
   CfgTRES=cpu=64,mem=256000M,billing=64,gres/gpu=2
   AllocTRES=
"""


def test_cpu_policy_prefers_test_for_short_jobs() -> None:
    nodes = parse_scontrol_cpu_nodes(CPU_SCONTROL_SAMPLE)
    plan = plan_cpu_job(
        nodes,
        CpuSchedulingConfig(expected_minutes=10, short_task_minutes=30),
        submit_script="scripts/slurm/run_crystalformer_bulk_test.slurm",
    )

    assert plan["ready"] is True
    assert plan["reason"] == "short_job_idle_test"
    assert plan["selection"]["partition_arg"] == "test"
    assert plan["sbatch"]["request"]["cpus"] == 64
    assert "--ntasks-per-node" in plan["sbatch"]["sbatch_args"]
    assert "FIIR_TOTAL_CPU_CORES=64" in " ".join(plan["sbatch"]["sbatch_args"])


def test_cpu_policy_uses_ordered_idle_partition_for_long_jobs() -> None:
    nodes = parse_scontrol_cpu_nodes(CPU_SCONTROL_SAMPLE)
    plan = plan_cpu_job(
        nodes,
        CpuSchedulingConfig(expected_minutes=180, short_task_minutes=30),
    )

    assert plan["ready"] is True
    assert plan["reason"] == "first_idle_in_policy_order"
    assert plan["selection"]["partition_arg"] == "regular256"
    assert plan["selection"]["selected_node"]["name"] == "node045"


def test_cpu_policy_queues_all_partitions_when_no_idle_node() -> None:
    busy_text = CPU_SCONTROL_SAMPLE.replace("State=IDLE", "State=ALLOCATED")
    nodes = parse_scontrol_cpu_nodes(busy_text)
    plan = plan_cpu_job(nodes, CpuSchedulingConfig(expected_minutes=180))

    assert plan["ready"] is True
    assert plan["reason"] == "no_idle_queue_all_policy_partitions"
    assert plan["selection"]["partition_arg"] == "regular256,regular128,regular6430,regular,test"
    assert plan["selection"]["core_budget"] is None
    assert plan["sbatch"]["request"]["cpus"] is None
    assert "--ntasks-per-node" not in plan["sbatch"]["sbatch_args"]


def test_unified_planner_dispatches_cpu_kind() -> None:
    nodes = parse_scontrol_cpu_nodes(CPU_SCONTROL_SAMPLE)
    plan = plan_slurm_job(
        kind="cpu",
        cpu_nodes=nodes,
        cpu_config=CpuSchedulingConfig(force_partition="regular128"),
    )

    assert plan["kind"] == "cpu"
    assert plan["ready"] is True
    assert plan["reason"] == "forced"
    assert plan["selection"]["partition_arg"] == "regular128"


def test_concurrency_warning_preserved_in_unified_cli(tmp_path: Path, capsys) -> None:
    fixture = tmp_path / "scontrol.txt"
    output_json = tmp_path / "plan.json"
    fixture.write_text(CPU_SCONTROL_SAMPLE, encoding="utf-8")

    plan = plan_slurm_main(
        [
            "--kind",
            "cpu",
            "--scontrol-output",
            str(fixture),
            "--expected-minutes",
            "180",
            "--max-concurrent-generations",
            "16",
            "--output-json",
            str(output_json),
            "--shell-vars",
        ]
    )
    captured = capsys.readouterr().out
    saved = json.loads(output_json.read_text(encoding="utf-8"))

    assert saved == plan
    assert "FIIR_SELECTED_PARTITION_ARG=regular256" in captured
    assert "FIIR_SELECTED_CORE_BUDGET=64" in captured
    assert "FIIR_CONCURRENCY_WARNING=" in captured
    assert saved["concurrency_warning"] == concurrency_warning(180, 30, "16")
