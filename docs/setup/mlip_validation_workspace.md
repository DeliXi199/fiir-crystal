# MLIP Validation Workspace Setup

FIIR Crystal treats MLIP validation as an optional external workflow. The core
`fiir_crystal` package remains standard-library only and does not install,
import, run, or download MACE, CHGNet, MatGL, ASE, pymatgen, torch, checkpoints,
or datasets.

## Recommended Layout

```text
fiir-crystal/
  fiir_crystal/
  configs/mlip_validation.example.json
  examples/mlip_validation/
  outputs/mlip_validation_dry_run/
  outputs/mlip_validation_mace/
  outputs/mlip_validation_chgnet/
  outputs/offline_validation_normalized/
```

Use a separate environment for real MLIP tools. Keep generated validation
outputs under `outputs/`; those files are local artifacts and are not committed.

## Boundary

The `fiir_crystal` core package prepares and normalizes evidence only; it does
not run MACE, CHGNet, MatGL, or any other validator:

- the core package does not run MACE;
- no MLIP execution inside FIIR core;
- no DFT execution;
- no model training;
- no external API calls;
- no checkpoint or dataset downloads from FIIR scripts;
- no writes into live CrystalFormer generation directories.

F3 remains unavailable or unknown until local validation evidence is imported.
A single MLIP result should be treated as low-confidence evidence
(`tier3_single_mlip`), while an ensemble result can become
`tier2_mlip_ensemble` only when the validators agree and the run metadata makes
that explicit. DFT-confirmed evidence is the intended `tier1_dft` source, but
DFT is out of scope for this local setup step.

## Dry-Run Plan

After collecting CrystalFormer outputs, prepare a dry-run MLIP plan:

```bash
python scripts/run_local_mlip_validation.py \
  --config configs/mlip_validation.example.json \
  --candidate-index outputs/crystalformer_audit/BaTiO3/audit_candidates.jsonl \
  --output-dir outputs/mlip_validation_dry_run
```

The script writes:

- `mlip_validation_plan.json`
- `mlip_validation_summary.json`
- `report.md`

It does not import MLIP packages and does not run calculations. If
`--run-mlip` is supplied today, the script exits with a clear boundary error.

## GPU Scheduling Plan

Before launching real local MLIP calculations on SLURM, use the GPU planner to
select a node with available resources. The planner is read-only unless
`--run-sbatch` is explicitly supplied. It checks SLURM node state, filters to
CUDA-compatible GPU partitions by default, ranks eligible nodes by
`free_gpus * tf32_gpu_weight`, then emits an `sbatch` command that requests all
currently free GPUs and CPUs on the selected node. CPU and memory settings are
eligibility filters and request sizing inputs, not default ranking signals.

```bash
python scripts/slurm/plan_slurm_job.py \
  --kind gpu \
  --accelerator cuda \
  --job-name fiir-mlip-gpu-smoke \
  --time 00:30:00 \
  --submit-script scripts/slurm/run_mlip_gpu_smoke.slurm \
  --output-json outputs/slurm_gpu_plans/mlip_gpu_smoke_plan.json
```

For an idle node, the generated command includes `--exclusive` and uses the
whole node. For a partially used `MIXED` node, it requests only the remaining
free GPU and CPU resources. The selected job receives `FIIR_TOTAL_GPUS`,
`FIIR_TOTAL_CPU_CORES`, `FIIR_GPU_NODE`, `FIIR_GPU_PARTITION`, and
`FIIR_GPU_GRES` in its environment so downstream runners can size worker pools
without hard-coded node assumptions.

## Suggested Install Order For Later

Install one validator at a time in a separate environment:

1. MACE, using an explicit model name such as `mace_mpa_0`.
2. CHGNet, using an explicit checkpoint name such as `0.3.0`.
3. MatGL/M3GNet, after confirming backend and version compatibility.

Do not add these packages to `pyproject.toml`. Do not make tests depend on
them.

## Expected Local Result Rows

Real MLIP runners should emit JSONL or CSV rows that can be normalized by
`scripts/normalize_offline_validation_results.py`. Example fields:

