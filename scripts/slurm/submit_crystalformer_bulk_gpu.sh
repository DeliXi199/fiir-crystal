#!/bin/bash
#
# Policy-aware GPU submitter for FIIR GPU jobs.
# It delegates node planning to scripts/slurm/plan_slurm_job.py --kind gpu.
# CrystalFormer generation remains opt-in through FIIR_RUN_GENERATION=1, while
# MACE and other GPU workflows can reuse this wrapper by setting
# FIIR_SUBMIT_SCRIPT.

set -eo pipefail

DEFAULT_GPU_PARTITIONS="auto"

FIIR_SUBMIT_SCRIPT="${FIIR_SUBMIT_SCRIPT:-scripts/slurm/run_crystalformer_bulk_test.slurm}"
FIIR_GPU_PARTITIONS="${FIIR_GPU_PARTITIONS:-${DEFAULT_GPU_PARTITIONS}}"
FIIR_GPU_ACCELERATOR="${FIIR_GPU_ACCELERATOR:-cuda}"
FIIR_GPU_MIN_GPUS="${FIIR_GPU_MIN_GPUS:-1}"
FIIR_GPU_MIN_CPUS="${FIIR_GPU_MIN_CPUS:-1}"
FIIR_GPU_MIN_MEMORY_MB="${FIIR_GPU_MIN_MEMORY_MB:-0}"
FIIR_GPU_QUEUE_MIN_GPUS="${FIIR_GPU_QUEUE_MIN_GPUS:-8}"
FIIR_GPU_QUEUE_MIN_CPUS="${FIIR_GPU_QUEUE_MIN_CPUS:-32}"
FIIR_GPU_QUEUE_MEMORY_MB="${FIIR_GPU_QUEUE_MEMORY_MB:-256000}"
FIIR_GPU_LAYOUT="${FIIR_GPU_LAYOUT:-single-task}"
FIIR_GPU_QUEUE_MODE="${FIIR_GPU_QUEUE_MODE:-auto}"
if [[ -z "${FIIR_GPU_PRECISION_PROFILE+x}" ]]; then
  if [[ "${FIIR_MACE_RELAX:-0}" == "1" || "${FIIR_MACE_RELAX:-0}" == "true" ]]; then
    FIIR_GPU_PRECISION_PROFILE="fp64"
  else
    FIIR_GPU_PRECISION_PROFILE="tf32"
  fi
fi
FIIR_SLURM_ACCOUNT="${FIIR_SLURM_ACCOUNT:-hmt03}"
FIIR_JOB_NAME="${FIIR_JOB_NAME:-fiir-cf-gpu}"
FIIR_TIME_LIMIT="${FIIR_TIME_LIMIT:-}"
FIIR_DRY_RUN="${FIIR_DRY_RUN:-0}"
FIIR_SLURM_LOG_DIR="${FIIR_SLURM_LOG_DIR:-logs/slurm}"
FIIR_GPU_PLAN_JSON="${FIIR_GPU_PLAN_JSON:-outputs/slurm_gpu_plans/crystalformer_bulk_gpu_plan.json}"
FIIR_PLANNER_PYTHON="${FIIR_PLANNER_PYTHON:-python}"

export FIIR_CONDA_ENV="${FIIR_CONDA_ENV:-crystalformer}"
export FIIR_REQUIRE_JAX_GPU="${FIIR_REQUIRE_JAX_GPU:-1}"
export FIIR_MAX_CONCURRENT_GENERATIONS="${FIIR_MAX_CONCURRENT_GENERATIONS:-auto}"
export FIIR_GENERATION_CPU_THREADS="${FIIR_GENERATION_CPU_THREADS:-auto}"
export XLA_PYTHON_CLIENT_PREALLOCATE="${XLA_PYTHON_CLIENT_PREALLOCATE:-false}"

normalize_partition_name() {
  local partition="$1"
  printf '%s\n' "${partition%\*}"
}

is_auto_partition_set() {
  local value="${1,,}"
  value="${value//[[:space:]]/}"
  [[ -z "$value" || "$value" == "auto" || "$value" == "all" || "$value" == "*" ]]
}

require_integer() {
  local name="$1"
  local value="$2"
  case "$value" in
    ''|*[!0-9]*)
      echo "${name} must be an integer: ${value}" >&2
      exit 2
      ;;
  esac
}

require_integer "FIIR_GPU_MIN_GPUS" "$FIIR_GPU_MIN_GPUS"
require_integer "FIIR_GPU_MIN_CPUS" "$FIIR_GPU_MIN_CPUS"
require_integer "FIIR_GPU_MIN_MEMORY_MB" "$FIIR_GPU_MIN_MEMORY_MB"
require_integer "FIIR_GPU_QUEUE_MIN_GPUS" "$FIIR_GPU_QUEUE_MIN_GPUS"
require_integer "FIIR_GPU_QUEUE_MIN_CPUS" "$FIIR_GPU_QUEUE_MIN_CPUS"
require_integer "FIIR_GPU_QUEUE_MEMORY_MB" "$FIIR_GPU_QUEUE_MEMORY_MB"

