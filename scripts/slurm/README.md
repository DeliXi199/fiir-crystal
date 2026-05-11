# SLURM Submission Templates

Submit the CrystalFormer bulk orchestration job from the repository root with
the policy wrapper:

```bash
bash scripts/slurm/submit_crystalformer_bulk.sh
```

The wrapper delegates selection to the unified stdlib-only planner
`scripts/slurm/plan_slurm_job.py --kind cpu`. It submits one exclusive node by
default and uses all CPU cores on that node. Partition selection follows this
policy:

- If `FIIR_EXPECTED_MINUTES <= 30` and `test` has an idle node, use `test`.
- Otherwise use the first idle partition in this order:
  `regular256`, `regular128`, `regular6430`, `regular`, `test`.
- If none have idle nodes, queue on all policy partitions:
  `regular256,regular128,regular6430,regular,test`.
- When node details are available, the planner uses the selected node's full
  `CPUTot`; if SLURM details are unavailable, `regular` falls back to 56 cores
  and the other listed CPU partitions fall back to 64 cores.
- `sinfo` may display the default partition as `regular256*`. The trailing
  `*` is only a display marker, not part of the partition name. Use
  `regular256` in `FIIR_FORCE_PARTITION` or `FIIR_PARTITION_ORDER`; the
  submitter also strips a trailing `*` defensively.

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

## CrystalFormer GPU Submitter

When the `crystalformer` environment has CUDA-enabled JAX, use the GPU
submitter to route bulk CrystalFormer jobs through the same unified scheduler:

```bash
FIIR_VALIDATE_ONLY=1 \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_gpu_validate \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real.example.json \
bash scripts/slurm/submit_crystalformer_bulk_gpu.sh
```

The GPU submitter is also safe by default: without `FIIR_RUN_GENERATION=1`, the
job only writes a bulk plan or validation summary. It exports
`FIIR_CONDA_ENV=crystalformer`, requires a JAX GPU backend by default, requests
all currently free GPUs and CPU cores on the selected node, and passes
`FIIR_TOTAL_GPUS` plus `CUDA_VISIBLE_DEVICES` into the bulk runner. The runner
then assigns one visible CUDA device per concurrent CrystalFormer subprocess
and divides the selected CPU cores across those subprocesses. Generation
subprocesses default to `JAX_PLATFORMS=cuda,cpu` because CrystalFormer sampling
uses JAX callbacks that need a local CPU device while CUDA remains the primary
backend.

After validation is clean, run a small explicit GPU generation:

```bash
FIIR_RUN_GENERATION=1 \
FIIR_ONLY_FORMULA=BaTiO3 \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_gpu_smoke \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real.example.json \
bash scripts/slurm/submit_crystalformer_bulk_gpu.sh
```

Useful GPU submitter overrides:

- `FIIR_GPU_PARTITIONS`: comma- or space-separated GPU partitions, default `gpu4090_8`.
- `FIIR_GPU_ACCELERATOR`: `cuda` or `any`, default `cuda`.
- `FIIR_GPU_MIN_GPUS`, `FIIR_GPU_MIN_CPUS`, `FIIR_GPU_MIN_MEMORY_MB`: minimum remaining resources.
- `FIIR_SLURM_ACCOUNT`: account passed to `sbatch`, default `hmt03`.
- `FIIR_REQUIRE_JAX_GPU`: set to `0` only for dry debugging without a GPU backend.
- `FIIR_GPU_PLAN_JSON`: path for the deterministic GPU scheduling plan.

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
  FIIR_MAX_CONCURRENT_GENERATIONS=8 \
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

## CPU Load And Over-Subscription

For long CrystalFormer shards, prefer `FIIR_MAX_CONCURRENT_GENERATIONS=8`.
Running 16 CrystalFormer/JAX subprocesses on 64-core `regular128` nodes has
shown `CPULoad` values around 100-120 while `CPUAlloc=64` and `CPUTot=64`.
That means the node is busy and likely over-subscribed by JAX/BLAS worker
threads, not necessarily failed.

If `scontrol show node <node>` shows `CPUAlloc` equal to `CPUTot`, stderr is
empty, memory is below node capacity, and `squeue` still shows the job running,
let the current job continue. For future jobs, reduce concurrency:

```bash
FIIR_MAX_CONCURRENT_GENERATIONS=8
```

The submitter prints a warning when a long job explicitly requests more than 8
concurrent generation subprocesses.

When `FIIR_RUN_GENERATION=1`, `auto` parallelism uses the full CPU budget. For
example, a 64-core node with a three-formula config runs three CrystalFormer
subprocesses concurrently and assigns thread counts such as `22, 21, 21`.
Resolved allocations are recorded in `bulk_summary.json` and
`generation_provenance.json`.

## GPU Node Planning Policy

Use the same unified planner with `--kind gpu` before launching optional local
MLIP or other GPU work. The planner is read-only by default: it inspects SLURM
node state, filters out nodes that do not meet the requested CUDA/GPU/CPU/memory
minimums, then ranks eligible nodes by available TF32 GPU compute capacity:

```text
score = free_gpus * tf32_gpu_weight
```

CPU cores and memory are used for eligibility checks and request sizing, not as
default ranking signals. It submits only when `--run-sbatch` is passed
explicitly. The older `scripts/slurm/plan_gpu_job.py` entrypoint remains as a
GPU-only compatibility wrapper.

For CUDA PyTorch jobs, the default `--accelerator cuda` ignores AMD and Intel
GPU partitions so a CUDA environment is not accidentally placed on the wrong
hardware. Override with `--accelerator any` for non-CUDA workflows.

```bash
python scripts/slurm/plan_slurm_job.py \
  --kind gpu \
  --accelerator cuda \
  --job-name fiir-mlip-gpu-smoke \
  --time 00:30:00 \
  --submit-script scripts/slurm/run_mlip_gpu_smoke.slurm \
  --output-json outputs/slurm_gpu_plans/mlip_gpu_smoke_plan.json
```

The generated plan requests one node, pins the selected node with `--nodelist`,
requests all currently free GPUs with `--gres`, and requests all currently free
CPU cores. For a fully idle node it also adds `--exclusive`; for a partially
used `MIXED` node it requests only the remaining free resources and does not
try to take resources already allocated to other jobs.

Useful options:

- `--partition gpu4090_8`: restrict selection to one or more partitions.
- `--layout single-task`: one task receives all selected CPUs and GPUs.
- `--layout one-task-per-gpu`: one task per free GPU, with CPU cores divided
  across tasks.
- `--min-gpus`, `--min-cpus`, `--min-memory-mb`: minimum remaining resources.
- `--gpu-weight h200=650`: override the default TF32 per-GPU ranking weight.
- `--print-json`: print the full deterministic plan.
- `--run-sbatch`: submit the planned command; off by default.

The planner exports these values into the SLURM job environment:

- `FIIR_GPU_NODE`
- `FIIR_GPU_PARTITION`
- `FIIR_TOTAL_GPUS`
- `FIIR_TOTAL_CPU_CORES`
- `FIIR_GPU_MODEL`
- `FIIR_GPU_GRES`
