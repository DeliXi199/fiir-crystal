#!/usr/bin/env bash
#SBATCH --job-name=fiir-mace-validation
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err

set -eo pipefail

cd "${FIIR_PROJECT_ROOT:-/data/home/yihaoxu/research/projects/fiir-crystal}"
mkdir -p logs/slurm

if [[ -f "${HOME}/.bashrc" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.bashrc"
fi

if command -v conda >/dev/null 2>&1; then
  conda activate "${FIIR_CONDA_ENV:-matgalaxy}"
fi

export MPLCONFIGDIR="${FIIR_MPLCONFIGDIR:-/tmp/fiir_mplconfig_${SLURM_JOB_ID:-local}}"
mkdir -p "${MPLCONFIGDIR}"

FIIR_MACE_OUTPUT_DIR="${FIIR_MACE_OUTPUT_DIR:-outputs/mlip_validation_mace_smoke}"
FIIR_MACE_CANDIDATES_JSONL="${FIIR_MACE_CANDIDATES_JSONL:-outputs/crystalformer_bulk_gpu_smoke_perovskite_3x20/smoke/crystalformer_audit/BaTiO3/candidates.jsonl}"
FIIR_MACE_AUDIT_INDEX="${FIIR_MACE_AUDIT_INDEX:-outputs/crystalformer_bulk_gpu_smoke_perovskite_3x20/smoke/crystalformer_audit/BaTiO3/audit_candidates.jsonl}"
FIIR_MACE_LIMIT="${FIIR_MACE_LIMIT:-8}"
FIIR_MACE_DEVICE="${FIIR_MACE_DEVICE:-cuda}"
FIIR_MACE_DEFAULT_DTYPE="${FIIR_MACE_DEFAULT_DTYPE:-float32}"
FIIR_MACE_WORKERS="${FIIR_MACE_WORKERS:-${FIIR_TOTAL_GPUS:-1}}"
FIIR_MACE_STRICT="${FIIR_MACE_STRICT:-0}"
FIIR_MACE_RELAX="${FIIR_MACE_RELAX:-0}"
FIIR_MACE_RELAX_STEPS="${FIIR_MACE_RELAX_STEPS:-100}"
FIIR_MACE_FMAX="${FIIR_MACE_FMAX:-0.05}"

echo "FIIR MACE offline validation"
echo "  node=${SLURM_NODELIST:-local}"
echo "  conda_env=${FIIR_CONDA_ENV:-matgalaxy}"
echo "  candidates=${FIIR_MACE_CANDIDATES_JSONL}"
echo "  output_dir=${FIIR_MACE_OUTPUT_DIR}"
echo "  limit=${FIIR_MACE_LIMIT}"
echo "  device=${FIIR_MACE_DEVICE}"
echo "  default_dtype=${FIIR_MACE_DEFAULT_DTYPE}"
echo "  workers=${FIIR_MACE_WORKERS}"
echo "  strict=${FIIR_MACE_STRICT}"
echo "  relax=${FIIR_MACE_RELAX}"
echo "  CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"

run_args=(
  "scripts/run_mace_offline_validation.py"
  --candidates-jsonl "${FIIR_MACE_CANDIDATES_JSONL}" \
  --output-jsonl "${FIIR_MACE_OUTPUT_DIR}/mace_validation_results.jsonl" \
  --output-summary "${FIIR_MACE_OUTPUT_DIR}/mace_validation_summary.json" \
  --report "${FIIR_MACE_OUTPUT_DIR}/report.md" \
  --device "${FIIR_MACE_DEVICE}" \
  --default-dtype "${FIIR_MACE_DEFAULT_DTYPE}" \
  --limit "${FIIR_MACE_LIMIT}" \
  --workers "${FIIR_MACE_WORKERS}"
)

if [[ "${FIIR_MACE_STRICT}" == "1" || "${FIIR_MACE_STRICT}" == "true" ]]; then
  run_args+=(--strict)
fi

if [[ "${FIIR_MACE_RELAX}" == "1" || "${FIIR_MACE_RELAX}" == "true" ]]; then
  run_args+=(--relax --relax-steps "${FIIR_MACE_RELAX_STEPS}" --fmax "${FIIR_MACE_FMAX}")
fi

python "${run_args[@]}"

normalize_args=(
  "scripts/normalize_offline_validation_results.py"
  --input "${FIIR_MACE_OUTPUT_DIR}/mace_validation_results.jsonl" \
  --input-format jsonl \
  --output-jsonl "${FIIR_MACE_OUTPUT_DIR}/normalized/validation_results.jsonl" \
  --output-summary "${FIIR_MACE_OUTPUT_DIR}/normalized/normalization_summary.json" \
  --report "${FIIR_MACE_OUTPUT_DIR}/normalized/report.md"
)

if [[ -n "${FIIR_MACE_AUDIT_INDEX}" ]]; then
  normalize_args+=(--candidate-index "${FIIR_MACE_AUDIT_INDEX}")
fi

python "${normalize_args[@]}"
