# Current Project State

Last updated: 2026-05-14, Asia/Shanghai.

This file is the compact project memory for future Codex sessions. Read it
after `AGENTS.md` and before making roadmap, experiment, or implementation
decisions.

## Current Stage

- FIIR Crystal has a local-first scaffold, mock loop, CrystalFormer adapter,
  bulk orchestration, offline validation import boundary, comparison reports,
  active-loop simulation, and CrystalFormer DPO handoff boundary.
- The repository should not run real DPO training, DFT, MLIP execution, or
  external model installation inside the core `fiir_crystal` package.
- Current best next step is to wait for the submitted 64 formulas x 20 samples
  matched before/after CrystalFormer generation jobs to complete, then inspect
  the four `bulk_summary.json` files and prepare matched MACE+CHGNet+MatGL
  offline validation import. The completed 10 formulas x 20 samples smoke
  already has imported MACE+CHGNet+MatGL relaxation consensus F3 proxy
  evidence. Do not treat these labels as DFT or hull-confirmed stability.

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
- F4 is now scoped as a fixed-reference novelty/leakage audit boundary, not a
  dynamic intra-batch diversity score and not a DPO training target. The core
  package plans local audit tasks and imports externally computed F4 evidence,
  but still does not run StructureMatcher, pymatgen, database queries, downloads,
  or external APIs.
- End-of-task operating rule: after each durable task, inspect whether the
  scoped code/config/status changes should be committed and pushed to GitHub.
  Push only when the worktree can be scoped cleanly without large generated
  artifacts or unrelated user changes; otherwise record why upload is deferred.

## F4 Novelty/Leakage Boundary

- Implemented local-only F4 audit planning, reference-pool manifest, readiness
  checking, and result import:
  - `scripts/plan_f4_novelty_audit.py`
  - `scripts/build_f4_reference_pool_manifest.py`
  - `scripts/check_f4_novelty_audit_ready.py`
  - `scripts/import_f4_novelty_audit.py`
  - `fiir_crystal/validation/novelty.py`
- Spec and runbook:
  - `docs/specs/f4_novelty_leakage_audit.md`
  - `docs/setup/f4_reference_pool_workspace.md`
- Intended first real use:
  1. Create a fixed `reference_pool_v1` from local CrystalFormer training-set
     and known-material snapshots.
  2. Run `plan_f4_novelty_audit.py` against the current candidate index.
  3. Run the actual StructureMatcher/fingerprint comparison outside the core
     package and write `f4_results.jsonl`.
  4. Import results with `import_f4_novelty_audit.py`, then use
     `f4_novelty_leakage` for benchmark leakage-rate reporting and DPO pair
     filtering.
- Verification passed:
  `pytest -q tests/test_f4_novelty_import.py tests/test_f4_novelty_audit_plan.py tests/test_f4_reference_pool_manifest.py`
  and `pytest -q`.
- Current F4 execution state:
  - Plan exists:
    `outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json`
  - Task rows: 1024 candidates, 64 formulas, 16 shards x 64 rows.
  - Skipped candidates: 0.
  - Alex-20 has been downloaded from Hugging Face dataset `zdcao/alex-20` into
    the gitignored local directory
    `external/datasets/reference_pool_v1/raw/alex20_hf/`.
  - Raw Alex-20 files:
    `alex20/train.csv` with 1,071,694 rows,
    `alex20/val.csv` with 133,962 rows,
    `alex20/test.csv` with 133,962 rows, plus
    `convex_hull_pbe_2023.12.29.json.bz2`.
  - Prepared production-scale Alex-20 reference JSONL sources:
    `outputs/f4_novelty_audit/reference_pool_v1/references/alex20_train_snapshot.structures.jsonl`,
    `outputs/f4_novelty_audit/reference_pool_v1/references/alex20_val_snapshot.structures.jsonl`,
    and
    `outputs/f4_novelty_audit/reference_pool_v1/references/alex20_test_snapshot.structures.jsonl`.
  - Production `reference_pool_v1` manifest exists:
    `outputs/f4_novelty_audit/reference_pool_v1/reference_pool_manifest.json`
    with 3 sources, 1,339,618 total references, 0 duplicate reference ids, and
    0 missing reference ids.
  - Readiness check output:
    `outputs/f4_novelty_audit/reference_pool_v1/readiness_summary.json`
    and reports ready true for plan/tasks/reference-pool presence.
  - `reference_pool_v1` currently covers Alex-20 only. Materials Project,
    GNoME, and ICSD snapshots are not staged; MP/GNoME need a chosen source or
    API/export path, and ICSD requires a licensed local export. Do not build
    production F4 conclusions as "all known materials" until those sources are
    added.
  - Download provenance is recorded locally at
    `external/datasets/reference_pool_v1/provenance/alex20_hf_download.json`.
    `external/datasets/` and `outputs/` are intentionally not committed.