mkdir -p "$FIIR_SLURM_LOG_DIR"
mkdir -p "$(dirname "$FIIR_GPU_PLAN_JSON")"

planner_args=(
  "$FIIR_PLANNER_PYTHON"
  "scripts/slurm/plan_slurm_job.py"
  "--kind"
  "gpu"
  "--accelerator"
  "$FIIR_GPU_ACCELERATOR"
  "--min-gpus"
  "$FIIR_GPU_MIN_GPUS"
  "--min-cpus"
  "$FIIR_GPU_MIN_CPUS"
  "--min-memory-mb"
  "$FIIR_GPU_MIN_MEMORY_MB"
  "--queue-min-gpus"
  "$FIIR_GPU_QUEUE_MIN_GPUS"
  "--queue-min-cpus"
  "$FIIR_GPU_QUEUE_MIN_CPUS"
  "--queue-memory-mb"
  "$FIIR_GPU_QUEUE_MEMORY_MB"
  "--layout"
  "$FIIR_GPU_LAYOUT"
  "--precision-profile"
  "$FIIR_GPU_PRECISION_PROFILE"
  "--gpu-queue-mode"
  "$FIIR_GPU_QUEUE_MODE"
  "--job-name"
  "$FIIR_JOB_NAME"
  "--log-dir"
  "$FIIR_SLURM_LOG_DIR"
  "--submit-script"
  "$FIIR_SUBMIT_SCRIPT"
  "--output-json"
  "$FIIR_GPU_PLAN_JSON"
)

if ! is_auto_partition_set "$FIIR_GPU_PARTITIONS"; then
  for partition in ${FIIR_GPU_PARTITIONS//,/ }; do
    normalized="$(normalize_partition_name "$partition")"
    if [ -n "$normalized" ]; then
      planner_args+=("--partition" "$normalized")
    fi
  done
fi

if [ -n "$FIIR_SLURM_ACCOUNT" ]; then
  planner_args+=("--account" "$FIIR_SLURM_ACCOUNT")
fi

if [ -n "$FIIR_TIME_LIMIT" ]; then
  planner_args+=("--time" "$FIIR_TIME_LIMIT")
fi

if [ "$FIIR_DRY_RUN" != "1" ] && [ "$FIIR_DRY_RUN" != "true" ]; then
  planner_args+=("--run-sbatch")
fi

echo "FIIR GPU submission policy:"
echo "  gpu_partitions=${FIIR_GPU_PARTITIONS}"
if is_auto_partition_set "$FIIR_GPU_PARTITIONS"; then
  echo "  partition_filter=auto_all_cuda_compatible"
else
  echo "  partition_filter=explicit_allowlist"
fi
echo "  accelerator=${FIIR_GPU_ACCELERATOR}"
echo "  min_gpus=${FIIR_GPU_MIN_GPUS}"
echo "  min_cpus=${FIIR_GPU_MIN_CPUS}"
echo "  min_memory_mb=${FIIR_GPU_MIN_MEMORY_MB}"
echo "  queue_min_gpus=${FIIR_GPU_QUEUE_MIN_GPUS}"
echo "  queue_min_cpus=${FIIR_GPU_QUEUE_MIN_CPUS}"
echo "  queue_memory_mb=${FIIR_GPU_QUEUE_MEMORY_MB}"
echo "  layout=${FIIR_GPU_LAYOUT}"
echo "  precision_profile=${FIIR_GPU_PRECISION_PROFILE}"
echo "  gpu_queue_mode=${FIIR_GPU_QUEUE_MODE} (auto pins the best free eligible GPU node and falls back to flexible queueing only when none is free)"
echo "  slurm_account=${FIIR_SLURM_ACCOUNT:-none}"
echo "  time_limit=${FIIR_TIME_LIMIT:-planner_default}"
echo "  test_partition_time_guard=eligible only when FIIR_TIME_LIMIT is <= 00:30:00; normal GPU resource ranking still applies"
echo "  conda_env=${FIIR_CONDA_ENV}"
echo "  require_jax_gpu=${FIIR_REQUIRE_JAX_GPU}"
echo "  xla_python_client_preallocate=${XLA_PYTHON_CLIENT_PREALLOCATE}"
echo "  slurm_log_dir=${FIIR_SLURM_LOG_DIR}"
echo "  submit_script=${FIIR_SUBMIT_SCRIPT}"
echo "  plan_json=${FIIR_GPU_PLAN_JSON}"

printf 'planner command:'
printf ' %q' "${planner_args[@]}"
printf '\n'

planner_output="$("${planner_args[@]}")"
echo "$planner_output"

job_id="$(printf '%s\n' "$planner_output" | awk '/Submitted batch job/ { print $4; exit }')"
if [ -n "$job_id" ]; then
  echo "Startup monitor command:"
  echo "  scripts/slurm/monitor_slurm_startup.sh --job-id ${job_id}"
  echo "  For new templates, new environments, or new scales, use: scripts/slurm/monitor_slurm_startup.sh --job-id ${job_id} --seconds 300"
fi
