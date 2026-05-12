# Current Project State

Last updated: 2026-05-13, Asia/Shanghai.

This file is the compact project memory for future Codex sessions. Read it
after `AGENTS.md` and before making roadmap, experiment, or implementation
decisions.

## Current Stage

- FIIR Crystal has a local-first scaffold, mock loop, CrystalFormer adapter,
  bulk orchestration, offline validation import boundary, comparison reports,
  active-loop simulation, and CrystalFormer DPO handoff boundary.
- The repository should not run real DPO training, DFT, MLIP execution, or
  external model installation inside the core `fiir_crystal` package.
- Current best next step: use the expanded 1024-candidate strict
  MACE+CHGNet+MatGL consensus artifact for the next CrystalFormer DPO handoff
  or smoke. Do not treat these labels as DFT or hull-confirmed stability.

## Important Guidance State

- `docs/guidance/00_reading_order.md` was removed.
- `AGENTS.md` is now the startup entrypoint and points to:
  - `docs/status/current_project_state.md`
  - `docs/guidance/01_fiir_project_manual.md`
  - `docs/guidance/02_paper1_crystalfail_bench.md`
  - `docs/guidance/03_paper2_fsal.md`
  - `docs/guidance/04_paper3_discovery_pipeline.md`
- Failure schema now includes optional F4 novelty leakage and F5
  synthesizability fields, while FSAL/DPO pair mining remains focused on F1-F3.

## Latest Durable Results

These are the currently important artifacts and counts.

### CrystalFormer Workspace

- `external/CrystalFormer` exists and is a normal clone.
- `external/checkpoints/crystalformer/alex20s_csp` exists.
- The DPO training boundary warns that a fork or submodule is recommended for
  future training, although the current normal clone is sufficient for smoke and
  data handoff.

### Existing CrystalFormer / MLIP Evidence

- A broad CrystalFormer audit corpus exists under:
  `outputs/crystalformer_bulk_real_smoke_perovskite_128_32x1600_shard_*`.
- MACE single-point evidence:
  `outputs/mlip_validation_mace_overnight_20260512/normalized/validation_results.jsonl`
  - normalized rows: 3200
  - unmatched candidate ids: 0
  - F3 available candidates: 0
  - reason: single-point force/stress evidence has no local hull or derived
    stability label.
- MACE relaxation-derived evidence:
  `outputs/mlip_validation_mace_relax_20260512/normalized/validation_results.jsonl`
  - normalized rows: 320
  - unmatched candidate ids: 0
  - F3 available candidates: 320
  - source: `local_mlip_mace_relaxation`
  - calibration tier: `tier3_single_mlip`
  - caveat: F3 is a relaxation-threshold proxy, not DFT or hull-confirmed
    stability.
- CHGNet single-point smoke evidence:
  `outputs/mlip_validation_chgnet_smoke_20260512/normalized/validation_results.jsonl`
  - normalized rows: 1
  - unmatched candidate ids: 0
  - F3 available candidates: 0
  - source: `local_mlip_chgnet_single_point`
  - calibration tier: `tier3_single_mlip`
  - SLURM job: `98551`, `fiir-chgnet-smoke`, `COMPLETED`, exit code
    `0:0`, elapsed `00:00:23`, node `gpu40904`
  - caveat: this is a one-candidate smoke for the non-MACE runner, not a
    production ensemble or hull workflow.
- CHGNet single-point evidence aligned to the 320 MACE-relax candidates:
  `outputs/mlip_validation_chgnet_mace_relax_aligned_20260512/normalized/validation_results.jsonl`
  - normalized rows: 320
  - unmatched candidate ids: 0
  - F3 available candidates: 0
  - source: `local_mlip_chgnet_single_point`
  - SLURM job: `98567`, `fiir-chgnet-320`, `COMPLETED`, exit code `0:0`,
    elapsed `00:00:11`, node `gpu40904`
- CHGNet relaxation-derived evidence aligned to the 320 MACE-relax candidates:
  `outputs/mlip_validation_chgnet_relax_mace_relax_aligned_20260512/normalized/validation_results.jsonl`
  - normalized rows: 320
  - unmatched candidate ids: 0
  - F3 available candidates: 320
  - source: `local_mlip_chgnet_relaxation`
  - calibration tier: `tier3_single_mlip`
  - SLURM job: `98588`, `fiir-chgnet-relax320`, `COMPLETED`, exit code
    `0:0`, elapsed `00:01:07`, node `gpu40904`
  - caveat: stderr reported CHGNet isolated-atom warnings for some structures;
    this is still relaxation-threshold proxy evidence, not DFT or hull-confirmed
    stability.
