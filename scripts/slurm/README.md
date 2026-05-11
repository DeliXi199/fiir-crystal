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

For multi-node generation, submit independent one-node shard configs. The
checked-in perovskite 128 bank is split into four 32-formula shard configs:

```bash
for shard in configs/generated/crystalformer_shards/perovskite_128_32x1600/shard_[0-9][0-9][0-9].json; do
  name="$(basename "${shard}" .json)"
  FIIR_CONDA_ENV=crystalformer \
  FIIR_RUN_GENERATION=1 \
  FIIR_CONTINUE_ON_ERROR=1 \
  FIIR_EXPECTED_MINUTES=180 \
  FIIR_TIME_LIMIT=04:00:00 \
  FIIR_SKIP_EXISTING_MODE=no-skip \
  FIIR_MAX_CONCURRENT_GENERATIONS=16 \
  FIIR_BULK_CONFIG="${shard}" \
  FIIR_OUTPUT_ROOT="outputs/crystalformer_bulk_real_smoke_perovskite_128_32x1600_${name}" \
  bash scripts/slurm/submit_crystalformer_bulk.sh
done
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
- `FIIR_SLURM_LOG_DIR`: directory for SLURM stdout/stderr files, default `logs/slurm`.

The wrapper creates the log directory before submission and writes SLURM logs
as `logs/slurm/%x_%j.log` and `logs/slurm/%x_%j.err` by default. Direct
`sbatch` uses the same default log directory. These logs are ignored by git.

## Startup Monitoring For Longer Jobs

For jobs expected to run longer than a few minutes, monitor only the startup
window, then leave the job to SLURM:

```bash
scripts/slurm/monitor_slurm_startup.sh --job-id <job-id>
```

The submitter prints this command after `sbatch` returns a job id. The default
startup window is 120 seconds. Use up to 300 seconds for a new template, new
environment, or new scale:

```bash
scripts/slurm/monitor_slurm_startup.sh --job-id <job-id> --seconds 300
```

The monitor checks `squeue`, tails the matching stdout/stderr files under
`logs/slurm/`, and exits with a failure if stderr becomes non-empty. If the job
is still listed by `squeue` and stderr is empty after the startup window, stop
watching it interactively and inspect the expected summary artifact after the
job finishes.

For CrystalFormer bulk runs, the expected final summary is usually:

```text
<FIIR_OUTPUT_ROOT>/bulk_summary.json
```

When `FIIR_RUN_GENERATION=1`, `auto` parallelism uses the full CPU budget. For
example, a 64-core node with a three-formula config runs three CrystalFormer
subprocesses concurrently and assigns thread counts such as `22, 21, 21`.
Resolved allocations are recorded in `bulk_summary.json` and
`generation_provenance.json`.