- F4 smoke reference state:
  - Added `scripts/prepare_f4_reference_source.py` to reshape local CSV rows
    with CIF text/path fields into manifest-friendly reference JSONL.
  - Created a non-production smoke reference pool from
    `external/CrystalFormer/data/mini.csv`:
    `outputs/f4_novelty_audit/reference_pool_mini_smoke/`
  - Smoke task plan: 1024 candidate tasks, 16 shards x 64 rows.
  - Smoke reference source:
    `outputs/f4_novelty_audit/reference_pool_mini_smoke/references/crystalformer_mini_example.structures.jsonl`
    with 29 rows.
  - Smoke manifest:
    `outputs/f4_novelty_audit/reference_pool_mini_smoke/reference_pool_manifest.json`
  - Smoke readiness:
    `outputs/f4_novelty_audit/reference_pool_mini_smoke/readiness_summary.json`
    reports ready true.
  - This only verifies the local reference-pool plumbing. It must not be used as
    production F4 leakage evidence.
  - The earlier broad local scan under `/data/home/yihaoxu` did not find
    production-scale MP, ICSD, or GNoME reference snapshots. That result is now
    superseded for Alex-20 by the downloaded Hugging Face snapshot above, but
    still applies to MP/ICSD/GNoME.

## SLURM GPU Scheduling Policy

- GPU submissions should use `scripts/slurm/submit_crystalformer_bulk_gpu.sh`
  or `scripts/slurm/plan_slurm_job.py --kind gpu` before direct `sbatch`.
- After submitting a SLURM job that needs more than a brief startup window,
  monitor startup only, then use the waiting time for safe lightweight work
  such as documentation, manifests, schema checks, dry-runs, focused tests, or
  runbook preparation. Return later to inspect `squeue`/`sacct`, logs, and
  artifacts.
- `FIIR_GPU_QUEUE_MODE=auto` is the default GPU placement policy. Auto first
  uses the original resource-aware pinned strategy: pick the best currently
  free eligible GPU node and submit with `--nodelist`. The pinned plan requests
  all currently free GPUs and CPU cores on that selected node. Auto falls back
  to flexible multi-partition queueing only when no eligible GPU node has
  enough free resources to start now.
- Flexible GPU queueing records the candidate partition set and intentionally
  does not use `--nodelist`; it requests the queued compatibility shape and
  leaves final node assignment to SLURM runtime.
- For larger GPU work, set `FIIR_GPU_MIN_GPUS` / `--min-gpus` to the GPU count
  the job should actually use. Flexible mode still requests GPUs with `--gres`
  and must not be used as a CPU-only placement shortcut.
- For larger CrystalFormer generation, MLIP validation, DPO smoke/evaluation,
  and similar GPU compute jobs, request 8 GPUs on current long-running CUDA GPU
  partitions unless the workflow has a documented smaller target partition.