```json
{
  "candidate_id": "cf_001",
  "formula": "BaTiO3",
  "validator": "mace_mpa_0",
  "validation_source": "local_mlip_mace_mpa_0",
  "validation_status": "completed",
  "energy_above_hull": 0.03,
  "formation_energy": -2.1,
  "relaxed": true,
  "relaxation_converged": true,
  "force_max": 0.04,
  "stress_max": 0.8,
  "uncertainty": null,
  "calibration_tier": "tier3_single_mlip",
  "source_checkpoint": "local-crystalformer-checkpoint-id",
  "generation_condition": {
    "source_checkpoint": "local-crystalformer-checkpoint-id",
    "temperature": "1.0",
    "top_k": "40",
    "K": "40"
  },
  "metadata": {
    "mlip_package_version": "record-explicitly",
    "mlip_model_name": "record-explicitly"
  }
}
```

Failed or incomplete rows should remain explicit:

```json
{
  "candidate_id": "cf_002",
  "formula": "BaTiO3",
  "validator": "mace_mpa_0",
  "validation_source": "local_mlip_mace_mpa_0",
  "validation_status": "failed",
  "energy_above_hull": null,
  "relaxed": false,
  "relaxation_converged": false,
  "calibration_tier": "unknown",
  "error_reason": "relaxation did not converge",
  "metadata": {}
}
```

Normalize local result files with:

```bash
python scripts/normalize_offline_validation_results.py \
  --input outputs/mlip_validation_mace/mace_validation_results.jsonl \
  --input-format auto \
  --output-jsonl outputs/offline_validation_normalized/validation_results.jsonl \
  --output-summary outputs/offline_validation_normalized/normalization_summary.json \
  --report outputs/offline_validation_normalized/report.md \
  --candidate-index outputs/crystalformer_audit/BaTiO3/audit_candidates.jsonl
```

Then run the existing offline validation import check before any F3-aware audit
or DPO handoff uses the evidence.

## Local MACE Smoke Runner

For a small local-only MACE inference smoke, use the optional script outside the
core package. It reads existing candidate JSONL files and a local MACE model
file, then writes local MLIP energy/force evidence. It does not generate new
CrystalFormer candidates, train models, run DFT, call external APIs, or
download models. To prevent implicit model download, pass a local model path or
set `FIIR_MACE_MODEL_PATH`.

Single-process dry-run:

```bash
python scripts/run_mace_offline_validation.py \
  --candidates-jsonl outputs/crystalformer_bulk_gpu_smoke_perovskite_3x20/smoke/crystalformer_audit/BaTiO3/candidates.jsonl \
  --output-jsonl outputs/mlip_validation_mace_smoke_dryrun/mace_validation_results.jsonl \
  --output-summary outputs/mlip_validation_mace_smoke_dryrun/mace_validation_summary.json \
  --report outputs/mlip_validation_mace_smoke_dryrun/report.md \
  --limit 3 \
  --dry-run
```

Policy-aware GPU smoke through the unified scheduler:

```bash
env \
  FIIR_CONDA_ENV=matgalaxy \
  FIIR_MACE_OUTPUT_DIR=outputs/mlip_validation_mace_gpu_smoke_BaTiO3_8 \
  FIIR_MACE_CANDIDATES_JSONL=outputs/crystalformer_bulk_gpu_smoke_perovskite_3x20/smoke/crystalformer_audit/BaTiO3/candidates.jsonl \
  FIIR_MACE_AUDIT_INDEX=outputs/crystalformer_bulk_gpu_smoke_perovskite_3x20/smoke/crystalformer_audit/BaTiO3/audit_candidates.jsonl \
  FIIR_MACE_LIMIT=8 \
  FIIR_MACE_DEVICE=cuda \
  python scripts/slurm/plan_slurm_job.py \
    --kind gpu \
    --accelerator cuda \
    --job-name fiir-mace-smoke \
    --account hmt03 \
    --time 00:10:00 \
    --submit-script scripts/slurm/run_mace_offline_validation.slurm \
    --output-json outputs/slurm_gpu_plans/mace_validation_smoke_submit_plan.json \
    --run-sbatch
```

The SLURM wrapper uses `FIIR_TOTAL_GPUS` from the GPU scheduler as the default
worker count, so a full 8-GPU RTX4090 node runs eight MACE workers. The
normalized output is written under:

```text
outputs/mlip_validation_mace_gpu_smoke_BaTiO3_8/normalized/validation_results.jsonl
```

Important F3 boundary: this smoke runner does not compute a hull or compare
against local reference phases. It leaves `energy_above_hull`, `formation_energy`,
and `is_stable` as null. The output is MLIP energy/force evidence, not a stable
F3 label. F3 remains unavailable until a local hull/reference workflow or other
explicit offline validation evidence supplies `energy_above_hull` or `is_stable`.
