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

This stage prepares and normalizes evidence only; it does not run MACE,
CHGNet, MatGL, or any other validator from FIIR core:

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