- General resource-use rule: when a SLURM job can start on a specific currently
  free node, it must request and actually use that node's available compute
  shape. This applies to all submitted jobs, including smoke, debug,
  validation, generation, training, and evaluation jobs. When no eligible GPU
  node can start the job now and the job must wait in a flexible queue, use the
  standard queued request shape of `FIIR_GPU_QUEUE_MIN_GPUS=8` and
  `FIIR_GPU_QUEUE_MIN_CPUS=32`, plus an explicit right-sized memory request
  `FIIR_GPU_QUEUE_MEMORY_MB=256000`, so future GPU nodes can satisfy the job
  without inheriting a 2TB full-node memory default. Match task-level
  concurrency to the allocation in either case.
- The `test` partition is considered CUDA-compatible GPU capacity and remains
  in the same resource-aware ranking as other GPU partitions. It is not
  preferred simply because a job is small; larger available GPU resources still
  win by the normal score.
- The extra `test` rule is only a time guard: if no GPU time limit is provided,
  or if the requested time exceeds 30 minutes, the planner skips `test` even
  when it has idle GPUs.
- Use `FIIR_TIME_LIMIT=00:30:00` or `--time 00:30:00` when deliberately routing
  a short GPU sanity job to `test`.

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
outputs/crystalformer_dpo_training_boundary/mace_chgnet_matgl_consensus_1024_20260513/trainer_manifest.json
```

Summary:

- ready for external training: true
- input pairs: 1040
- valid pairs: 1040
- invalid pairs: 0
- stability-aware pair count: 1040
- train DPO in FIIR: false
- preference source:
  `outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild/dpo_preferences/preference_pairs.jsonl`
- evidence context:
  - input candidates: 1024
  - strict consensus F3-available candidates: 658
  - disagreement candidates excluded from F3: 366
  - source validation:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl`
- caveat: the 1024 strict MACE+CHGNet+MatGL consensus labels are MLIP
  relaxation proxy evidence, not DFT evidence and not self-consistent
  hull-confirmed stability.
- warning: CrystalFormer is a normal clone; fork/submodule is recommended for
  future training work.

### Completed 1024 Strict-Consensus DPO Smoke Run

The current DPO smoke package is:

```text
outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/dpo_smoke_manifest.json
```

Summary:

- FIIR core still does not implement DPO training; the prepared external
  CrystalFormer smoke was run through SLURM on a GPU compute node with JAX GPU
  preflight enabled.
- prepared pairs: 1040
- chosen/rejected raw-sequence JSONL rows: 1040 / 1040
- before checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- checkpoint start epoch: 46000
- checkpoint target epoch: 46001
- after checkpoint output root:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/after_checkpoint/`
- produced after checkpoint:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046001.pkl`
- after checkpoint size: 159M
- after checkpoint sha256:
  `f22dd30a4ae53ed3c6f8dbc485ee25c1177e40fbaeaf62682d1aabdfc4265aa1`
