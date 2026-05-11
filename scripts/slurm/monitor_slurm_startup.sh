#!/bin/bash
#
# Watch only the startup window of a longer SLURM job.
#
# Policy:
# - Stable long jobs: watch the first 120 seconds by default.
# - New templates, new environments, or new scales: watch up to 300 seconds.
# - If the job is running and stderr stays empty after the startup window,
#   leave the job to SLURM and inspect summary artifacts later.

set -eo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/slurm/monitor_slurm_startup.sh --job-id JOB_ID [options]

Options:
  --job-id JOB_ID       SLURM job id to monitor.
  --seconds N           Startup window in seconds. Default: 120, capped at 300.
  --interval N          Seconds between checks. Default: 30.
  --log-dir PATH        SLURM log directory. Default: logs/slurm.
  --tail-lines N        Lines of stdout/stderr to show per check. Default: 30.
  --no-fail-on-stderr   Do not return a failure when stderr is non-empty.
  --help                Show this help.

Environment equivalents:
  FIIR_JOB_ID
  FIIR_STARTUP_MONITOR_SECONDS
  FIIR_STARTUP_MONITOR_MAX_SECONDS
  FIIR_STARTUP_MONITOR_INTERVAL_SECONDS
  FIIR_STARTUP_MONITOR_TAIL_LINES
  FIIR_STARTUP_MONITOR_FAIL_ON_STDERR
  FIIR_SLURM_LOG_DIR
EOF
}

job_id="${FIIR_JOB_ID:-}"
monitor_seconds="${FIIR_STARTUP_MONITOR_SECONDS:-120}"
max_seconds="${FIIR_STARTUP_MONITOR_MAX_SECONDS:-300}"
interval_seconds="${FIIR_STARTUP_MONITOR_INTERVAL_SECONDS:-30}"
tail_lines="${FIIR_STARTUP_MONITOR_TAIL_LINES:-30}"
fail_on_stderr="${FIIR_STARTUP_MONITOR_FAIL_ON_STDERR:-1}"
log_dir="${FIIR_SLURM_LOG_DIR:-logs/slurm}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --job-id)
      job_id="${2:-}"
      shift 2
      ;;
    --seconds)
      monitor_seconds="${2:-}"
      shift 2
      ;;
    --interval)
      interval_seconds="${2:-}"
      shift 2
      ;;
    --log-dir)
      log_dir="${2:-}"
      shift 2
      ;;
    --tail-lines)
      tail_lines="${2:-}"
      shift 2
      ;;
    --no-fail-on-stderr)
      fail_on_stderr="0"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_integer() {
  local name="$1"
  local value="$2"
  case "$value" in
    ''|*[!0-9]*)
      echo "${name} must be a non-negative integer: ${value}" >&2
      exit 2
      ;;
  esac
}

if [ -z "$job_id" ]; then
  echo "Missing required --job-id or FIIR_JOB_ID." >&2
  usage >&2
  exit 2
fi

require_integer "FIIR_STARTUP_MONITOR_SECONDS" "$monitor_seconds"
require_integer "FIIR_STARTUP_MONITOR_MAX_SECONDS" "$max_seconds"
require_integer "FIIR_STARTUP_MONITOR_INTERVAL_SECONDS" "$interval_seconds"
require_integer "FIIR_STARTUP_MONITOR_TAIL_LINES" "$tail_lines"

if [ "$monitor_seconds" -gt "$max_seconds" ]; then
  echo "Requested startup monitor window ${monitor_seconds}s exceeds cap ${max_seconds}s; using ${max_seconds}s."
  monitor_seconds="$max_seconds"
fi

if [ "$interval_seconds" -eq 0 ]; then
  interval_seconds=1
fi

find_log_file() {
  local suffix="$1"
  if [ ! -d "$log_dir" ]; then
    return 0
  fi
  find "$log_dir" -maxdepth 1 -type f \
    \( -name "*_${job_id}.${suffix}" -o -name "slurm_${job_id}.${suffix}" -o -name "slurm-${job_id}.${suffix}" \) \
    | sort \
    | tail -n 1
}

queue_line() {
  if ! command -v squeue >/dev/null 2>&1; then
    echo "squeue_unavailable"
    return 0
  fi
  squeue -h -j "$job_id" -o "%i|%T|%M|%N|%R" 2>/dev/null || true
}

print_file_tail() {
  local label="$1"
  local path="$2"
  if [ -z "$path" ] || [ ! -f "$path" ]; then
    echo "${label}: not_found"
    return
  fi
  echo "${label}: ${path}"
  tail -n "$tail_lines" "$path"
}

start_epoch="$(date +%s)"
iteration=1

echo "FIIR SLURM startup monitor:"
echo "  job_id=${job_id}"
echo "  monitor_seconds=${monitor_seconds}"
echo "  interval_seconds=${interval_seconds}"
echo "  max_seconds=${max_seconds}"
echo "  log_dir=${log_dir}"
echo "  fail_on_stderr=${fail_on_stderr}"

while true; do
  now_epoch="$(date +%s)"
  elapsed=$((now_epoch - start_epoch))
  queue_status="$(queue_line)"
  stdout_path="$(find_log_file log)"
  stderr_path="$(find_log_file err)"

  echo ""
  echo "startup_check iteration=${iteration} elapsed_seconds=${elapsed}"
  if [ -n "$queue_status" ]; then
    echo "squeue: ${queue_status}"
  else
    echo "squeue: job_not_listed"
  fi

  print_file_tail "stdout_tail" "$stdout_path"

  if [ -n "$stderr_path" ] && [ -s "$stderr_path" ]; then
    print_file_tail "stderr_tail" "$stderr_path"
    if [ "$fail_on_stderr" = "1" ] || [ "$fail_on_stderr" = "true" ]; then
      echo "Startup monitor found non-empty stderr; inspect the job before leaving it unattended." >&2
      exit 1
    fi
  else
    echo "stderr_tail: empty"
  fi

  if [ -z "$queue_status" ]; then
    echo "Job is no longer listed by squeue during startup monitoring."
    echo "Inspect stdout/stderr and the expected output summary before assuming success."
    exit 0
  fi

  if [ "$elapsed" -ge "$monitor_seconds" ]; then
    echo "Startup monitor window passed with the job still listed and stderr empty."
    echo "Leave the job to SLURM and inspect summary artifacts afterward."
    exit 0
  fi

  sleep "$interval_seconds"
  iteration=$((iteration + 1))
done
