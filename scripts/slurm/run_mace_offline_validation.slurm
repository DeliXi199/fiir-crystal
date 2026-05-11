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
FIIR_MACE_WORKERS="${FIIR_MACE_WORKERS:-${FIIR_TOTAL_GPUS:-1}}"

echo "FIIR MACE offline validation"
echo "  node=${SLURM_NODELIST:-local}"
echo "  conda_env=${FIIR_CONDA_ENV:-matgalaxy}"
echo "  candidates=${FIIR_MACE_CANDIDATES_JSONL}"
echo "  output_dir=${FIIR_MACE_OUTPUT_DIR}"
echo "  limit=${FIIR_MACE_LIMIT}"
echo "  device=${FIIR_MACE_DEVICE}"
echo "  workers=${FIIR_MACE_WORKERS}"
echo "  CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"

python scripts/run_mace_offline_validation.py \
  --candidates-jsonl "${FIIR_MACE_CANDIDATES_JSONL}" \
  --output-jsonl "${FIIR_MACE_OUTPUT_DIR}/mace_validation_results.jsonl" \
  --output-summary "${FIIR_MACE_OUTPUT_DIR}/mace_validation_summary.json" \
  --report "${FIIR_MACE_OUTPUT_DIR}/report.md" \
  --device "${FIIR_MACE_DEVICE}" \
  --limit "${FIIR_MACE_LIMIT}" \
  --workers "${FIIR_MACE_WORKERS}" \
  --strict

python scripts/normalize_offline_validation_results.py \
  --input "${FIIR_MACE_OUTPUT_DIR}/mace_validation_results.jsonl" \
  --input-format jsonl \
  --output-jsonl "${FIIR_MACE_OUTPUT_DIR}/normalized/validation_results.jsonl" \
  --output-summary "${FIIR_MACE_OUTPUT_DIR}/normalized/normalization_summary.json" \
  --report "${FIIR_MACE_OUTPUT_DIR}/normalized/report.md" \
  --candidate-index "${FIIR_MACE_AUDIT_INDEX}"