- run script:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/run_training.sh`
- SLURM execution provenance:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/slurm_execution_provenance.json`
- matched before/after validation plan:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/before_after_validation_plan.md`
- non-overwrite guard: the after output root is separate from the before
  checkpoint directory, and this package uses a new output directory separate
  from the older MACE-only smoke package.
- SLURM job: `99443`, `fiir-cf-dpo-1024smoke`, `COMPLETED`, exit code `0:0`,
  elapsed `00:03:08`, node `gpu40902`.
- SLURM logs:
  - `logs/slurm/fiir-cf-dpo-1024smoke_99443.log`
  - `logs/slurm/fiir-cf-dpo-1024smoke_99443.err`
- GPU evidence:
  - requested GRES: `gpu:rtx4090:8`
  - `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`
  - `FIIR_TOTAL_GPUS=8`
  - `jax_default_backend=gpu`
  - `jax_devices`: `CudaDevice(id=0)` through `CudaDevice(id=7)`
- smoke training row in `data.txt`:
  - epoch: 46001
  - loss / dpo_loss: 1281.960815 / 1281.960815
  - val loss / val dpo_loss: 307.132141 / 307.132141
- stderr contained XLA GPU autotuning warnings only in the inspected tail; no
  traceback, `Error`, `Exception`, or CPU-only JAX failure marker was found.
- caveat: the 1024 strict MACE+CHGNet+MatGL consensus labels are MLIP
  relaxation proxy evidence, not DFT evidence and not self-consistent
  hull-confirmed stability. The checkpoint is only a pipeline artifact until
  matched before/after offline validation is imported.

### Completed 1024 Strict-Consensus Before/After Generation Sanity

Matched before/after generation configs were prepared, validate-only checks
passed, and the 10 formulas x 20 samples sanity generation was run through the
GPU SLURM wrapper on the `test` partition:

- before config:
  `configs/generated/dpo_strict3mlip_1024_before_after/before_10x20_seed20260513.json`
- after config:
  `configs/generated/dpo_strict3mlip_1024_before_after/after_10x20_seed20260513.json`
- scope: 10 formulas x 20 samples for before and after
- seed: 20260513
- sampling: `K=40`, `top_p=1.0`, `temperature=1.0`
- before checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- after checkpoint:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1`
- before output root:
  `outputs/dpo_strict3mlip_1024_before_after/before_10x20_seed20260513/`
- after output root:
  `outputs/dpo_strict3mlip_1024_before_after/after_10x20_seed20260513/`
- validate-only summaries:
  - `outputs/dpo_strict3mlip_1024_before_after/before_10x20_seed20260513/bulk_validation_summary.json`
  - `outputs/dpo_strict3mlip_1024_before_after/after_10x20_seed20260513/bulk_validation_summary.json`
- ready_for_generation: true for both before and after
- blocking reasons / warnings: none for both before and after
- generation SLURM jobs:
  - before: job `99459`, `fiir-dpo1024-before-test`, partition `test`, node
    `test001`, `COMPLETED`, exit `0:0`, elapsed `00:09:54`
  - after: job `99467`, `fiir-dpo1024-after-test`, partition `test`, node
    `test001`, `COMPLETED`, exit `0:0`, elapsed `00:04:59`
- generation logs:
  - `logs/slurm/fiir-dpo1024-before-test_99459.log`
  - `logs/slurm/fiir-dpo1024-before-test_99459.err`
  - `logs/slurm/fiir-dpo1024-after-test_99467.log`
  - `logs/slurm/fiir-dpo1024-after-test_99467.err`
- GPU evidence:
  - before: `jax_default_backend=gpu`, JAX saw two CUDA devices, wrapper
    worker devices were `0` because the first `sbatch --export` path preserved
    only the first comma-separated value
  - after: `jax_default_backend=gpu`, JAX saw two CUDA devices, wrapper worker
    devices were `0,1`
  - both stderr files were empty, and no traceback / error / CPU-only GPU
    preflight marker was found in the inspected SLURM logs
- before summary:
  - completed formulas: 10 / 10
  - candidates: 200
  - DPO eligible candidates: 200
  - F1 fail count / rate: 7 / 0.035
  - F2 fail count / rate: 0 / 0.0
  - F3 available / unknown: 0 / 200
  - generated preference pairs: 130
- after summary:
  - completed formulas: 10 / 10
  - candidates: 200
  - DPO eligible candidates: 200
  - F1 fail count / rate: 3 / 0.015
  - F2 fail count / rate: 0 / 0.0
  - F3 available / unknown: 0 / 200
  - generated preference pairs: 76
- comparison summary/report:
  - `outputs/dpo_strict3mlip_1024_before_after/comparison_10x20_seed20260513/summary.json`
  - `outputs/dpo_strict3mlip_1024_before_after/comparison_10x20_seed20260513/report.md`
