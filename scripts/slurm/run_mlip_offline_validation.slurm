#!/usr/bin/env bash
#SBATCH --job-name=fiir-mlip-validation
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

FIIR_MLIP_KIND="${FIIR_MLIP_KIND:-chgnet}"
FIIR_MLIP_OUTPUT_DIR="${FIIR_MLIP_OUTPUT_DIR:-outputs/mlip_validation_${FIIR_MLIP_KIND}_smoke}"
FIIR_MLIP_CANDIDATES_JSONL="${FIIR_MLIP_CANDIDATES_JSONL:-outputs/mlip_validation_mace_overnight_20260512_batch/selected_candidates.jsonl}"
FIIR_MLIP_AUDIT_INDEX="${FIIR_MLIP_AUDIT_INDEX:-outputs/mlip_validation_mace_overnight_20260512_batch/candidate_index.jsonl}"
FIIR_MLIP_LIMIT="${FIIR_MLIP_LIMIT:-8}"
FIIR_MLIP_DEVICE="${FIIR_MLIP_DEVICE:-cuda}"
FIIR_MLIP_WORKERS="${FIIR_MLIP_WORKERS:-${FIIR_TOTAL_GPUS:-1}}"
FIIR_MLIP_STRICT="${FIIR_MLIP_STRICT:-0}"
FIIR_MLIP_RELAX="${FIIR_MLIP_RELAX:-0}"
FIIR_MLIP_RELAX_CELL="${FIIR_MLIP_RELAX_CELL:-0}"
FIIR_MLIP_RELAX_STEPS="${FIIR_MLIP_RELAX_STEPS:-100}"
FIIR_MLIP_FMAX="${FIIR_MLIP_FMAX:-0.05}"
FIIR_MLIP_DERIVE_STABILITY_FROM_RELAXATION="${FIIR_MLIP_DERIVE_STABILITY_FROM_RELAXATION:-0}"
FIIR_MLIP_RELAXATION_STABILITY_FORCE_MAX="${FIIR_MLIP_RELAXATION_STABILITY_FORCE_MAX:-${FIIR_MLIP_FMAX}}"
FIIR_MLIP_RELAXATION_STABILITY_STRESS_MAX="${FIIR_MLIP_RELAXATION_STABILITY_STRESS_MAX:-}"
FIIR_MLIP_RELAXATION_STABILITY_ALLOW_UNCONVERGED="${FIIR_MLIP_RELAXATION_STABILITY_ALLOW_UNCONVERGED:-0}"

if [[ "${FIIR_MLIP_KIND}" == "matgl" ]]; then
  export FIIR_MATGL_HOME="${FIIR_MATGL_HOME:-${FIIR_MLIP_OUTPUT_DIR}/matgl_home}"
fi

if [[ -z "${FIIR_MLIP_VALIDATION_SOURCE+x}" ]]; then
  if [[ "${FIIR_MLIP_RELAX}" == "1" || "${FIIR_MLIP_RELAX}" == "true" ]]; then
    FIIR_MLIP_VALIDATION_SOURCE="local_mlip_${FIIR_MLIP_KIND}_relaxation"
  else
    FIIR_MLIP_VALIDATION_SOURCE="local_mlip_${FIIR_MLIP_KIND}_single_point"
  fi
fi

echo "FIIR external MLIP offline validation"
echo "  node=${SLURM_NODELIST:-local}"
echo "  conda_env=${FIIR_CONDA_ENV:-matgalaxy}"
echo "  mlip_kind=${FIIR_MLIP_KIND}"
echo "  candidates=${FIIR_MLIP_CANDIDATES_JSONL}"
echo "  output_dir=${FIIR_MLIP_OUTPUT_DIR}"
echo "  limit=${FIIR_MLIP_LIMIT}"
echo "  device=${FIIR_MLIP_DEVICE}"
echo "  workers=${FIIR_MLIP_WORKERS}"
echo "  strict=${FIIR_MLIP_STRICT}"
echo "  relax=${FIIR_MLIP_RELAX}"
echo "  relax_cell=${FIIR_MLIP_RELAX_CELL}"
echo "  validation_source=${FIIR_MLIP_VALIDATION_SOURCE}"
echo "  derive_stability_from_relaxation=${FIIR_MLIP_DERIVE_STABILITY_FROM_RELAXATION}"
echo "  FIIR_MATGL_HOME=${FIIR_MATGL_HOME:-}"
echo "  CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"

