#!/bin/bash
#
# Submit from the fiir-crystal repository root with the policy wrapper:
#   bash scripts/slurm/submit_crystalformer_bulk.sh
#
# Direct sbatch is also supported:
#   sbatch scripts/slurm/run_crystalformer_bulk_test.slurm
#
# By default this creates a bulk-generation plan only. To validate paths and
# commands without running generation or smoke:
#   FIIR_VALIDATE_ONLY=1 sbatch scripts/slurm/run_crystalformer_bulk_test.slurm
#
# To execute generation:
#   FIIR_RUN_GENERATION=1 sbatch scripts/slurm/run_crystalformer_bulk_test.slurm
#
# Useful overrides:
#   FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real.example.json
#   FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke
#   FIIR_ONLY_FORMULA=BaTiO3
#   FIIR_CONDA_ENV=crystalformer
#   FIIR_MAX_CONCURRENT_GENERATIONS=auto
#   FIIR_GENERATION_CPU_THREADS=auto
#   FIIR_MODULES="cuda/12.1"
#
#SBATCH --account=hmt03
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --partition=test
#SBATCH --job-name=fiir-cf-test
#SBATCH --output=./slurm_%x_%j.log
#SBATCH --error=./slurm_%x_%j.err

set -eo pipefail

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export MV2_ENABLE_AFFINITY="${MV2_ENABLE_AFFINITY:-0}"

echo "The current job ID is ${SLURM_JOB_ID:-local}"
echo "Running on ${SLURM_JOB_NUM_NODES:-1} nodes:"
echo "${SLURM_JOB_NODELIST:-localhost}"
echo "Using ${SLURM_CPUS_ON_NODE:-${SLURM_NTASKS_PER_NODE:-1}} CPU cores on node"
echo "Using ${SLURM_NTASKS_PER_NODE:-1} tasks per node"
echo "A total of ${SLURM_NTASKS:-1} tasks is used"

if [ -f "${HOME}/.bashrc" ]; then
  # shellcheck disable=SC1090
  source "${HOME}/.bashrc"
fi

set -u

ulimit -s unlimited
ulimit -c unlimited

if command -v module >/dev/null 2>&1 && [ -n "${FIIR_MODULES:-}" ]; then
  for module_name in ${FIIR_MODULES}; do
    echo "Loading module: ${module_name}"
    module load "${module_name}"
  done
fi

if [ -n "${FIIR_CONDA_ENV:-}" ]; then
  echo "Activating conda environment: ${FIIR_CONDA_ENV}"
  set +u
  conda activate "${FIIR_CONDA_ENV}"
  set -u
fi

if [ -n "${FIIR_VENV:-}" ]; then
  echo "Activating virtualenv: ${FIIR_VENV}"
  set +u
  # shellcheck disable=SC1090
  source "${FIIR_VENV}/bin/activate"
  set -u
fi

cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
echo "Working directory: $(pwd)"

FIIR_PYTHON="${FIIR_PYTHON:-python}"
FIIR_BULK_CONFIG="${FIIR_BULK_CONFIG:-configs/crystalformer_bulk_generation.json}"
FIIR_OUTPUT_ROOT="${FIIR_OUTPUT_ROOT:-outputs/crystalformer_bulk_slurm_${SLURM_JOB_ID:-local}}"
FIIR_ONLY_FORMULA="${FIIR_ONLY_FORMULA:-}"
FIIR_VALIDATE_ONLY="${FIIR_VALIDATE_ONLY:-0}"
FIIR_RUN_GENERATION="${FIIR_RUN_GENERATION:-0}"
FIIR_CONTINUE_ON_ERROR="${FIIR_CONTINUE_ON_ERROR:-0}"
FIIR_SKIP_EXISTING_MODE="${FIIR_SKIP_EXISTING_MODE:-default}"
FIIR_TOTAL_CPU_CORES="${FIIR_TOTAL_CPU_CORES:-}"
FIIR_MAX_CONCURRENT_GENERATIONS="${FIIR_MAX_CONCURRENT_GENERATIONS:-auto}"
FIIR_GENERATION_CPU_THREADS="${FIIR_GENERATION_CPU_THREADS:-auto}"

if [ -n "${SLURM_CPUS_ON_NODE:-}" ]; then
  ncpu="${SLURM_CPUS_ON_NODE}"
else
  ncpu=$((${SLURM_JOB_NUM_NODES:-1} * ${SLURM_NTASKS_PER_NODE:-1}))
fi
if [ -z "${FIIR_TOTAL_CPU_CORES}" ]; then
  FIIR_TOTAL_CPU_CORES="${ncpu}"
fi
echo "Computed ncpu=${ncpu}"
echo "FIIR_TOTAL_CPU_CORES=${FIIR_TOTAL_CPU_CORES}"
echo "FIIR_MAX_CONCURRENT_GENERATIONS=${FIIR_MAX_CONCURRENT_GENERATIONS}"
echo "FIIR_GENERATION_CPU_THREADS=${FIIR_GENERATION_CPU_THREADS}"
echo "CrystalFormer bulk orchestration starts at $(date)"

cmd=(
  "${FIIR_PYTHON}"
  "scripts/run_crystalformer_bulk_generation.py"
  "--config"
  "${FIIR_BULK_CONFIG}"
  "--output-root"
  "${FIIR_OUTPUT_ROOT}"
  "--total-cpu-cores"
  "${FIIR_TOTAL_CPU_CORES}"
)

if [ "${FIIR_MAX_CONCURRENT_GENERATIONS}" != "auto" ]; then
  cmd+=("--max-concurrent-generations" "${FIIR_MAX_CONCURRENT_GENERATIONS}")
fi

if [ "${FIIR_GENERATION_CPU_THREADS}" != "auto" ]; then
  cmd+=("--generation-cpu-threads" "${FIIR_GENERATION_CPU_THREADS}")
fi

if [ -n "${FIIR_ONLY_FORMULA}" ]; then
  cmd+=("--only-formula" "${FIIR_ONLY_FORMULA}")
fi

if [ "${FIIR_VALIDATE_ONLY}" = "1" ] || [ "${FIIR_VALIDATE_ONLY}" = "true" ]; then
  cmd+=("--validate-only")
  echo "FIIR_VALIDATE_ONLY is enabled; this job will only validate and expand the bulk plan."
elif [ "${FIIR_RUN_GENERATION}" = "1" ] || [ "${FIIR_RUN_GENERATION}" = "true" ]; then
  cmd+=("--run-generation")
else
  echo "FIIR_RUN_GENERATION is not enabled; this job will only write a bulk plan."
fi

if [ "${FIIR_CONTINUE_ON_ERROR}" = "1" ] || [ "${FIIR_CONTINUE_ON_ERROR}" = "true" ]; then
  cmd+=("--continue-on-error")
fi

case "${FIIR_SKIP_EXISTING_MODE}" in
  default)
    ;;
  skip)
    cmd+=("--skip-existing")
    ;;
  no-skip)
    cmd+=("--no-skip-existing")
    ;;
  *)
    echo "Unsupported FIIR_SKIP_EXISTING_MODE=${FIIR_SKIP_EXISTING_MODE}; use default, skip, or no-skip." >&2
    exit 2
    ;;
esac

printf 'Command:'
printf ' %q' "${cmd[@]}"
printf '\n'

"${cmd[@]}"

echo "CrystalFormer bulk orchestration ends at $(date)"
