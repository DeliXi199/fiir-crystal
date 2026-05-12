#!/bin/bash
#
# Submit from the fiir-crystal repository root with the GPU policy wrapper:
#   FIIR_SUBMIT_SCRIPT=scripts/slurm/run_crystalformer_dpo_smoke.slurm \
#   FIIR_JOB_NAME=fiir-cf-dpo-smoke \
#   FIIR_TIME_LIMIT=00:30:00 \
#   bash scripts/slurm/submit_crystalformer_bulk_gpu.sh
#
# This script runs an already prepared non-overwriting DPO smoke command. It
# uses the base checkpoint only through --restore_path; the after checkpoint is
# written under the prepared output directory.
#
# Useful overrides:
#   FIIR_DPO_RUN_SCRIPT=outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/run_training.sh
#   FIIR_CONDA_ENV=crystalformer
#   FIIR_REQUIRE_JAX_GPU=1
#   FIIR_MODULES="cuda/12.1"
#
#SBATCH --account=hmt03
#SBATCH --nodes=1
#SBATCH --partition=test
#SBATCH --job-name=fiir-cf-dpo-smoke
#SBATCH --output=logs/slurm/%x_%j.log
#SBATCH --error=logs/slurm/%x_%j.err

set -eo pipefail

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export MV2_ENABLE_AFFINITY="${MV2_ENABLE_AFFINITY:-0}"
export XLA_PYTHON_CLIENT_PREALLOCATE="${XLA_PYTHON_CLIENT_PREALLOCATE:-false}"
export JAX_PLATFORMS="${JAX_PLATFORMS:-cuda,cpu}"

echo "The current job ID is ${SLURM_JOB_ID:-local}"
echo "Running on ${SLURM_JOB_NUM_NODES:-1} nodes:"
echo "${SLURM_JOB_NODELIST:-localhost}"
echo "Using ${SLURM_CPUS_ON_NODE:-${SLURM_NTASKS_PER_NODE:-1}} CPU cores on node"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
echo "FIIR_TOTAL_GPUS=${FIIR_TOTAL_GPUS:-unset}"

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
FIIR_DPO_RUN_SCRIPT="${FIIR_DPO_RUN_SCRIPT:-outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/run_training.sh}"
FIIR_REQUIRE_JAX_GPU="${FIIR_REQUIRE_JAX_GPU:-1}"

if [ ! -f "${FIIR_DPO_RUN_SCRIPT}" ]; then
  echo "DPO run script does not exist: ${FIIR_DPO_RUN_SCRIPT}" >&2
  exit 2
fi

if [ "${FIIR_REQUIRE_JAX_GPU}" = "1" ] || [ "${FIIR_REQUIRE_JAX_GPU}" = "true" ]; then
  echo "FIIR_REQUIRE_JAX_GPU is enabled; checking JAX CUDA backend before DPO smoke."
  "${FIIR_PYTHON}" - <<'PY'
import jax
import jaxlib

backend = jax.default_backend()
devices = jax.devices()
print(f"jax={jax.__version__}")
print(f"jaxlib={jaxlib.__version__}")
print(f"jax_default_backend={backend}")
print(f"jax_devices={devices}")
if backend != "gpu":
    raise SystemExit("JAX default backend is not gpu")
if not any(getattr(device, "platform", "") == "gpu" for device in devices):
    raise SystemExit("JAX did not report any GPU devices")
PY
fi

echo "CrystalFormer DPO smoke starts at $(date)"
echo "Run script: ${FIIR_DPO_RUN_SCRIPT}"
bash "${FIIR_DPO_RUN_SCRIPT}"
echo "CrystalFormer DPO smoke ends at $(date)"