- read-only strict QA artifacts:
  - combined:
    `outputs/dpo_strict3mlip_1024_before_after/qa_before_after_10x20_seed20260513/qa_summary.json`
  - before:
    `outputs/dpo_strict3mlip_1024_before_after/qa_before_10x20_seed20260513/qa_summary.json`
  - after:
    `outputs/dpo_strict3mlip_1024_before_after/qa_after_10x20_seed20260513/qa_summary.json`
- strict QA caveat: `ready` is false because 6 formulas per side produced zero
  generated preference-pair artifacts, and the combined before/after scan also
  flags duplicate candidate ids across matched roots. Candidate generation did
  complete and parse as full structures, so this is a generation sanity artifact
  awaiting offline validation import rather than a performance result.
- caveat: generation sanity F1/F2 results and generated preference-pair yield
  are not DPO performance evidence. Import offline MACE+CHGNet+MatGL relaxation
  consensus F3 proxy evidence before making before/after claims. The 1024
  strict-consensus labels remain MLIP relaxation proxy evidence, not DFT and not
  self-consistent hull-confirmed stability.

### Completed 1024 Strict-Consensus Before/After Offline Validation

Matched before/after MACE+CHGNet+MatGL relaxation validation has been submitted
through SLURM for the completed 10 formulas x 20 samples generation roots, and
the local strict three-MLIP consensus import/comparison has completed. This is a
small smoke-scale proxy audit, not a production-scale performance result:

- provenance/runbook directory:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/`
- partial manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/run_manifest_partial.json`
- final manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/run_manifest_final.json`
- readiness summary:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/readiness_summary.json`
- runbook:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/README.md`
- candidate validation batches:
  - before:
    `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_20260513_batch/before/selected_candidates.jsonl`
  - after:
    `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_20260513_batch/after/selected_candidates.jsonl`
- batch counts: 200 selected/indexed candidates for before and 200
  selected/indexed candidates for after
- candidate IDs were prefixed as `before__` and `after__` to avoid
  before/after ID collisions during offline validation import.
- initial jobs `101119`-`101122` were cancelled before running because the
  initial `gpu4090` target was not usable for these submissions; they produced
  no validation outputs.
- current SLURM validation jobs:
  - MACE before: job `101126`, `test`, `test001`, `COMPLETED`, exit `0:0`,
    elapsed `00:04:04`, normalized rows 200
  - MACE after: job `101127`, `test`, `test001`, `COMPLETED`, exit `0:0`,
    elapsed `00:02:57`, normalized rows 200
  - CHGNet before: job `101128`, `test`, `test001`, `COMPLETED`, exit `0:0`,
    elapsed `00:02:59`, normalized rows 200
  - CHGNet after: job `101129`, `test`, `test001`, `COMPLETED`, exit `0:0`,
    elapsed `00:09:47`, normalized rows 200
  - MatGL before: job `101130`, `test`, `test001`, `COMPLETED`, exit `0:0`,
    elapsed `00:12:35`, normalized rows 200
  - MatGL after: job `101131`, `test`, `test001`, `COMPLETED`, exit `0:0`,
    elapsed `00:09:38`, normalized rows 200
- scheduler policy: `test` is GPU-capable but has a 30-minute time guard and
  remains part of normal resource-based GPU ranking; it is not a special
  "small task preferred" partition.
- all submitted validation jobs requested `gpu:rtx4090:2` on SLURM and were
  launched through existing SLURM wrappers, not local login-node MLIP runs.
- local import scripts:
  - `scripts/check_dpo_offline_validation_ready.py`
  - `scripts/build_mlip_ensemble_consensus.py`
  - `scripts/compare_dpo_before_after_mlip_consensus.py`
- readiness gate: passed; all six normalized validator JSONL files exist and
  have the expected 200-row matched coverage.
- consensus artifacts:
  - before:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_before_20260513/`
  - after:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_after_20260513/`
- final matched comparison:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_comparison_10x20_seed20260513/`
- imported comparison counts:
  - before: 200 candidates, 200 DPO eligible, F1 fail rate 0.035, F2 fail rate
    0.0, F3 available 125, stable consensus 52, unstable consensus 73,
    disagreement 75, all-three agreement rate 0.625, stable consensus rate
    0.26, preference-pair yield 130
  - after: 200 candidates, 200 DPO eligible, F1 fail rate 0.015, F2 fail rate
    0.0, F3 available 130, stable consensus 58, unstable consensus 72,
    disagreement 70, all-three agreement rate 0.65, stable consensus rate
    0.29, preference-pair yield 76
  - deltas: stable consensus +6, stable consensus rate +0.03, F3 available +5,
    all-three agreement rate +0.025, disagreement -5, F1 fail rate -0.02,
    preference-pair yield -54
  - diversity/collapse smoke signal: formula coverage remained 10 formulas x
    20 samples, unique sequence fraction remained 1.0, spacegroup count
    remained 46, spacegroup entropy changed from 3.68908 to 3.69188
  - proxy-divergence screen: no flag in the small 10x20 report