- MACE+CHGNet relaxation consensus evidence:
  `outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/normalized/validation_results.jsonl`
  - normalized rows: 320
  - unmatched candidate ids: 0
  - F3 available candidates: 242
  - stable consensus: 96
  - unstable consensus: 146
  - disagreement rows with `is_stable=null`: 78
  - calibration policy: `tier2_mlip_ensemble` only when MACE and CHGNet
    relaxation proxies agree; disagreement rows remain `tier3_mlip_disagreement`.
  - agreement report:
    `outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/report.md`
- MatGL relaxation-derived evidence aligned to the same 320 MACE-relax
  candidates:
  `outputs/mlip_validation_matgl_relax_mace_relax_aligned_cuda_20260512/normalized/validation_results.jsonl`
  - normalized rows: 320
  - unmatched candidate ids: 0
  - failed/incomplete rows: 0
  - F3 available candidates: 320
  - source: `local_mlip_matgl_relaxation`
  - calibration tier: `tier3_single_mlip`
  - model: `M3GNet-PES-MatPES-PBE-2025.2`
  - SLURM job: `99042`, `fiir-matgl-relax320-cuda`, `COMPLETED`, exit
    code `0:0`, elapsed `00:01:03`, node `gpu40904`
  - caveat: first full MatGL relax attempt (`98645`) timed out after one hour
    because MatGL stayed CPU-only; the runner now explicitly moves the loaded
    potential to CUDA with `.to(actual_device)`.
- MACE+CHGNet+MatGL relaxation consensus evidence:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_20260512/normalized/validation_results.jsonl`
  - normalized rows: 320
  - F3 available candidates: 194
  - stable consensus: 85
  - unstable consensus: 109
  - disagreement rows with `is_stable=null`: 126
  - all-three agreement rate: 0.60625
  - pairwise agreement rates: MACE/CHGNet 0.75625, MACE/MatGL 0.721875,
    CHGNet/MatGL 0.734375
  - calibration policy: `tier2_mlip_ensemble` only when all three relaxation
    proxies agree; disagreement rows remain `tier3_mlip_disagreement`.
- Expanded 1024-candidate MACE+CHGNet+MatGL relaxation consensus evidence:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl`
  - input batch:
    `outputs/mlip_validation_three_mlip_1024_20260513_batch/selected_candidates.jsonl`
  - batch shape: 1024 candidates, 64 formulas, 16 candidates/formula
  - normalized rows: 1024
  - formula mismatch count: 0
  - unmatched candidate ids: 0
  - single-model relax outputs:
    - MACE:
      `outputs/mlip_validation_mace_relax_1024_20260513/normalized/validation_results.jsonl`,
      SLURM job `99186`, elapsed `00:04:08`
    - CHGNet:
      `outputs/mlip_validation_chgnet_relax_1024_20260513/normalized/validation_results.jsonl`,
      SLURM job `99196`, elapsed `00:03:39`
    - MatGL:
      `outputs/mlip_validation_matgl_relax_1024_20260513/normalized/validation_results.jsonl`,
      SLURM job `99200`, elapsed `00:05:14`
  - all three single-model outputs normalized 1024/1024 with no failed or
    incomplete rows
  - F3 available candidates: 658
  - stable consensus: 186
  - unstable consensus: 472
  - disagreement rows with `is_stable=null`: 366
  - all-three agreement rate: 0.642578125
  - pairwise agreement rates: MACE/CHGNet 0.76171875, MACE/MatGL
    0.7490234375, CHGNet/MatGL 0.7744140625
  - pairwise energy Pearson: MACE/CHGNet 0.8016007981667927, MACE/MatGL
    0.8447657796203446, CHGNet/MatGL 0.7874871617358663
  - calibration policy: `tier2_mlip_ensemble` only when all three relaxation
    proxies agree; disagreement rows remain `tier3_mlip_disagreement`.
- Generic non-MACE runner state:
  - `scripts/run_mlip_offline_validation.py` supports `--mlip-kind chgnet`
    and `--mlip-kind matgl` as external optional workflows.
  - `scripts/slurm/run_mlip_offline_validation.slurm` runs the generic
    workflow on a GPU node and normalizes outputs in place.
  - `matgalaxy` has CHGNet, MatGL 3.0.3, torch, torch-geometric, pymatgen, and
    ASE. DGL is not installed; MatGL is using the `PYG` backend.
  - Real MatGL execution requires an explicit local
    `FIIR_MLIP_MODEL_PATH`/`--model-path` to avoid implicit model downloads,
    and the runner now gives MatGL a writable per-output `matgl_home`.

### Current DPO Preference Artifact

The current preferred strict three-MLIP consensus DPO preference artifact is:

```text
outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild/dpo_preferences/preference_pairs.jsonl
```

Summary:

