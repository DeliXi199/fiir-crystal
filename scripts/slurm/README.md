# SLURM Submission Templates

Submit the CrystalFormer bulk orchestration job from the repository root with
the policy wrapper:

```bash
bash scripts/slurm/submit_crystalformer_bulk.sh
```

The wrapper submits one exclusive node by default and uses all CPU cores on
that node. Partition selection follows this policy:

- If `FIIR_EXPECTED_MINUTES <= 30` and `test` has an idle node, use `test`.
- Otherwise use the first idle partition in this order:
  `regular256`, `regular128`, `regular6430`, `regular`, `test`.
- If none have idle nodes, queue on all policy partitions:
  `regular256,regular128,regular6430,regular,test`.
- `regular` is treated as 56 cores; all other listed CPU partitions are treated as 64 cores.

The direct SLURM file still works with `sbatch`, but the wrapper is the
recommended entrypoint. The default job is safe: it only writes a bulk plan and
does not execute CrystalFormer generation.

Validate a real-command template on the test partition before running it:

```bash
FIIR_VALIDATE_ONLY=1 \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_validate \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real.example.json \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

To run generation explicitly after validation is clean:

```bash
FIIR_RUN_GENERATION=1 \
FIIR_ONLY_FORMULA=BaTiO3 \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real.example.json \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

Common overrides:

- `FIIR_BULK_CONFIG`: bulk generation JSON config path.
- `FIIR_OUTPUT_ROOT`: output directory for plan, raw outputs, smoke artifacts, and reports.
- `FIIR_ONLY_FORMULA`: run a single configured formula.
- `FIIR_VALIDATE_ONLY`: set to `1` or `true` to expand commands and check paths without running generation or smoke.
- `FIIR_RUN_GENERATION`: set to `1` or `true` to execute generation.
- `FIIR_CONTINUE_ON_ERROR`: set to `1` or `true` to keep later formulas running after a failure.
- `FIIR_SKIP_EXISTING_MODE`: `default`, `skip`, or `no-skip`.
- `FIIR_TOTAL_CPU_CORES`: CPU budget passed to the runner, default computed from SLURM nodes and tasks per node.
- `FIIR_MAX_CONCURRENT_GENERATIONS`: formula subprocess concurrency, default `auto`.
- `FIIR_GENERATION_CPU_THREADS`: CPU threads per CrystalFormer subprocess, default `auto`.
- `FIIR_CONDA_ENV`: conda environment to activate after `~/.bashrc`.
- `FIIR_VENV`: virtualenv path to activate.
- `FIIR_MODULES`: whitespace-separated modules to load, for example `cuda/12.1`.
- `FIIR_PYTHON`: Python executable, default `python`.
- `FIIR_EXPECTED_MINUTES`: expected job duration in minutes, default `30`.
- `FIIR_FORCE_PARTITION`: bypass policy and submit to one named partition.
- `FIIR_DRY_RUN`: set to `1` or `true` to print the selected `sbatch` command without submitting.
- `FIIR_TIME_LIMIT`: optional SLURM `--time` value.

The script writes SLURM logs as `slurm_%x_%j.log` and `slurm_%x_%j.err` in the
submission directory. These logs are ignored by git.

When `FIIR_RUN_GENERATION=1`, `auto` parallelism uses the full CPU budget. For
example, a 64-core node with a three-formula config runs three CrystalFormer
subprocesses concurrently and assigns thread counts such as `22, 21, 21`.
Resolved allocations are recorded in `bulk_summary.json` and
`generation_provenance.json`.
