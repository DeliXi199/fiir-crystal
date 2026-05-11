from pathlib import Path


def test_crystalformer_bulk_slurm_template_is_safe_by_default() -> None:
    script = Path("scripts/slurm/run_crystalformer_bulk_test.slurm")
    text = script.read_text(encoding="utf-8")

    assert "#SBATCH --account=hmt03" in text
    assert "#SBATCH --partition=test" in text
    assert "#SBATCH --ntasks-per-node=64" in text
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


def test_slurm_logs_are_gitignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "slurm_*.log" in text
    assert "slurm_*.err" in text
    assert "log_*.log" in text
    assert "err_*.err" in text
