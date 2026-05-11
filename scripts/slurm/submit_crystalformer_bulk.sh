#!/bin/bash
#
# Policy-aware submitter for CrystalFormer bulk jobs.
# It selects one CPU node partition before calling sbatch:
# - <=30 minute jobs prefer an idle test node.
# - Otherwise use: regular256, regular128, regular6430, regular, test.
# - If no partition has idle nodes, queue on all partitions in that order.

set -eo pipefail

PARTITION_ORDER_DEFAULT="regular256 regular128 regular6430 regular test"

FIIR_SUBMIT_SCRIPT="${FIIR_SUBMIT_SCRIPT:-scripts/slurm/run_crystalformer_bulk_test.slurm}"
FIIR_PARTITION_ORDER="${FIIR_PARTITION_ORDER:-${PARTITION_ORDER_DEFAULT}}"
FIIR_SHORT_TASK_MINUTES="${FIIR_SHORT_TASK_MINUTES:-30}"
FIIR_EXPECTED_MINUTES="${FIIR_EXPECTED_MINUTES:-30}"
FIIR_TEST_PARTITION="${FIIR_TEST_PARTITION:-test}"
FIIR_DRY_RUN="${FIIR_DRY_RUN:-0}"
FIIR_FORCE_PARTITION="${FIIR_FORCE_PARTITION:-}"
FIIR_TIME_LIMIT="${FIIR_TIME_LIMIT:-}"
FIIR_SLURM_LOG_DIR="${FIIR_SLURM_LOG_DIR:-logs/slurm}"

normalize_partition_name() {
  local partition="$1"
  # sinfo marks the default partition with a trailing '*', for example
  # regular256*. The star is display-only and must not be passed to sbatch.
  printf '%s\n' "${partition%\*}"
}

partition_cores() {
  local partition
  partition="$(normalize_partition_name "$1")"
  case "$partition" in
    regular)
      printf '56\n'
      ;;
    *)
      printf '64\n'
      ;;
  esac
}

join_partitions() {
  local joined=""
  local partition
  for partition in $FIIR_PARTITION_ORDER; do
    partition="$(normalize_partition_name "$partition")"
    if [ -z "$joined" ]; then
      joined="$partition"
    else
      joined="${joined},${partition}"
    fi
  done
  printf '%s\n' "$joined"
}

idle_node_count() {
  local partition
  partition="$(normalize_partition_name "$1")"
  if ! command -v sinfo >/dev/null 2>&1; then
    printf '0\n'
    return
  fi
  sinfo -h -p "$partition" -t idle -o "%D" 2>/dev/null \
    | awk '{ total += $1 } END { print total + 0 }'
}

require_integer() {
  local name="$1"
  local value="$2"
  case "$value" in
    ''|*[!0-9]*)
      echo "${name} must be an integer number of minutes: ${value}" >&2
      exit 2
      ;;
  esac
}

require_integer "FIIR_EXPECTED_MINUTES" "$FIIR_EXPECTED_MINUTES"
require_integer "FIIR_SHORT_TASK_MINUTES" "$FIIR_SHORT_TASK_MINUTES"

FIIR_TEST_PARTITION="$(normalize_partition_name "$FIIR_TEST_PARTITION")"
FIIR_FORCE_PARTITION="$(normalize_partition_name "$FIIR_FORCE_PARTITION")"

concurrency_warning=""
case "${FIIR_MAX_CONCURRENT_GENERATIONS:-auto}" in
  ''|auto|AUTO|none|None)
    ;;
  *[!0-9]*)
    ;;
  *)
    if [ "$FIIR_EXPECTED_MINUTES" -gt "$FIIR_SHORT_TASK_MINUTES" ] \
      && [ "$FIIR_MAX_CONCURRENT_GENERATIONS" -gt 8 ]; then
      concurrency_warning="long_job_high_concurrency_may_oversubscribe_jax_threads:FIIR_MAX_CONCURRENT_GENERATIONS=${FIIR_MAX_CONCURRENT_GENERATIONS}; prefer 8 unless benchmarked"
    fi
    ;;
esac

selected_partition=""
selected_reason=""

if [ -n "$FIIR_FORCE_PARTITION" ]; then
  selected_partition="$FIIR_FORCE_PARTITION"
  selected_reason="forced"
elif [ "$FIIR_EXPECTED_MINUTES" -le "$FIIR_SHORT_TASK_MINUTES" ] \
  && [ "$(idle_node_count "$FIIR_TEST_PARTITION")" -gt 0 ]; then
  selected_partition="$FIIR_TEST_PARTITION"
  selected_reason="short_job_idle_test"
else
  for partition in $FIIR_PARTITION_ORDER; do
    partition="$(normalize_partition_name "$partition")"
    if [ "$(idle_node_count "$partition")" -gt 0 ]; then
      selected_partition="$partition"
      selected_reason="first_idle_in_policy_order"
      break
    fi
  done
fi

if [ -n "$selected_partition" ]; then
  partition_arg="$selected_partition"
  cores="$(partition_cores "$selected_partition")"
  export_arg="ALL,FIIR_TOTAL_CPU_CORES=${cores}"
  ntasks_args=(--ntasks-per-node "$cores")
else
  partition_arg="$(join_partitions)"
  cores="auto"
  export_arg="ALL"
  ntasks_args=()
  selected_reason="no_idle_queue_all_policy_partitions"
fi

sbatch_args=(
  --nodes 1
  --exclusive
  --partition "$partition_arg"
  --export "$export_arg"
)

if [ "${#ntasks_args[@]}" -gt 0 ]; then
  sbatch_args+=("${ntasks_args[@]}")
fi

if [ -n "$FIIR_TIME_LIMIT" ]; then
  sbatch_args+=(--time "$FIIR_TIME_LIMIT")
fi

mkdir -p "$FIIR_SLURM_LOG_DIR"
sbatch_args+=(--output "${FIIR_SLURM_LOG_DIR}/%x_%j.log")
sbatch_args+=(--error "${FIIR_SLURM_LOG_DIR}/%x_%j.err")

echo "FIIR partition policy:"
echo "  expected_minutes=${FIIR_EXPECTED_MINUTES}"
echo "  short_task_minutes=${FIIR_SHORT_TASK_MINUTES}"
echo "  partition_order=${FIIR_PARTITION_ORDER}"
echo "  selected_partition=${partition_arg}"
echo "  selected_reason=${selected_reason}"
echo "  selected_core_budget=${cores}"
echo "  slurm_log_dir=${FIIR_SLURM_LOG_DIR}"
echo "  submit_script=${FIIR_SUBMIT_SCRIPT}"
if [ -n "$concurrency_warning" ]; then
  echo "  concurrency_warning=${concurrency_warning}"
fi

printf 'sbatch command:'
printf ' %q' sbatch "${sbatch_args[@]}" "$FIIR_SUBMIT_SCRIPT"
printf '\n'

if [ "$FIIR_DRY_RUN" = "1" ] || [ "$FIIR_DRY_RUN" = "true" ]; then
  exit 0
fi

submit_output="$(sbatch "${sbatch_args[@]}" "$FIIR_SUBMIT_SCRIPT")"
echo "$submit_output"

job_id="$(printf '%s\n' "$submit_output" | awk '/Submitted batch job/ { print $4; exit }')"
if [ -n "$job_id" ]; then
  echo "Startup monitor command:"
  echo "  scripts/slurm/monitor_slurm_startup.sh --job-id ${job_id}"
  echo "  For new templates, new environments, or new scales, use: scripts/slurm/monitor_slurm_startup.sh --job-id ${job_id} --seconds 300"
fi