run_args=(
  "scripts/run_mlip_offline_validation.py"
  --mlip-kind "${FIIR_MLIP_KIND}" \
  --candidates-jsonl "${FIIR_MLIP_CANDIDATES_JSONL}" \
  --output-dir "${FIIR_MLIP_OUTPUT_DIR}" \
  --device "${FIIR_MLIP_DEVICE}" \
  --validation-source "${FIIR_MLIP_VALIDATION_SOURCE}" \
  --limit "${FIIR_MLIP_LIMIT}" \
  --workers "${FIIR_MLIP_WORKERS}"
)

if [[ -n "${FIIR_MLIP_MODEL_NAME:-}" ]]; then
  run_args+=(--model-name "${FIIR_MLIP_MODEL_NAME}")
fi

if [[ -n "${FIIR_MLIP_MODEL_PATH:-}" ]]; then
  run_args+=(--model-path "${FIIR_MLIP_MODEL_PATH}")
fi

if [[ -n "${FIIR_MLIP_VALIDATOR_NAME:-}" ]]; then
  run_args+=(--validator-name "${FIIR_MLIP_VALIDATOR_NAME}")
fi

if [[ "${FIIR_MLIP_STRICT}" == "1" || "${FIIR_MLIP_STRICT}" == "true" ]]; then
  run_args+=(--strict)
fi

if [[ "${FIIR_MLIP_RELAX}" == "1" || "${FIIR_MLIP_RELAX}" == "true" ]]; then
  run_args+=(--relax --relax-steps "${FIIR_MLIP_RELAX_STEPS}" --fmax "${FIIR_MLIP_FMAX}")
fi

if [[ "${FIIR_MLIP_RELAX_CELL}" == "1" || "${FIIR_MLIP_RELAX_CELL}" == "true" ]]; then
  run_args+=(--relax-cell)
fi

python "${run_args[@]}"

normalize_args=(
  "scripts/normalize_offline_validation_results.py"
  --input "${FIIR_MLIP_OUTPUT_DIR}/${FIIR_MLIP_KIND}_validation_results.jsonl" \
  --input-format jsonl \
  --output-jsonl "${FIIR_MLIP_OUTPUT_DIR}/normalized/validation_results.jsonl" \
  --output-summary "${FIIR_MLIP_OUTPUT_DIR}/normalized/normalization_summary.json" \
  --report "${FIIR_MLIP_OUTPUT_DIR}/normalized/report.md"
)

if [[ -n "${FIIR_MLIP_AUDIT_INDEX}" ]]; then
  normalize_args+=(--candidate-index "${FIIR_MLIP_AUDIT_INDEX}")
fi

if [[ "${FIIR_MLIP_DERIVE_STABILITY_FROM_RELAXATION}" == "1" || "${FIIR_MLIP_DERIVE_STABILITY_FROM_RELAXATION}" == "true" ]]; then
  normalize_args+=(--derive-stability-from-relaxation)
  normalize_args+=(--relaxation-stability-force-max "${FIIR_MLIP_RELAXATION_STABILITY_FORCE_MAX}")
  if [[ -n "${FIIR_MLIP_RELAXATION_STABILITY_STRESS_MAX}" ]]; then
    normalize_args+=(--relaxation-stability-stress-max "${FIIR_MLIP_RELAXATION_STABILITY_STRESS_MAX}")
  fi
  if [[ "${FIIR_MLIP_RELAXATION_STABILITY_ALLOW_UNCONVERGED}" == "1" || "${FIIR_MLIP_RELAXATION_STABILITY_ALLOW_UNCONVERGED}" == "true" ]]; then
    normalize_args+=(--relaxation-stability-allow-unconverged)
  fi
fi

python "${normalize_args[@]}"
