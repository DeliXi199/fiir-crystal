from pathlib import Path


def test_crystalformer_bulk_slurm_template_is_safe_by_default() -> None:
    script = Path("scripts/slurm/run_crystalformer_bulk_test.slurm")
    text = script.read_text(encoding="utf-8")

    assert "#SBATCH --account=hmt03" in text
    assert "#SBATCH --partition=test" in text
    assert "#SBATCH --exclusive" in text
    assert "#SBATCH --ntasks-per-node=64" not in text
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
    assert "idle_node_count" in text
    assert "sinfo" in text
    assert "regular)" in text
    assert "printf '56" in text
    assert "printf '64" in text
    assert "join_partitions" in text
    assert "--exclusive" in text
    assert "--ntasks-per-node" in text
    assert "FIIR_TOTAL_CPU_CORES" in text
    assert "FIIR_DRY_RUN" in text


def test_slurm_logs_are_gitignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "slurm_*.log" in text
    assert "slurm_*.err" in text
    assert "log_*.log" in text
    assert "err_*.err" in text