- caveat: these labels are MLIP relaxation proxy evidence, not DFT evidence and
  not self-consistent hull-confirmed stability. The apparent proxy improvement
  is small-smoke evidence only and should be followed by a larger matched
  64-formula audit before any performance claim.

### Submitted 64-Formula Before/After Generation Gate

The next larger matched before/after generation gate has been submitted through
the project GPU SLURM wrapper and is waiting for GPU resources:

- submission manifest:
  `outputs/dpo_strict3mlip_1024_before_after/generation_64x20_seed20260513_submission_20260513/submission_manifest.json`
- submission runbook:
  `outputs/dpo_strict3mlip_1024_before_after/generation_64x20_seed20260513_submission_20260513/README.md`
- earlier defer marker:
  `outputs/dpo_strict3mlip_1024_before_after/deferred_64x20_gpu_resources_20260513/defer_marker.json`
- earlier defer runbook:
  `outputs/dpo_strict3mlip_1024_before_after/deferred_64x20_gpu_resources_20260513/README.md`
- target: 64 formulas x 20 samples, matched before/after
- formula bank:
  `configs/generated/dpo_strict3mlip_1024_before_after/perovskite_first64_formula_bank_seed20260513.json`
- before configs:
  `configs/generated/dpo_strict3mlip_1024_before_after/before_64x20_seed20260513_shards/shard_001.json`
  and
  `configs/generated/dpo_strict3mlip_1024_before_after/before_64x20_seed20260513_shards/shard_002.json`
- after configs:
  `configs/generated/dpo_strict3mlip_1024_before_after/after_64x20_seed20260513_shards/shard_001.json`
  and
  `configs/generated/dpo_strict3mlip_1024_before_after/after_64x20_seed20260513_shards/shard_002.json`
- validate-only status: all four shard configs passed local lightweight
  validate-only checks with 32 formulas and 640 requested samples per shard.
- initial bad submissions:
  - jobs `101184` and `101185` were cancelled because the automatic pinned
    choice used the known-unusable `gpu4090` partition for this workflow
    (`PartitionConfig` / unusable node reason).
  - jobs `101187`, `101188`, `101190`, and `101191` were cancelled before
    running because they requested only `gpu:1`; they were replaced with
    whole-node GPU requests.
  - jobs `101197`, `101198`, `101200`, and `101201` were cancelled before
    running because they requested 8 GPUs but only 32 CPUs under the earlier
    strict full-H20/H200-node interpretation.
  - jobs `101205`, `101206`, `101208`, and `101210` were cancelled before
    running after the queue rule was clarified: if no eligible GPU node can
    start now, flexible queueing should use the broader 8 GPU + 32 CPU queued
    shape rather than the 192-CPU H20/H200-only shape.
  - jobs `101217`, `101218`, `101219`, and `101220` were cancelled before
    running because omitting `--mem` let SLURM infer
    `ReqTRES=cpu=32,mem=2000000M,...,gres/gpu=8` on the broad queue.
  - jobs `101253`, `101254`, `101255`, and `101256` were cancelled before
    running after the queue memory policy was refined from a fixed 256GB to the
    minimum memory of the currently eligible queueable GPU nodes.
  - jobs `101268`, `101269`, `101270`, and `101271` were cancelled before
    running after that auto-memory policy was superseded.
  - jobs `101274`, `101275`, `101276`, and `101277` were cancelled before
    running after the no-free-node flexible queue fallback was changed from
    512G-class memory to 256G-class memory.
