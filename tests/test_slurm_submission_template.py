from pathlib import Path


def test_crystalformer_bulk_slurm_template_is_safe_by_default() -> None:
    script = Path("scripts/slurm/run_crystalformer_bulk_test.slurm")
    text = script.read_text(encoding="utf-8")

    assert "#SBATCH --account=hmt03" in text
    assert "#SBATCH --partition=test" in text
    assert "#SBATCH --exclusive" in text
    assert "#SBATCH --ntasks-per-node=64" not in text
    assert "#SBATCH --output=logs/slurm/%x_%j.log" in text
    assert "#SBATCH --error=logs/slurm/%x_%j.err" in text
    assert "SLURM_CPUS_ON_NODE" in text
    assert 'FIIR_VALIDATE_ONLY="${FIIR_VALIDATE_ONLY:-0}"' in text
    assert "--validate-only" in text
    assert "FIIR_VALIDATE_ONLY is enabled" in text
    assert 'FIIR_RUN_GENERATION="${FIIR_RUN_GENERATION:-0}"' in text
    assert "--run-generation" in text
    assert 'FIIR_TOTAL_CPU_CORES="${FIIR_TOTAL_CPU_CORES:-}"' in text
    assert 'FIIR_MAX_CONCURRENT_GENERATIONS="${FIIR_MAX_CONCURRENT_GENERATIONS:-auto}"' in text
    assert 'FIIR_GENERATION_CPU_THREADS="${FIIR_GENERATION_CPU_THREADS:-auto}"' in text
    assert "--total-cpu-cores" in text
    assert "--max-concurrent-generations" in text
    assert "--generation-cpu-threads" in text
    assert 'conda activate "${FIIR_CONDA_ENV}"' in text
    assert 'source "${FIIR_VENV}/bin/activate"' in text
    assert text.count("set +u") >= 2
    assert "FIIR_RUN_GENERATION is not enabled" in text
    assert "scripts/run_crystalformer_bulk_generation.py" in text


def test_crystalformer_policy_submitter_encodes_partition_order() -> None:
    script = Path("scripts/slurm/submit_crystalformer_bulk.sh")
    text = script.read_text(encoding="utf-8")

    assert "regular256 regular128 regular6430 regular test" in text
    assert "FIIR_EXPECTED_MINUTES" in text
    assert "FIIR_SHORT_TASK_MINUTES" in text
    assert "normalize_partition_name" in text
    assert "regular256*" in text
    assert "plan_slurm_job.py" in text
    assert "--kind cpu" in text
    assert "--shell-vars" in text
    assert "FIIR_SELECTED_PARTITION_ARG" in text
    assert "FIIR_SELECTED_CORE_BUDGET" in text
    assert "FIIR_EXPORT_ARG" in text
    assert "--exclusive" in text
    assert "--ntasks-per-node" in text
    assert "export_arg=\"$FIIR_EXPORT_ARG\"" in text
    assert "FIIR_DRY_RUN" in text
    assert "FIIR_CONCURRENCY_WARNING" in text
    assert 'FIIR_SLURM_LOG_DIR="${FIIR_SLURM_LOG_DIR:-logs/slurm}"' in text
    assert 'mkdir -p "$FIIR_SLURM_LOG_DIR"' in text
    assert '--output "${FIIR_SLURM_LOG_DIR}/%x_%j.log"' in text
    assert '--error "${FIIR_SLURM_LOG_DIR}/%x_%j.err"' in text
    assert "monitor_slurm_startup.sh --job-id" in text
    assert "Submitted batch job" in text


def test_unified_slurm_planner_cli_exists() -> None:
    script = Path("scripts/slurm/plan_slurm_job.py")
    text = script.read_text(encoding="utf-8")

    assert "--kind" in text
    assert "choices=(\"cpu\", \"gpu\")" in text
    assert "CpuSchedulingConfig" in text
    assert "GpuSchedulingConfig" in text
    assert "--shell-vars" in text
    assert "--run-sbatch" in text


def test_slurm_startup_monitor_encodes_long_job_watch_policy() -> None:
    script = Path("scripts/slurm/monitor_slurm_startup.sh")
    text = script.read_text(encoding="utf-8")

    assert "FIIR_STARTUP_MONITOR_SECONDS:-120" in text
    assert "FIIR_STARTUP_MONITOR_MAX_SECONDS:-300" in text
    assert "FIIR_STARTUP_MONITOR_INTERVAL_SECONDS:-30" in text
    assert "squeue" in text
    assert "logs/slurm" in text
    assert "job_not_listed" in text
    assert "non-empty stderr" in text
    assert "Startup monitor window passed" in text
    assert "Leave the job to SLURM" in text


def test_slurm_readme_documents_cpu_load_oversubscription() -> None:
    text = Path("scripts/slurm/README.md").read_text(encoding="utf-8")

    assert "CPU Load And Over-Subscription" in text
    assert "FIIR_MAX_CONCURRENT_GENERATIONS=8" in text
    assert "CPULoad" in text
    assert "CPUAlloc=64" in text
    assert "CPUTot=64" in text


def test_slurm_logs_are_gitignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "slurm_*.log" in text
    assert "slurm_*.err" in text
    assert "log_*.log" in text
    assert "err_*.err" in text
    assert "logs/slurm/*.log" in text
    assert "logs/slurm/*.err" in text
