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
    assert 'FIIR_TOTAL_GPUS="${FIIR_TOTAL_GPUS:-}"' in text
    assert 'FIIR_GPU_DEVICES="${FIIR_GPU_DEVICES:-${CUDA_VISIBLE_DEVICES:-}}"' in text
    assert 'FIIR_REQUIRE_JAX_GPU="${FIIR_REQUIRE_JAX_GPU:-0}"' in text
    assert 'FIIR_MAX_CONCURRENT_GENERATIONS="${FIIR_MAX_CONCURRENT_GENERATIONS:-auto}"' in text
    assert 'FIIR_GENERATION_CPU_THREADS="${FIIR_GENERATION_CPU_THREADS:-auto}"' in text
    assert "--total-cpu-cores" in text
    assert "--total-gpus" in text
    assert "--gpu-devices" in text
    assert "--max-concurrent-generations" in text
    assert "--generation-cpu-threads" in text
    assert "jax_default_backend" in text
    assert "JAX default backend is not gpu" in text
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


def test_crystalformer_gpu_submitter_uses_unified_gpu_policy() -> None:
    script = Path("scripts/slurm/submit_crystalformer_bulk_gpu.sh")
    text = script.read_text(encoding="utf-8")

    assert "--kind" in text
    assert '"gpu"' in text
    assert "FIIR_GPU_PARTITIONS" in text
    assert 'DEFAULT_GPU_PARTITIONS="auto"' in text
    assert "is_auto_partition_set" in text
    assert "partition_filter=auto_all_cuda_compatible" in text
    assert "partition_filter=explicit_allowlist" in text
    assert "FIIR_GPU_ACCELERATOR" in text
    assert "FIIR_GPU_PRECISION_PROFILE" in text
    assert "FIIR_GPU_QUEUE_MODE" in text
    assert "--gpu-queue-mode" in text
    assert "FIIR_GPU_RESERVED_NODES" in text
    assert "FIIR_GPU_RESERVED_NODES_FILE" in text
    assert "--reserved-node" in text
    assert "batch_reserved_nodes" in text
    assert "FIIR_GPU_QUEUE_MIN_GPUS" in text
    assert "FIIR_GPU_QUEUE_MIN_CPUS" in text
    assert "FIIR_GPU_QUEUE_MEMORY_MB" in text
    assert "--queue-min-gpus" in text
    assert "--queue-min-cpus" in text
    assert "--queue-memory-mb" in text
    assert "FIIR_MACE_RELAX" in text
    assert "fp64" in text
    assert "--precision-profile" in text
    assert "FIIR_SLURM_ACCOUNT" in text
    assert "hmt03" in text
    assert "FIIR_CONDA_ENV" in text
    assert "crystalformer" in text
    assert "FIIR_REQUIRE_JAX_GPU" in text
    assert "XLA_PYTHON_CLIENT_PREALLOCATE" in text
    assert (
        "test_partition_policy=eligible only when FIIR_TIME_LIMIT is <= 00:30:00, "
        "and used only when no non-test GPU partition has enough free GPUs"
    ) in text
    assert "--run-sbatch" in text
    assert "FIIR_DRY_RUN" in text
    assert "monitor_slurm_startup.sh --job-id" in text


def test_mace_slurm_template_uses_float64_by_default_for_relaxation() -> None:
    text = Path("scripts/slurm/run_mace_offline_validation.slurm").read_text(encoding="utf-8")

    assert 'FIIR_MACE_RELAX="${FIIR_MACE_RELAX:-0}"' in text
    assert "FIIR_MACE_VALIDATION_SOURCE" in text
    assert "local_mlip_mace_relaxation" in text
    assert "FIIR_MACE_DERIVE_STABILITY_FROM_RELAXATION" in text
    assert "--derive-stability-from-relaxation" in text
    assert 'if [[ -z "${FIIR_MACE_DEFAULT_DTYPE+x}" ]]; then' in text
    assert 'FIIR_MACE_DEFAULT_DTYPE="float64"' in text
    assert 'FIIR_MACE_DEFAULT_DTYPE="float32"' in text
    assert '--default-dtype "${FIIR_MACE_DEFAULT_DTYPE}"' in text
    assert '--validation-source "${FIIR_MACE_VALIDATION_SOURCE}"' in text


def test_unified_slurm_planner_cli_exists() -> None:
    script = Path("scripts/slurm/plan_slurm_job.py")
    text = script.read_text(encoding="utf-8")

    assert "--kind" in text
    assert "choices=(\"cpu\", \"gpu\")" in text
    assert "CpuSchedulingConfig" in text
    assert "GpuSchedulingConfig" in text
    assert "--precision-profile" in text
    assert "--reserved-node" in text
    assert "--gpu-queue-mode" in text
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


def test_slurm_readme_documents_auto_gpu_partition_selection() -> None:
    text = Path("scripts/slurm/README.md").read_text(encoding="utf-8")

    assert "FIIR_GPU_PARTITIONS=auto" in text
    assert "currently available CUDA-compatible GPU nodes" in text
    assert "The `test` partition is non-preferred CUDA-compatible GPU capacity" in text
    assert "no non-`test` GPU partition has enough free GPUs to" in text
    assert "GPU start-now eligibility" in text
    assert "30\nminutes or less" in text
    assert "flexible multi-partition queueing" in text
    assert "does not use `--nodelist`" in text
    assert "8 GPUs and 32 CPUs" in text
    assert "256000M" in text
    assert "Omit" in text
    assert "resource-aware selection across all CUDA-compatible GPU" in text


def test_slurm_logs_are_gitignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "slurm_*.log" in text
    assert "slurm_*.err" in text
    assert "log_*.log" in text
    assert "err_*.err" in text
    assert "logs/slurm/*.log" in text
    assert "logs/slurm/*.err" in text