- active submitted generation jobs:
  - before shard 001: job `101278`, `fiir-dpo64-b1-m256`, pending at submission
    snapshot, output root
    `outputs/dpo_strict3mlip_1024_before_after/before_64x20_seed20260513_shard_001`
  - before shard 002: job `101279`, `fiir-dpo64-b2-m256`, pending at submission
    snapshot, output root
    `outputs/dpo_strict3mlip_1024_before_after/before_64x20_seed20260513_shard_002`
  - after shard 001: job `101280`, `fiir-dpo64-a1-m256`, pending at submission
    snapshot, output root
    `outputs/dpo_strict3mlip_1024_before_after/after_64x20_seed20260513_shard_001`
  - after shard 002: job `101281`, `fiir-dpo64-a2-m256`, pending at submission
    snapshot, output root
    `outputs/dpo_strict3mlip_1024_before_after/after_64x20_seed20260513_shard_002`
- scheduling policy used: `FIIR_GPU_QUEUE_MODE=auto` with an explicit
  long-running CUDA allowlist `h200,h20,h20llm,gpu4090_8,gpu4090_128`.
  Because no eligible GPU node had enough free resources to start immediately,
  the effective mode was flexible queueing across those partitions.
- resource request per active job: `gpu:8`, 32 CPUs, `02:00:00`, account
  `hmt03`, conda environment `crystalformer`, JAX GPU preflight required.
  No-free-node flexible queue memory is now `FIIR_GPU_QUEUE_MEMORY_MB=256000`.
  `scontrol show job 101278` confirmed
  `ReqTRES=cpu=32,mem=250G,node=1,billing=32,gres/gpu=8`
  and `TresPerTask=cpu=32`. The bulk runner will see `FIIR_TOTAL_GPUS=8` and
  `FIIR_TOTAL_CPU_CORES=32`, so it should use eight GPU workers with the
  queued CPU budget while waiting across more eligible 8-GPU CUDA nodes.
- optional follow-up if clean: 64 formulas x 40 samples
- execution policy: submit only through existing SLURM wrappers or project
  submit wrappers; do not run CrystalFormer generation, MLIP validation, DFT,
  or long evaluation on the login node.
- scheduler caveat: use normal GPU resource ranking first, and use flexible
  multi-partition queueing only when no eligible long-running GPU node has
  enough free resources; `test` remains limited to explicitly bounded jobs of
  30 minutes or less.
- next step after completion: inspect all four `bulk_summary.json` files,
  confirm matched before/after coverage, then prepare the matched
  MACE+CHGNet+MatGL relaxation offline validation batches. Do not claim DPO
  improvement from generation-only outputs.
- evidence caveat: the completed 10x20 smoke and the deferred larger gate are
  MLIP relaxation consensus proxy evidence, not DFT evidence and not
  self-consistent hull-confirmed stability.

### Previous Completed MACE-Only DPO Smoke Run

The previous completed DPO smoke package is:

```text
outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/dpo_smoke_manifest.json
```

Summary:

- FIIR core still does not implement DPO training; the prepared external
  CrystalFormer smoke was run through SLURM on a GPU compute node.