- input candidates: 1024
- consensus F3-available candidates: 658
- disagreement candidates excluded from F3 by `is_stable=null`: 366
- preference pairs: 1040
- stability-aware pairs: 1040
- preference type: `stability_aware_offline_validation`
- stability preferences: true
- source validation:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl`
- caveat: this is the expanded strict MLIP-proxy preference set, not DFT or
  self-consistent hull-confirmed stability. Use it as the current best
  production-scale preference source when precision is preferred.

The current best production-scale single-MLIP DPO preference artifact is:

```text
outputs/dpo_preferences/mace_relax_20260512_rebuild_current_filtered/dpo_preferences_all_formula/preference_pairs.jsonl
```

Summary:

- input F3-available candidates: 320
- usable candidates: 320
- preference pairs: 284
- preference type: `stability_aware_offline_validation`
- stability preferences: true
- geometry/chemistry-only pairs in this artifact: 0

The filtered F3-available input used to build it is:

```text
outputs/dpo_preferences/mace_relax_20260512_filtered/audit_candidates_f3_available.jsonl
```

Important note: the default `configs/dpo_preference_builder.yaml` is
BaTiO3-oriented. For all-formula rebuilds, use:

```text
configs/dpo_preference_builder.all_formula_mace_relax_20260512.json
```

The current conservative two-MLIP consensus DPO preference artifact is:

```text
outputs/dpo_preferences/mace_chgnet_consensus_20260512_import_rebuild/dpo_preferences/preference_pairs.jsonl
```

Summary:

- input candidates: 320
- consensus F3-available candidates: 242
- disagreement candidates excluded from F3 by `is_stable=null`: 78
- preference pairs: 153
- preference type: `stability_aware_offline_validation`
- stability preferences: true
- source validation:
  `outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/normalized/validation_results.jsonl`
- caveat: this is still MLIP relaxation proxy evidence, not DFT or
  self-consistent hull-confirmed stability. Use it as the more conservative
  alternative to the MACE-only 284-pair artifact.

The previous 320-candidate strict three-MLIP consensus DPO preference artifact is:

```text
outputs/dpo_preferences/mace_chgnet_matgl_consensus_20260512_import_rebuild/dpo_preferences/preference_pairs.jsonl
```

Summary:

- input candidates: 320
- consensus F3-available candidates: 194
- disagreement candidates excluded from F3 by `is_stable=null`: 126
- preference pairs: 96
- preference type: `stability_aware_offline_validation`
- stability preferences: true
- source validation:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_20260512/normalized/validation_results.jsonl`
- caveat: this was the strictest MLIP-proxy preference set before the expanded
  1024-candidate run.

### DPO Training Boundary

The current handoff artifact is:

```text
outputs/crystalformer_dpo_training_boundary/mace_relax_20260512_rebuild_current_filtered/trainer_manifest.json
```

Summary:

- ready for external training: true
- input pairs: 284
- valid pairs: 284
- invalid pairs: 0
- stability-aware pair count: 284
- train DPO in FIIR: false
- warning: CrystalFormer is a normal clone; fork/submodule is recommended for
  future training work.

### Completed Non-Overwriting DPO Smoke Run

The current DPO smoke package is:

```text
outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/dpo_smoke_manifest.json
```

Summary:

- FIIR core still does not implement DPO training; the prepared external
  CrystalFormer smoke was run through SLURM on a GPU compute node.
- prepared pairs: 284
- chosen/rejected raw-sequence JSONL rows: 284 / 284
- before checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- checkpoint start epoch: 46000
- checkpoint target epoch: 46001
- after checkpoint output root:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/after_checkpoint/`
- produced after checkpoint:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046001.pkl`
- after checkpoint size: 159M
- after checkpoint sha256:
  `42b11edfbf1586a1a8910e087616a5803486eba53b3901657c170c1b30c33fa6`
