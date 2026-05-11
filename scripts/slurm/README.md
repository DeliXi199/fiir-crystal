# SLURM Submission Templates

Submit the CrystalFormer bulk orchestration job from the repository root:

```bash
sbatch scripts/slurm/run_crystalformer_bulk_test.slurm
```

The default job is safe: it only writes a bulk plan and does not execute
CrystalFormer generation.

Validate a real-command template on the test partition before running it:

```bash
FIIR_VALIDATE_ONLY=1 \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_validate \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real.example.json \
sbatch scripts/slurm/run_crystalformer_bulk_test.slurm
```

To run generation explicitly after validation is clean:

```bash
FIIR_RUN_GENERATION=1 \
FIIR_ONLY_FORMULA=BaTiO3 \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real.example.json \
sbatch scripts/slurm/run_crystalformer_bulk_test.slurm
```

Common overrides:

- `FIIR_BULK_CONFIG`: bulk generation JSON config path.
- `FIIR_OUTPUT_ROOT`: output directory for plan, raw outputs, smoke artifacts, and reports.
- `FIIR_ONLY_FORMULA`: run a single configured formula.
- `FIIR_VALIDATE_ONLY`: set to `1` or `true` to expand commands and check paths without running generation or smoke.
- `FIIR_RUN_GENERATION`: set to `1` or `true` to execute generation.
- `FIIR_CONTINUE_ON_ERROR`: set to `1` or `true` to keep later formulas running after a failure.
- `FIIR_SKIP_EXISTING_MODE`: `default`, `skip`, or `no-skip`.
- `FIIR_CONDA_ENV`: conda environment to activate after `~/.bashrc`.
- `FIIR_VENV`: virtualenv path to activate.
- `FIIR_MODULES`: whitespace-separated modules to load, for example `cuda/12.1`.
- `FIIR_PYTHON`: Python executable, default `python`.

The script writes SLURM logs as `slurm_%x_%j.log` and `slurm_%x_%j.err` in the
submission directory. These logs are ignored by git.