- prepared pairs: 284
- chosen/rejected raw-sequence JSONL rows: 284 / 284
- before checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- after checkpoint output root:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/after_checkpoint/`
- produced after checkpoint:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046001.pkl`
- after checkpoint size: 159M
- after checkpoint sha256:
  `42b11edfbf1586a1a8910e087616a5803486eba53b3901657c170c1b30c33fa6`
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

Regenerate the current 1024 strict three-MLIP consensus training boundary:

```bash
python scripts/prepare_crystalformer_dpo_training_boundary.py \
  --preference-pairs-jsonl outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild/dpo_preferences/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_training_boundary/mace_chgnet_matgl_consensus_1024_20260513 \
  --crystalformer-work-dir external/CrystalFormer \
  --checkpoint-dir external/checkpoints/crystalformer/alex20s_csp \
  --preference-artifact-label mace_chgnet_matgl_consensus_1024_20260513_import_rebuild \
  --source-validation-jsonl outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl \
  --input-candidate-count 1024 \
  --f3-available-candidate-count 658 \
  --disagreement-candidate-count 366 \
  --evidence-caveat "1024 strict MACE+CHGNet+MatGL consensus labels are MLIP relaxation proxy evidence, not DFT evidence and not self-consistent hull-confirmed stability."
```

Prepare the current non-overwriting 1024 strict-consensus DPO smoke package:

```bash
python scripts/prepare_crystalformer_dpo_smoke_run.py \
  --preference-pairs-jsonl outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild/dpo_preferences/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare \
  --base-checkpoint-dir external/checkpoints/crystalformer/alex20s_csp \
  --crystalformer-work-dir external/CrystalFormer \
  --epochs 1 \
  --batchsize 32 \
  --num-io-process 1 \
  --preference-artifact-label mace_chgnet_matgl_consensus_1024_20260513_import_rebuild \
  --source-validation-jsonl outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl \
  --input-candidate-count 1024 \
  --f3-available-candidate-count 658 \
  --disagreement-candidate-count 366 \
  --evidence-caveat "1024 strict MACE+CHGNet+MatGL consensus labels are MLIP relaxation proxy evidence, not DFT evidence and not self-consistent hull-confirmed stability."
```

Run the prepared smoke only on an allocated compute node with the CrystalFormer
environment active. The reusable SLURM wrapper is:

```bash
FIIR_DPO_RUN_SCRIPT=outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/run_training.sh \
sbatch scripts/slurm/run_crystalformer_dpo_smoke.slurm
```

The generated run script can also be run directly inside an interactive GPU
allocation:

```bash
outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/run_training.sh
```

Verify code health:

```bash
pytest -q
```

## Known Pitfalls

- Do not treat MACE single-point force/stress evidence as F3 stability. The
  3200-row single-point artifact is useful QA evidence but produces zero
  F3-available candidates.
- Do not default to the old MACE-only 284-pair artifact for precision-first DPO
  handoff. Use the 1024-candidate strict MACE+CHGNet+MatGL consensus preference
  source unless a task explicitly requests the older artifact.
- Do not describe the 1024 strict consensus labels as DFT or hull-confirmed
  stability. They are MLIP relaxation proxy evidence.
- Do not use the default BaTiO3 DPO config for all-formula pair building.
- Do not commit large `outputs/` artifacts or checkpoints.

## Recommended Next Step

Wait for sufficient GPU compute resources, then run the larger matched
before/after validation gate. Start with 64 formulas x 20 samples, then expand
to 64 formulas x 40 only if the first scale-up is clean. Keep before/after
checkpoints, formulas, seed, sampling parameters, and candidate count matched;
report agreement, disagreement, diversity/collapse, coverage, preference-pair
yield, and proxy-divergence checks. The deferred gate remains MLIP relaxation
proxy evidence, not DFT or hull-confirmed stability.