- run script:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/run_training.sh`
- non-overwrite guard: the after output root is separate from the before
  checkpoint directory.
- SLURM job: `98336`, `fiir-cf-dpo-smoke`, `COMPLETED`, exit code `0:0`,
  elapsed `00:03:05`, node `gpu40902`.
- SLURM logs:
  - `logs/slurm/fiir-cf-dpo-smoke_98336.log`
  - `logs/slurm/fiir-cf-dpo-smoke_98336.err`
- smoke training row in `data.txt`:
  - epoch: 46001
  - loss / dpo_loss: 1253.308228 / 1253.308228
  - val loss / val dpo_loss: 3654.330566 / 3654.330566
- stderr contained XLA autotuning warnings only; no traceback was present in
  the successful job.

CrystalFormer local branch/state:

- `external/CrystalFormer` is on local branch `fiir-dpo-adapter-smoke`.
- Local CrystalFormer edits:
  - `crystalformer/reinforce/dpo.py`: convert the top-level DPO deprecation
    hard raise into a warning so `train_dpo` can import; adapt DPO log-prob
    calls to the current CrystalFormer composition argument; include `logp_g`;
    and shuffle six-field data tuples safely.
  - `crystalformer/src/utils.py`: allow `GLXYZAW_from_file(... .jsonl)` to
    load FIIR raw `g/L/X/A/W` sequence JSONL directly.
- Because `external/CrystalFormer` is a normal external clone, the local
  CrystalFormer adapter changes are also exported in the main repository at:
  `patches/crystalformer/fiir-dpo-adapter-smoke.patch`.

### DPO Smoke Before/After Generation Sanity

Matched before/after generation was run with identical formulas and sampling
settings:

- scope: 10 formulas x 20 samples for before and after
- seed: 20260512
- sampling: `K=40`, `top_p=1.0`, `temperature=1.0`
- before config:
  `configs/generated/dpo_smoke_before_after/before_10x20_seed20260512.json`
- after config:
  `configs/generated/dpo_smoke_before_after/after_10x20_seed20260512.json`
- before output:
  `outputs/dpo_smoke_before_after/before_10x20_seed20260512/`
- after output:
  `outputs/dpo_smoke_before_after/after_10x20_seed20260512/`
- comparison report:
  `outputs/dpo_smoke_before_after/comparison/report.md`
- comparison summary:
  `outputs/dpo_smoke_before_after/comparison/summary.json`

SLURM state:

- before job `98383`: `COMPLETED`, exit `0:0`, node `gpu40902`
- old after job `98385`: cancelled while pending so it could be resubmitted
  onto the freed node
- after retry job `98407`: `COMPLETED`, exit `0:0`, node `gpu40902`

Result:

- before candidates / DPO eligible: 200 / 200
- after candidates / DPO eligible: 200 / 200
- before F1 fails: 3
- after F1 fails: 2
- F2 fails: 0 before and after
- F3 unknown: 200 before and 200 after
- geometry/chemistry preference pairs from smoke audit: 57 before, 38 after
- single-root artifact QA passed for both runs:
  - before: `outputs/dpo_smoke_before_after/qa_before/qa_summary.json`
  - after: `outputs/dpo_smoke_before_after/qa_after/qa_summary.json`

Interpretation:

- This is only a generation/audit sanity check for the DPO smoke checkpoint.
- It shows no obvious generation breakage after the one-epoch DPO smoke.
- It is not evidence of DPO performance improvement because there is no offline
  validation import for these generated candidates and F3 remains unknown.

## Reproduction Commands

Rebuild the current all-formula F3-aware DPO preference artifact:

```bash
python scripts/build_crystalformer_dpo_preferences.py \
  --config configs/dpo_preference_builder.all_formula_mace_relax_20260512.json \
  --fail-on-zero-pairs
```

Regenerate the training boundary artifact:

```bash
python scripts/prepare_crystalformer_dpo_training_boundary.py \
  --preference-pairs-jsonl outputs/dpo_preferences/mace_relax_20260512_rebuild_current_filtered/dpo_preferences_all_formula/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_training_boundary/mace_relax_20260512_rebuild_current_filtered \
  --crystalformer-work-dir external/CrystalFormer \
  --checkpoint-dir external/checkpoints/crystalformer/alex20s_csp
```

Prepare the current non-overwriting DPO smoke run package:

```bash
python scripts/prepare_crystalformer_dpo_smoke_run.py \
  --preference-pairs-jsonl outputs/dpo_preferences/mace_relax_20260512_rebuild_current_filtered/dpo_preferences_all_formula/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare \
  --base-checkpoint-dir external/checkpoints/crystalformer/alex20s_csp \
  --crystalformer-work-dir external/CrystalFormer \
  --epochs 1 \
  --batchsize 32 \
  --num-io-process 1
```

Run the prepared smoke only on an allocated compute node with the CrystalFormer
environment active. The reusable SLURM wrapper is:

```bash
FIIR_DPO_RUN_SCRIPT=outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/run_training.sh \
sbatch scripts/slurm/run_crystalformer_dpo_smoke.slurm
```

The generated run script can also be run directly inside an interactive GPU
allocation:

```bash
outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/run_training.sh
```

Verify code health:

```bash
pytest -q
```

## Known Pitfalls

- Do not treat MACE single-point force/stress evidence as F3 stability. The
  3200-row single-point artifact is useful QA evidence but produces zero
  F3-available candidates.
- Do not run full all-audit DPO rebuild directly over 102400 audit rows unless
  the builder is optimized first; pair comparison is unnecessarily heavy for
  this task. Use the 320-row F3-available filtered input for current DPO handoff.
- Do not use the default BaTiO3 DPO config for all-formula pair building.
- Do not commit large `outputs/` artifacts or checkpoints.

## Recommended Next Step

Use the before/after generated candidates as a small sanity set for the same
offline validation workflow, or expand the preference data before running any
larger DPO. The current DPO smoke checkpoint should be treated as a pipeline
artifact, not a performance-improved model.
