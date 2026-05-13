# Run Log

This file records durable, high-signal workflow results for future agents. Keep
entries concise and point to generated artifacts instead of duplicating large
outputs.

## 2026-05-14: F4 Novelty/Leakage Audit Boundary

- Added a local-only F4 novelty/leakage audit boundary. The FIIR core now plans
  audit tasks, records fixed reference-pool provenance, checks readiness, and
  imports externally computed F4 rows without running StructureMatcher,
  pymatgen, database queries, downloads, or external APIs.
- Added:
  - `fiir_crystal/validation/novelty.py`
  - `scripts/plan_f4_novelty_audit.py`
  - `scripts/build_f4_reference_pool_manifest.py`
  - `scripts/check_f4_novelty_audit_ready.py`
  - `scripts/import_f4_novelty_audit.py`
  - `docs/specs/f4_novelty_leakage_audit.md`
  - `docs/setup/f4_reference_pool_workspace.md`
  - focused F4 tests.
- F4 decision: `f4_novelty_leakage` is measured against a frozen external
  reference pool such as training-set and known-material snapshots. Internal
  generated-structure duplication remains a separate diversity/mode-collapse
  QA metric, not the F4 main label.
- Verification:
  `pytest -q tests/test_f4_novelty_import.py tests/test_f4_novelty_audit_plan.py tests/test_f4_reference_pool_manifest.py`
  and `pytest -q` passed.

Follow-up execution:

- Confirmed candidate index exists:
  `outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl`
  with 1024 rows.
- F4 audit plan is already materialized at
  `outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json`.
- Plan shape: 1024 selected tasks, 64 formulas, 16 shards with 64 rows each,
  0 skipped candidates.
- Re-ran readiness check:
  `python scripts/check_f4_novelty_audit_ready.py --plan-json outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json --output-json outputs/f4_novelty_audit/reference_pool_v1/readiness_summary.json`
- Readiness result: not ready only because
  `outputs/f4_novelty_audit/reference_pool_v1/reference_pool_manifest.json`
  is missing.
- Local reference scan found only `external/CrystalFormer/data/mini.csv` as an
  example CIF-bearing dataset, not a production-scale Alex-20s/training-set,
  MP, ICSD, or GNoME reference snapshot. Do not use `mini.csv` as production
  F4 reference evidence.

Mini smoke reference pool:

- Added `scripts/prepare_f4_reference_source.py` to convert an existing local
  CSV with CIF text/path fields into reference JSONL for manifest construction.
- Prepared a non-production smoke source from `external/CrystalFormer/data/mini.csv`:
  `outputs/f4_novelty_audit/reference_pool_mini_smoke/references/crystalformer_mini_example.structures.jsonl`
  with 29 rows.
- Built smoke manifest:
  `outputs/f4_novelty_audit/reference_pool_mini_smoke/reference_pool_manifest.json`
  with `reference_pool_id=reference_pool_mini_smoke`.
- Planned smoke F4 tasks:
  `outputs/f4_novelty_audit/reference_pool_mini_smoke/f4_audit_plan.json`
  with 1024 tasks and 16 shards.
- Readiness check:
  `python scripts/check_f4_novelty_audit_ready.py --plan-json outputs/f4_novelty_audit/reference_pool_mini_smoke/f4_audit_plan.json --output-json outputs/f4_novelty_audit/reference_pool_mini_smoke/readiness_summary.json`
  reported ready true.
- Caveat: this smoke pool validates local plumbing only. It is not production F4
  evidence and must not replace the missing full training/known-material
  reference snapshot.

## 2026-05-12: Guidance Consolidation And F1-F5 Alignment

- Removed `docs/guidance/00_reading_order.md`.
- Made `AGENTS.md` the startup entrypoint.
- Updated failure schema and docs so F1-F5 are represented:
  - F1 geometry
  - F2 chemistry
  - F3 stability
  - F4 novelty leakage
  - F5 synthesizability
- Kept FSAL/DPO pair mining centered on F1-F3; F4 can filter/quality-weight, F5
  is recorded but not used as a pair axis.
- Committed and pushed to `main`:
  - `93f43e2 docs: consolidate FIIR v2.2 guidance`
  - `d6d6a20 feat: align failure schema with F1-F5 guidance`
  - `472fc12 feat: add offline validation DPO import tools`
- Verification: `pytest -q` passed.

## 2026-05-12: Offline Validation And DPO Handoff Verification

Workspace check:

- `external/CrystalFormer` state: normal clone.
- checkpoint directory exists: `external/checkpoints/crystalformer/alex20s_csp`.

Key evidence artifacts:

- MACE single-point normalized validation:
  `outputs/mlip_validation_mace_overnight_20260512/normalized/validation_results.jsonl`
  - normalized rows: 3200
  - issue count: 0
  - F3 available count: 0
  - caveat: no hull or relaxation-derived stability label.
- MACE relaxation normalized validation:
  `outputs/mlip_validation_mace_relax_20260512/normalized/validation_results.jsonl`
  - normalized rows: 320
  - issue count: 0
  - F3 available count: 320
  - source: `local_mlip_mace_relaxation`
  - tier: `tier3_single_mlip`

DPO rebuild:

```bash
python scripts/build_crystalformer_dpo_preferences.py \
  --config configs/dpo_preference_builder.all_formula_mace_relax_20260512.json \
  --fail-on-zero-pairs
```

Result:

- input candidates: 320
- usable candidates: 320
- preference pairs: 284
- preference type breakdown: `stability_aware_offline_validation: 284`
- output:
  `outputs/dpo_preferences/mace_relax_20260512_rebuild_current_filtered/dpo_preferences_all_formula/`

DPO training boundary:

```bash
python scripts/prepare_crystalformer_dpo_training_boundary.py \
  --preference-pairs-jsonl outputs/dpo_preferences/mace_relax_20260512_rebuild_current_filtered/dpo_preferences_all_formula/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_training_boundary/mace_relax_20260512_rebuild_current_filtered \
  --crystalformer-work-dir external/CrystalFormer \
  --checkpoint-dir external/checkpoints/crystalformer/alex20s_csp
```

Result:

- ready for external training: true
- valid pairs: 284
- invalid pairs: 0
- stability-aware pairs: 284
- train DPO in FIIR: false
- warning: normal clone is OK for smoke/handoff, but fork/submodule is
  recommended for training.

Additional verification:

- `pytest -q` passed.
- No lingering `import_offline_validation_and_build_dpo.py` process remained.
- Git status was clean before adding this status documentation.

## 2026-05-12: Non-Overwriting CrystalFormer DPO Smoke Preparation

Implemented a FIIR-side DPO smoke-run preparer and a minimal CrystalFormer
loader patch for FIIR raw-sequence JSONL:

- FIIR additions:
  - `fiir_crystal/dpo/smoke_run.py`
  - `scripts/prepare_crystalformer_dpo_smoke_run.py`
  - `tests/test_prepare_crystalformer_dpo_smoke_run.py`
- CrystalFormer local branch: `fiir-dpo-adapter-smoke`
- CrystalFormer local edits:
  - `crystalformer/reinforce/dpo.py`: DPO deprecation is now a warning instead
    of an import-time hard raise.
  - `crystalformer/src/utils.py`: `GLXYZAW_from_file` can load FIIR raw
    `g/L/X/A/W` JSONL directly.

Prepared smoke package:

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

Result:

- prepared pairs: 284
- chosen/rejected JSONL rows: 284 / 284
- base checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- after-checkpoint output root:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/after_checkpoint/`
- run script:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/run_training.sh`
- training was not run; the prepared command should run only on an allocated
  compute node with the CrystalFormer environment active.

Verification:

- `pytest -q tests/test_prepare_crystalformer_dpo_smoke_run.py tests/test_dpo_preference_builder.py tests/test_build_crystalformer_dpo_preferences_cli.py` passed.
- `python -m py_compile fiir_crystal/dpo/smoke_run.py scripts/prepare_crystalformer_dpo_smoke_run.py` passed.
- `python -m py_compile external/CrystalFormer/crystalformer/src/utils.py external/CrystalFormer/crystalformer/reinforce/dpo.py` passed.

## 2026-05-12: CrystalFormer DPO Smoke Execution

Executed the prepared non-overwriting DPO smoke through SLURM, keeping the
before checkpoint untouched and writing all trained outputs under the prepared
`after_checkpoint/` directory.

Submission wrapper:

```bash
FIIR_DPO_RUN_SCRIPT=outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/run_training.sh \
sbatch scripts/slurm/run_crystalformer_dpo_smoke.slurm
```

Final successful job:

- job id: `98336`
- job name: `fiir-cf-dpo-smoke`
- state: `COMPLETED`
- exit code: `0:0`
- elapsed: `00:03:05`
- node: `gpu40902`
- stdout: `logs/slurm/fiir-cf-dpo-smoke_98336.log`
- stderr: `logs/slurm/fiir-cf-dpo-smoke_98336.err`

Produced after checkpoint:

```text
outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046001.pkl
```

Result details:

- base checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- restored epoch: 46000
- saved epoch: 46001
- checkpoint size: 159M
- checkpoint sha256:
  `42b11edfbf1586a1a8910e087616a5803486eba53b3901657c170c1b30c33fa6`
- reference logps:
  - chosen: `-879087.6875`
  - rejected: `-669711.0`
- training samples: 228
- validation samples: 56
- `data.txt` row:
  `46001 1253.308228 1253.308228 -729914.312500 -942742.937500 3654.330566 3654.330566 -971061.437500 -984123.187500`
- successful stderr contained XLA autotuning warnings only.

Debugging during execution:

- job `98317` showed the installed `train_dpo` entrypoint was importing the
  site-packages copy with the deprecation hard raise.
- job `98322` exposed CrystalFormer's newer `logp_fn` composition argument.
- job `98328` exposed batched composition lookup shape handling.
- job `98334` exposed tuple shuffling that assumed five fields instead of the
  DPO smoke's six fields including composition.
- the local CrystalFormer branch `fiir-dpo-adapter-smoke` now patches those
  smoke blockers in `crystalformer/reinforce/dpo.py` and
  `crystalformer/src/utils.py`.
- the same external CrystalFormer patch is exported in the main repository at
  `patches/crystalformer/fiir-dpo-adapter-smoke.patch` because
  `external/CrystalFormer` is a normal external clone rather than a tracked
  submodule.

Verification:

- `sacct -j 98336 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList -P`
  reported `COMPLETED|0:0`.
- `pytest -q tests/test_prepare_crystalformer_dpo_smoke_run.py` passed.
- `python -m py_compile fiir_crystal/dpo/smoke_run.py scripts/prepare_crystalformer_dpo_smoke_run.py external/CrystalFormer/crystalformer/reinforce/dpo.py external/CrystalFormer/crystalformer/src/utils.py` passed.
- `pytest -q` passed.

## 2026-05-12: DPO Smoke Before/After Generation Sanity

Prepared matched before/after CrystalFormer generation configs:

- before:
  `configs/generated/dpo_smoke_before_after/before_10x20_seed20260512.json`
- after:
  `configs/generated/dpo_smoke_before_after/after_10x20_seed20260512.json`
- scope: 10 formulas x 20 samples each
- sampling: seed `20260512`, `K=40`, `top_p=1.0`, `temperature=1.0`
- before checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- after checkpoint:
  `outputs/crystalformer_dpo_runs/mace_relax_20260512_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1`

Validate-only checks:

- before ready: true
- after ready: true
- blocking reasons: none

SLURM execution:

- before job `98383`: `COMPLETED`, exit `0:0`, elapsed `00:02:47`, node
  `gpu40902`
- initial after job `98385`: `CANCELLED` while pending, because it was waiting
  after the before node had become available
- after retry job `98407`: `COMPLETED`, exit `0:0`, elapsed `00:02:39`, node
  `gpu40902`

Artifacts:

- before output:
  `outputs/dpo_smoke_before_after/before_10x20_seed20260512/`
- after output:
  `outputs/dpo_smoke_before_after/after_10x20_seed20260512/`
- comparison summary:
  `outputs/dpo_smoke_before_after/comparison/summary.json`
- comparison report:
  `outputs/dpo_smoke_before_after/comparison/report.md`
- before QA:
  `outputs/dpo_smoke_before_after/qa_before/qa_summary.json`
- after QA:
  `outputs/dpo_smoke_before_after/qa_after/qa_summary.json`

Results:

- before: 10/10 formulas succeeded, 200 candidates, 200 DPO-eligible, 3 F1
  failures, 0 F2 failures, 200 F3 unknown, 57 geometry/chemistry preference
  pairs from smoke audit
- after: 10/10 formulas succeeded, 200 candidates, 200 DPO-eligible, 2 F1
  failures, 0 F2 failures, 200 F3 unknown, 38 geometry/chemistry preference
  pairs from smoke audit

- before and after single-root QA both reported `ready=true` with zero critical
  findings
- combined QA reports duplicate candidate ids because matched before/after runs
  intentionally reuse candidate-id namespaces for the same formulas and seed

Interpretation:

- The one-epoch DPO smoke checkpoint did not obviously break CrystalFormer
  generation or FIIR audit ingestion.
- This is not evidence of performance improvement: no offline validation was
  imported for these generated candidates, and F3 remains unknown for all 400
  generated candidates.

## 2026-05-12: Non-MACE MLIP Runner And CHGNet Smoke

Implemented the external non-MACE MLIP boundary:

- new runner: `scripts/run_mlip_offline_validation.py`
- new SLURM wrapper: `scripts/slurm/run_mlip_offline_validation.slurm`
- supported runner kinds: `chgnet`, `matgl`
- MatGL guard: real execution requires an explicit local model path to avoid
  implicit model downloads
- added `scripts/__init__.py` so direct script execution in conda environments
  imports local helper scripts instead of any site package named `scripts`
- docs updated in `README.md` and `docs/setup/mlip_validation_workspace.md`

Dry-run artifacts:

- CHGNet dry run:
  `outputs/mlip_validation_chgnet_dryrun_20260512/`
- CHGNet dry run in `matgalaxy`:
  `outputs/mlip_validation_chgnet_dryrun_matgalaxy_20260512/`
- MatGL dry run:
  `outputs/mlip_validation_matgl_dryrun_20260512/`

CHGNet SLURM smoke:

- first job `98547` failed before model execution because
  `scripts.run_mace_offline_validation` resolved incorrectly in the conda
  environment; fixed by making `scripts` a local package and forcing the repo
  root to the front of `sys.path` in the new runner.
- retry job `98551`: `COMPLETED`, exit `0:0`, elapsed `00:00:23`, node
  `gpu40904`
- raw output:
  `outputs/mlip_validation_chgnet_smoke_20260512/chgnet_validation_results.jsonl`
- normalized output:
  `outputs/mlip_validation_chgnet_smoke_20260512/normalized/validation_results.jsonl`
- normalized rows: 1
- unmatched candidate ids: 0
- formula mismatch count: 0
- failed/incomplete rows: 0
- F3 available candidates: 0
- validator/source: `chgnet_0_3_0` /
  `local_mlip_chgnet_single_point`
- example evidence row:
  - candidate: `crystalformer_output_AgNbO3_000001`
  - formula: `AgNbO3`
  - CHGNet package: `0.4.2`
  - torch: `2.6.0+cu124`
  - force_max: `19.561818528710795`
  - stress_max: `40.982086181640625`
  - CHGNet energy per atom: `-6.373408317565918`

Current interpretation:

- MACE remains the only production-scale MLIP result set.
- CHGNet now has a real end-to-end smoke path through SLURM and normalization.
- MatGL is dry-run/schema ready, but `matgalaxy` does not currently have
  `matgl`/`dgl`; real MatGL execution needs a separate environment and local
  model path.

Verification:

- `python -m pytest` passed: 188 tests.
- `bash -n scripts/slurm/run_mlip_offline_validation.slurm` passed.

## 2026-05-12: CHGNet Aligned 320 And MACE/CHGNet Consensus

Ran CHGNet over the same 320 hydrated candidates used for the current
MACE-relax DPO preference artifact.

Inputs:

- candidates:
  `outputs/mlip_validation_mace_relax_20260512_input/relaxation_candidates_full.jsonl`
- candidate index:
  `outputs/mlip_validation_mace_relax_20260512_input/candidate_index.jsonl`

CHGNet single-point run:

- SLURM job: `98567`, `fiir-chgnet-320`
- state: `COMPLETED`, exit `0:0`, elapsed `00:00:11`, node `gpu40904`
- output:
  `outputs/mlip_validation_chgnet_mace_relax_aligned_20260512/`
- normalized rows: 320
- unmatched candidate ids: 0
- formula mismatch count: 0
- failed/incomplete rows: 0
- F3 available candidates: 0
- source: `local_mlip_chgnet_single_point`
- QA report:
  `outputs/mlip_validation_ensemble_mace_chgnet_aligned_20260512/report.md`

CHGNet relaxation smoke:

- SLURM job: `98577`, `fiir-chgnet-relax`
- state: `COMPLETED`, exit `0:0`, elapsed `00:00:15`, node `gpu40904`
- output:
  `outputs/mlip_validation_chgnet_relax_smoke_20260512/`
- normalized rows: 16
- F3 available candidates: 16
- source: `local_mlip_chgnet_relaxation`

CHGNet relaxation full aligned run:

- SLURM job: `98588`, `fiir-chgnet-relax320`
- state: `COMPLETED`, exit `0:0`, elapsed `00:01:07`, node `gpu40904`
- output:
  `outputs/mlip_validation_chgnet_relax_mace_relax_aligned_20260512/`
- normalized rows: 320
- unmatched candidate ids: 0
- formula mismatch count: 0
- failed/incomplete rows: 0
- F3 available candidates: 320
- source: `local_mlip_chgnet_relaxation`
- caveat: stderr reported CHGNet isolated-atom warnings for some structures;
  treat high-risk/disagreement rows as candidates for stricter QA or DFT
  spot-check.

MACE/CHGNet relaxation proxy agreement:

- report:
  `outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/report.md`
- comparison rows:
  `outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/comparison_rows.jsonl`
- overlap: 320
- formula count: 64
- MACE stable proxy count: 131
- CHGNet stable proxy count: 139
- agreement rate: 0.75625
- both stable: 96
- both unstable: 146
- MACE stable / CHGNet unstable: 35
- MACE unstable / CHGNet stable: 43
- energy Pearson at candidate level: 0.9105276067567758

Consensus validation artifact:

- raw consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/consensus_validation_results.jsonl`
- normalized consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/normalized/validation_results.jsonl`
- normalized rows: 320
- F3 available candidates: 242
- stable consensus: 96
- unstable consensus: 146
- disagreement rows: 78
- calibration policy: `tier2_mlip_ensemble` when MACE and CHGNet relaxation
  proxies agree; `tier3_mlip_disagreement` with `is_stable=null` when they
  disagree.

Consensus DPO preference rebuild:

- command:
  `python scripts/import_offline_validation_and_build_dpo.py --validation-jsonl outputs/mlip_validation_ensemble_mace_chgnet_relax_20260512/normalized/validation_results.jsonl --audit-candidates-jsonl outputs/mlip_validation_mace_relax_20260512_input/candidate_index.jsonl --output-dir outputs/dpo_preferences/mace_chgnet_consensus_20260512_import_rebuild --fail-on-zero-stability-pairs`
- output:
  `outputs/dpo_preferences/mace_chgnet_consensus_20260512_import_rebuild/`
- updated audit:
  `outputs/dpo_preferences/mace_chgnet_consensus_20260512_import_rebuild/audit_candidates_with_validation.jsonl`
- preference pairs:
  `outputs/dpo_preferences/mace_chgnet_consensus_20260512_import_rebuild/dpo_preferences/preference_pairs.jsonl`
- audit candidates: 320
- validation records: 320
- matched: 320
- F3 available: 242
- validation/disagreement rows: 78
- preference pairs: 153
- stability-aware pairs: 153
- preference type breakdown:
  `{"stability_aware_offline_validation": 153}`

MatGL state:

- `matgalaxy` has `chgnet`, `torch`, `pymatgen`, and `ase`.
- `matgalaxy` does not currently have `matgl` or `dgl`.
- MatGL dry-runs passed via `scripts/run_mlip_offline_validation.py`, but real
  MatGL execution still needs a separate environment and explicit local model
  path.

## 2026-05-12: MatGL CUDA Rerun And Three-MLIP Consensus

Added MatGL to the external MLIP validation workflow and completed the aligned
320-candidate MatGL relaxation run after fixing CUDA placement.

Environment/model setup:

- installed `matgl==3.0.3` in the external `matgalaxy` environment
- backend: `MATGL_BACKEND=PYG`; DGL is not installed
- pretrained model:
  `M3GNet-PES-MatPES-PBE-2025.2`
- local model snapshot:
  `outputs/mlip_models/matgl/M3GNet-PES-MatPES-PBE-2025.2/models--materialyze--M3GNet-PES-MatPES-PBE-2025.2/snapshots/8414b23e68b173d6e36271e4366ee3717364051c`

Important debugging result:

- initial full MatGL relaxation job `98645` timed out after `01:00:26`
  despite being allocated `gres/gpu=7`
- live `nvidia-smi` showed 0% GPU utilization and no Python GPU processes
- probe showed `matgl.load_model(path, device="cuda")` left parameters on CPU
- fixed `scripts/run_mlip_offline_validation.py` to explicitly call
  `potential.to(actual_device)` after loading the MatGL potential

Corrected MatGL relaxation smoke:

- SLURM job: `99040`, `fiir-matgl-relax-gpucheck`
- state: `COMPLETED`, exit `0:0`, elapsed `00:00:57`, node `gpu40904`
- live GPU check showed Python processes on GPUs 0-3 with nonzero SM
  utilization
- output:
  `outputs/mlip_validation_matgl_relax_smoke_cuda_20260512/`
- normalized rows: 16
- F3 available candidates: 16

Corrected MatGL full aligned relaxation:

- SLURM job: `99042`, `fiir-matgl-relax320-cuda`
- state: `COMPLETED`, exit `0:0`, elapsed `00:01:03`, node `gpu40904`
- input:
  `outputs/mlip_validation_mace_relax_20260512_input/relaxation_candidates_full.jsonl`
- output:
  `outputs/mlip_validation_matgl_relax_mace_relax_aligned_cuda_20260512/`
- normalized output:
  `outputs/mlip_validation_matgl_relax_mace_relax_aligned_cuda_20260512/normalized/validation_results.jsonl`
- normalized rows: 320
- unmatched candidate ids: 0
- formula mismatch count: 0
- failed/incomplete rows: 0
- F3 available candidates: 320
- source: `local_mlip_matgl_relaxation`
- caveat: this is relaxation-threshold proxy evidence, not DFT or
  hull-confirmed stability.

Three-MLIP consensus:

- command:
  `python scripts/build_mlip_ensemble_consensus.py --validation mace=outputs/mlip_validation_mace_relax_20260512/normalized/validation_results.jsonl --validation chgnet=outputs/mlip_validation_chgnet_relax_mace_relax_aligned_20260512/normalized/validation_results.jsonl --validation matgl=outputs/mlip_validation_matgl_relax_mace_relax_aligned_cuda_20260512/normalized/validation_results.jsonl --output-dir outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_20260512 --validator-name mace_mpa_0_medium+chgnet_0_3_0+matgl_m3gnet_matpes_pbe_2025_2 --validation-source local_mlip_mace_chgnet_matgl_relaxation_consensus`
- output:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_20260512/`
- normalized consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_20260512/normalized/validation_results.jsonl`
- overlap: 320
- formula count: 64
- all-three agreement rate: 0.60625
- F3 available candidates: 194
- stable consensus: 85
- unstable consensus: 109
- disagreement rows: 126
- pairwise agreement rates:
  - MACE/CHGNet: 0.75625
  - MACE/MatGL: 0.721875
  - CHGNet/MatGL: 0.734375

Three-MLIP consensus DPO preference rebuild:

- command:
  `python scripts/import_offline_validation_and_build_dpo.py --validation-jsonl outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_20260512/normalized/validation_results.jsonl --audit-candidates-jsonl outputs/mlip_validation_mace_relax_20260512_input/candidate_index.jsonl --output-dir outputs/dpo_preferences/mace_chgnet_matgl_consensus_20260512_import_rebuild --fail-on-zero-stability-pairs`
- output:
  `outputs/dpo_preferences/mace_chgnet_matgl_consensus_20260512_import_rebuild/`
- preference pairs:
  `outputs/dpo_preferences/mace_chgnet_matgl_consensus_20260512_import_rebuild/dpo_preferences/preference_pairs.jsonl`
- audit candidates: 320
- validation records: 320
- matched: 320
- F3 available: 194
- preference pairs: 96
- stability-aware pairs: 96
- preference type breakdown:
  `{"stability_aware_offline_validation": 96}`

## 2026-05-13: Expanded 1024 Three-MLIP Relaxation Consensus

Expanded the strict MACE+CHGNet+MatGL relaxation-consensus workflow from the
original aligned 320 candidates to a new balanced 1024-candidate batch.

Candidate batch:

- command:
  `python scripts/build_mace_validation_batch.py --candidate-glob 'outputs/crystalformer_bulk_real_smoke_perovskite_128_32x1600_shard_*/smoke/crystalformer_audit/*/candidates.jsonl' --output-dir outputs/mlip_validation_three_mlip_1024_20260513_batch --per-formula-limit 16 --max-total 1024 --sort ranking --require-audit --require-dpo-eligible --require-f1-pass --require-f2-pass --exclude-validation-jsonl outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_20260512/normalized/validation_results.jsonl --strict`
- selected candidates:
  `outputs/mlip_validation_three_mlip_1024_20260513_batch/selected_candidates.jsonl`
- candidate index:
  `outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl`
- selected candidate count: 1024
- selected formula count: 64
- per-formula count: 16
- skipped candidate count: 101376
- load issue count: 0
- skip reasons: already validated 320, F1 not pass 2511,
  per-formula overflow 98545

Single-model relaxation runs:

- MACE:
  - SLURM job: `99186`, `fiir-mace-relax1024`, `COMPLETED`,
    elapsed `00:04:08`, node `gpu40904`
  - output:
    `outputs/mlip_validation_mace_relax_1024_20260513/normalized/validation_results.jsonl`
  - normalized rows: 1024
  - F3 available candidates: 1024
  - failed/incomplete rows: 0
  - issue count: 0
  - live GPU check: 8 Python GPU processes, nonzero SM utilization
- CHGNet:
  - SLURM job: `99196`, `fiir-chgnet-relax1024`, `COMPLETED`,
    elapsed `00:03:39`, node `gpu40904`
  - output:
    `outputs/mlip_validation_chgnet_relax_1024_20260513/normalized/validation_results.jsonl`
  - normalized rows: 1024
  - F3 available candidates: 1024
  - failed/incomplete rows: 0
  - issue count: 0
  - live GPU check: 8 Python GPU processes, around 20% SM utilization
- MatGL:
  - SLURM job: `99200`, `fiir-matgl-relax1024`, `COMPLETED`,
    elapsed `00:05:14`, node `gpu40904`
  - model: `M3GNet-PES-MatPES-PBE-2025.2`
  - backend: `MATGL_BACKEND=PYG`
  - output:
    `outputs/mlip_validation_matgl_relax_1024_20260513/normalized/validation_results.jsonl`
  - normalized rows: 1024
  - F3 available candidates: 1024
  - failed/incomplete rows: 0
  - issue count: 0
  - live GPU check: 8 Python GPU processes, around 16%-19% SM utilization

Three-MLIP consensus:

- command:
  `python scripts/build_mlip_ensemble_consensus.py --validation mace=outputs/mlip_validation_mace_relax_1024_20260513/normalized/validation_results.jsonl --validation chgnet=outputs/mlip_validation_chgnet_relax_1024_20260513/normalized/validation_results.jsonl --validation matgl=outputs/mlip_validation_matgl_relax_1024_20260513/normalized/validation_results.jsonl --output-dir outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513 --validator-name mace_mpa_0_medium+chgnet_0_3_0+matgl_m3gnet_matpes_pbe_2025_2 --validation-source local_mlip_mace_chgnet_matgl_relaxation_consensus`
- output:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/`
- normalized consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl`
- overlap: 1024
- formula count: 64
- all-three agreement rate: 0.642578125
- F3 available candidates: 658
- stable consensus: 186
- unstable consensus: 472
- disagreement or unavailable rows: 366
- pairwise agreement rates:
  - MACE/CHGNet: 0.76171875
  - MACE/MatGL: 0.7490234375
  - CHGNet/MatGL: 0.7744140625
- pairwise energy Pearson:
  - MACE/CHGNet: 0.8016007981667927
  - MACE/MatGL: 0.8447657796203446
  - CHGNet/MatGL: 0.7874871617358663
- calibration policy: `tier2_mlip_ensemble` only when all three relaxation
  proxies agree; `tier3_mlip_disagreement` with `is_stable=null` when they
  disagree.

Expanded consensus DPO preference rebuild:

- command:
  `python scripts/import_offline_validation_and_build_dpo.py --validation-jsonl outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl --audit-candidates-jsonl outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl --output-dir outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild --fail-on-zero-stability-pairs`
- output:
  `outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild/`
- preference pairs:
  `outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild/dpo_preferences/preference_pairs.jsonl`
- audit candidates: 1024
- validation records: 1024
- matched: 1024
- F3 available: 658
- preference pairs: 1040
- stability-aware pairs: 1040
- preference type breakdown:
  `{"stability_aware_offline_validation": 1040}`
- caveat: this remains MLIP relaxation-threshold proxy evidence, not DFT or
  hull-confirmed stability.

GPU utilization audit:

- reason checked: CHGNet and MatGL showed low per-GPU memory use and modest SM
  utilization during the 1024-candidate relaxation runs.
- code path:
  - parent worker pool launches one child process per worker.
  - each child receives `--workers 1`, a unique `--shard-index`, and
    `CUDA_VISIBLE_DEVICES` set to one GPU id.
  - MatGL runtime loads the explicit local model path and then calls
    `potential.to(actual_device)` before constructing the ASE calculator.
- run evidence:
  - MatGL summary recorded 8 workers with shard-level `CUDA_VISIBLE_DEVICES`
    values `0` through `7`.
  - every MatGL shard completed 128 rows with failed count 0.
  - live `nvidia-smi` during the MatGL run showed 8 Python GPU processes and
    nonzero SM utilization on all 8 GPUs.
  - CHGNet showed the same 8-shard GPU binding pattern and completed all
    1024 rows.
- conclusion: no code-level GPU dispatch bug was found. The modest utilization
  is expected for these small perovskite structures and ASE/optimizer-driven
  relaxation loops, where each step runs small graph kernels with Python and
  launch overhead. The prior MatGL CPU-only issue is covered by an added unit
  test that verifies the loaded potential is explicitly moved to the requested
  CUDA device.

## 2026-05-13: 1024 Strict Three-MLIP CrystalFormer DPO Handoff/Smoke Prepare

Intent:

- Promote the current preferred 1024-candidate strict MACE+CHGNet+MatGL
  consensus DPO preference artifact into a non-overwriting CrystalFormer DPO
  handoff and smoke-prepare package.
- Keep FIIR as a boundary/handoff layer only; no local DPO training,
  CrystalFormer generation, MLIP, DFT, or long evaluation was run.

Input preference artifact:

```text
outputs/dpo_preferences/mace_chgnet_matgl_consensus_1024_20260513_import_rebuild/dpo_preferences/preference_pairs.jsonl
```

Input evidence context:

- input candidates: 1024
- strict consensus F3-available candidates: 658
- disagreement candidates excluded from F3: 366
- preference pairs: 1040
- preference type: `stability_aware_offline_validation`
- source validation:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_1024_20260513/normalized/validation_results.jsonl`
- caveat: labels are MLIP relaxation proxy evidence from strict
  MACE+CHGNet+MatGL consensus, not DFT evidence and not self-consistent
  hull-confirmed stability.

Training boundary result:

- manifest:
  `outputs/crystalformer_dpo_training_boundary/mace_chgnet_matgl_consensus_1024_20260513/trainer_manifest.json`
- report:
  `outputs/crystalformer_dpo_training_boundary/mace_chgnet_matgl_consensus_1024_20260513/report.md`
- command provenance:
  `outputs/crystalformer_dpo_training_boundary/mace_chgnet_matgl_consensus_1024_20260513/training_command_provenance.json`
- ready for external training: true
- train DPO in FIIR: false
- input/valid/invalid pairs: 1040 / 1040 / 0
- stability-aware pairs: 1040
- warning: `external/CrystalFormer` is a normal clone; fork/submodule remains
  recommended for future training work.

DPO smoke-prepare result:

- manifest:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/dpo_smoke_manifest.json`
- run script:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/run_training.sh`
- chosen/rejected JSONL:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/chosen_sequences.jsonl`
  and
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/rejected_sequences.jsonl`
- pair index:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/pair_index.jsonl`
- matched before/after validation plan:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/before_after_validation_plan.md`
- prepared pairs: 1040
- chosen/rejected rows: 1040 / 1040
- base checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- after-checkpoint root:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/after_checkpoint/`
- after checkpoint produced: none; no SLURM smoke was submitted in this turn.
- non-overwrite status: new output directory; after root is separate from the
  base checkpoint and from the older MACE-only smoke package.

Next validation gate:

- If a SLURM smoke later completes, record job id, exit code, elapsed time,
  node, stdout/stderr, after-checkpoint path, size, sha256, loss row, stderr
  caveat, and traceback status.
- Then run matched before/after generation with identical formulas, seed,
  sampling parameters, and candidate count. Use 10 formulas x 20 samples for
  sanity, then 64 formulas x 20 or 64 formulas x 40 for a stronger comparison.
- Import offline MACE+CHGNet+MatGL relaxation consensus evidence before any
  performance claim. Report counts, DPO eligible count, F1/F2 fail rates,
  F3 availability, strict stable/unstable/disagreement counts, all-three and
  pairwise agreement rates, stable consensus rate, diversity/collapse signals,
  formula/prototype coverage, preference-pair yield, and reward-hacking or
  proxy-divergence signals.

Verification:

- `pytest -q` passed.

## 2026-05-13: 1024 Strict Three-MLIP CrystalFormer DPO Smoke Execution

Intent:

- Execute the prepared non-overwriting CrystalFormer DPO smoke for the
  1024-candidate strict MACE+CHGNet+MatGL consensus preference artifact through
  SLURM on GPUs.
- Confirm the job uses JAX GPU execution, not CPU-only execution on a GPU node.

Submission:

```bash
sbatch --nodes 1 \
  --partition gpu4090_8 \
  --job-name fiir-cf-dpo-1024smoke \
  --gres gpu:rtx4090:8 \
  --account hmt03 \
  --time 00:30:00 \
  --exclusive \
  --ntasks 1 \
  --cpus-per-task 32 \
  --export ALL,FIIR_DPO_RUN_SCRIPT=outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/run_training.sh,FIIR_REQUIRE_JAX_GPU=1,FIIR_CONDA_ENV=crystalformer,FIIR_TOTAL_GPUS=8,FIIR_GPU_PARTITION=gpu4090_8,FIIR_GPU_GRES=gpu:rtx4090:8 \
  --output logs/slurm/%x_%j.log \
  --error logs/slurm/%x_%j.err \
  scripts/slurm/run_crystalformer_dpo_smoke.slurm
```

SLURM result:

- job id: `99443`
- job name: `fiir-cf-dpo-1024smoke`
- state: `COMPLETED`
- exit code: `0:0`
- elapsed: `00:03:08`
- node: `gpu40902`
- stdout: `logs/slurm/fiir-cf-dpo-1024smoke_99443.log`
- stderr: `logs/slurm/fiir-cf-dpo-1024smoke_99443.err`
- execution provenance:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/slurm_execution_provenance.json`

GPU evidence:

- requested GRES: `gpu:rtx4090:8`
- `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`
- `FIIR_TOTAL_GPUS=8`
- `FIIR_REQUIRE_JAX_GPU=1`
- `jax_default_backend=gpu`
- `jax_devices`: `CudaDevice(id=0)` through `CudaDevice(id=7)`

Produced after checkpoint:

```text
outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046001.pkl
```

Checkpoint provenance:

- base checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- restored epoch: 46000
- saved epoch: 46001
- after checkpoint size: 159M
- after checkpoint sha256:
  `f22dd30a4ae53ed3c6f8dbc485ee25c1177e40fbaeaf62682d1aabdfc4265aa1`

Training details:

- prepared pairs: 1040
- training samples: 832
- validation samples: 208
- reference logps:
  - chosen: `-4314301.0`
  - rejected: `-1816139.875`
- `data.txt` row:
  `46001 1281.960815 1281.960815 -3809575.750000 -1924038.250000 307.132141 307.132141 -3188903.500000 -2261599.500000`
- loss / dpo_loss: 1281.960815 / 1281.960815
- val loss / val dpo_loss: 307.132141 / 307.132141

stderr / caveats:

- stderr contained XLA GPU autotuning warnings in the inspected tail.
- `rg` over stdout/stderr found no `Traceback`, `Error`, `Exception`,
  `JAX default backend is not gpu`, or `not gpu` marker.
- This smoke proves the external DPO training boundary can run on GPUs and
  write a non-overwriting after checkpoint. It is not evidence of DPO model
  improvement until matched before/after generation and offline
  MACE+CHGNet+MatGL relaxation consensus validation are imported.
- The underlying 1024 strict MACE+CHGNet+MatGL consensus labels are MLIP
  relaxation proxy evidence, not DFT evidence and not self-consistent
  hull-confirmed stability.

## 2026-05-13: 1024 Strict Three-MLIP Before/After Generation Config Prepare

Intent:

- Prepare the next matched before/after generation sanity gate for the
  completed 1024 strict-consensus DPO smoke checkpoint.
- Keep the generation itself as a future GPU SLURM workflow; only local
  validate-only checks were run here.

Prepared configs:

- before:
  `configs/generated/dpo_strict3mlip_1024_before_after/before_10x20_seed20260513.json`
- after:
  `configs/generated/dpo_strict3mlip_1024_before_after/after_10x20_seed20260513.json`

Matched generation settings:

- scope: 10 formulas x 20 samples for before and after
- seed: 20260513
- sampling: `K=40`, `top_p=1.0`, `temperature=1.0`
- before checkpoint: `external/checkpoints/crystalformer/alex20s_csp`
- after checkpoint:
  `outputs/crystalformer_dpo_runs/mace_chgnet_matgl_consensus_1024_20260513_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1`

Validate-only commands:

```bash
python scripts/run_crystalformer_bulk_generation.py \
  --config configs/generated/dpo_strict3mlip_1024_before_after/before_10x20_seed20260513.json \
  --validate-only

python scripts/run_crystalformer_bulk_generation.py \
  --config configs/generated/dpo_strict3mlip_1024_before_after/after_10x20_seed20260513.json \
  --validate-only
```

Validate-only result:

- before ready_for_generation: true
- after ready_for_generation: true
- before / after formula count: 10 / 10
- before / after total samples: 200 / 200
- blocking reasons: none for both configs
- warnings: none for both configs
- before output root:
  `outputs/dpo_strict3mlip_1024_before_after/before_10x20_seed20260513/`
- after output root:
  `outputs/dpo_strict3mlip_1024_before_after/after_10x20_seed20260513/`

Next gate:

- Submit both generation configs through the GPU SLURM wrapper.
- Treat generation/audit F1/F2 sanity as structural QA only.
- Import offline MACE+CHGNet+MatGL relaxation consensus F3 proxy evidence
  before making any before/after performance claim.

## 2026-05-13: 1024 Strict Three-MLIP Before/After Generation Sanity Run

Intent:

- Execute the prepared matched before/after CrystalFormer generation sanity gate
  for the 1024 strict MACE+CHGNet+MatGL consensus DPO smoke checkpoint.
- Use GPU SLURM execution only; do not run local CrystalFormer generation,
  MLIP relaxation, DFT, or long evaluation on the login node.

Submitted jobs:

- before: job `99459`, `fiir-dpo1024-before-test`, partition `test`, node
  `test001`, `COMPLETED`, exit `0:0`, elapsed `00:09:54`
- after: job `99467`, `fiir-dpo1024-after-test`, partition `test`, node
  `test001`, `COMPLETED`, exit `0:0`, elapsed `00:04:59`
- requested GRES for both: `gpu:rtx4090:2`
- logs:
  - `logs/slurm/fiir-dpo1024-before-test_99459.log`
  - `logs/slurm/fiir-dpo1024-before-test_99459.err`
  - `logs/slurm/fiir-dpo1024-after-test_99467.log`
  - `logs/slurm/fiir-dpo1024-after-test_99467.err`

GPU and stderr evidence:

- before: `jax_default_backend=gpu`; JAX saw two CUDA devices; the bulk wrapper
  used worker device `0` because the first `sbatch --export` path preserved
  only the first comma-separated GPU device value.
- after: `jax_default_backend=gpu`; JAX saw two CUDA devices; the corrected
  environment-prefix submit path preserved `FIIR_GPU_DEVICES=0,1` and the bulk
  wrapper used both worker devices.
- both stderr files had 0 lines.
- `rg` over stdout/stderr found no `Traceback`, `Error`, `Exception`,
  `JAX default backend is not gpu`, or `not gpu` marker.

Outputs:

- before root:
  `outputs/dpo_strict3mlip_1024_before_after/before_10x20_seed20260513/`
- after root:
  `outputs/dpo_strict3mlip_1024_before_after/after_10x20_seed20260513/`
- comparison summary:
  `outputs/dpo_strict3mlip_1024_before_after/comparison_10x20_seed20260513/summary.json`
- comparison report:
  `outputs/dpo_strict3mlip_1024_before_after/comparison_10x20_seed20260513/report.md`
- read-only strict QA summaries:
  - combined:
    `outputs/dpo_strict3mlip_1024_before_after/qa_before_after_10x20_seed20260513/qa_summary.json`
  - before:
    `outputs/dpo_strict3mlip_1024_before_after/qa_before_10x20_seed20260513/qa_summary.json`
  - after:
    `outputs/dpo_strict3mlip_1024_before_after/qa_after_10x20_seed20260513/qa_summary.json`

Generation counts:

| side | formulas completed | candidates | DPO eligible | F1 fails | F2 fails | F3 available | F3 unknown | generated preference pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| before | 10 / 10 | 200 | 200 | 7 | 0 | 0 | 200 | 130 |
| after | 10 / 10 | 200 | 200 | 3 | 0 | 0 | 200 | 76 |

QA and caveats:

- Strict QA reported `ready: false`: 6 formulas per side produced zero
  generated preference-pair artifacts, and the combined before/after scan also
  flagged duplicate candidate ids across matched roots.
- Candidate generation itself completed and all 400 generated candidates parsed
  as full structures across before and after. Treat this as structural
  generation sanity only.
- The F1/F2 counts and generated preference-pair yield are not evidence that
  DPO improved the model. No F3 offline validation has been imported for these
  generated candidates.
- The 1024 strict MACE+CHGNet+MatGL consensus labels remain MLIP relaxation
  proxy evidence, not DFT evidence and not self-consistent hull-confirmed
  stability.

Next gate:

- Run/import matched MACE+CHGNet+MatGL relaxation consensus validation for the
  before and after roots with identical formula/sample coverage.
- The first performance-facing report must include candidate count, DPO eligible
  count, F1/F2 fail rates, F3 available count, strict stable consensus count,
  unstable consensus count, disagreement count, all-three and pairwise
  agreement rates, stable consensus rate, diversity/collapse signals,
  composition/formula coverage, prototype or structural coverage,
  preference-pair yield, and reward-hacking/proxy-divergence checks.

## 2026-05-13: Add `test` to GPU Scheduling Policy with Time Guard

Intent:

- Treat the `test` partition as GPU-capable scheduling capacity because it has
  RTX 4090 GPUs.
- Prevent accidental long GPU jobs from landing on `test`, while keeping `test`
  in the same resource-based ranking as all other GPU partitions.

Policy change:

- `test` remains in the CUDA-compatible GPU partition hints.
- GPU planner selection still ranks by the normal compute-resource score:
  `free_gpus * gpu_weight[precision_profile][gpu_model]`.
- The only special `test` rule is a time guard: it requires an explicit time
  limit of 30 minutes or less before `test` can be selected.
- If GPU `--time` / `FIIR_TIME_LIMIT` is absent, or if it exceeds 30 minutes,
  `test` is skipped even when idle.
- The policy is recorded in planner config as:
  - `test_partition: test`
  - `test_partition_max_minutes: 30`
  - `time_limit_minutes: <parsed requested limit>`

Touched files:

- `fiir_crystal/slurm_gpu_policy.py`
- `fiir_crystal/slurm_scheduling.py`
- `scripts/slurm/plan_slurm_job.py`
- `scripts/slurm/plan_gpu_job.py`
- `scripts/slurm/submit_crystalformer_bulk_gpu.sh`
- `scripts/slurm/README.md`
- `tests/test_slurm_gpu_policy.py`
- `tests/test_slurm_submission_template.py`

Validation:

- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed.
- Fixture planner check accepted `test001` with `--time 00:30:00`.
- Fixture planner check rejected `test001` with no `--time` and with
  `--time 00:31:00`.
- Fixture planner check with both `test001` and a larger idle `gpu4090_8` node
  selected `gpu40902`, confirming `test` still uses the same resource ranking
  and is not preferred merely because the job is short.

Caveat:

- This was a scheduling-policy edit only. It did not submit new SLURM jobs,
  run CrystalFormer generation, run MLIP validation, run DFT, or alter the
  1024 strict-consensus DPO artifacts.

## 2026-05-13: Start 1024 Strict Three-MLIP Before/After Offline Validation

Intent:

- Run/import matched MACE+CHGNet+MatGL relaxation consensus validation for the
  completed 10 formulas x 20 samples before/after DPO smoke generation roots.
- Use GPU SLURM only for MLIP relaxation; do not run MLIP, DFT, CrystalFormer
  generation, or training directly on the login node.
- Preserve the caveat that these labels are MLIP relaxation proxy evidence, not
  DFT evidence and not self-consistent hull-confirmed stability.

Prepared candidate batches:

- before selected candidates:
  `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_20260513_batch/before/selected_candidates.jsonl`
- before candidate index:
  `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_20260513_batch/before/candidate_index.jsonl`
- after selected candidates:
  `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_20260513_batch/after/selected_candidates.jsonl`
- after candidate index:
  `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_20260513_batch/after/candidate_index.jsonl`
- counts: 200 selected/indexed candidates for before and 200 selected/indexed
  candidates for after
- candidate ID guard: before IDs are prefixed with `before__`; after IDs are
  prefixed with `after__`, while original IDs are preserved in metadata.

Scheduler setup:

- allowed GPU partitions: `gpu4090_8,test`
- requested time limit: `00:30:00`
- requested GRES per job: `gpu:rtx4090:2`
- precision profile: `fp64`
- `test` partition policy: eligible only for jobs with explicit time limit
  `<= 00:30:00`; still uses the same resource-based GPU ranking as other
  partitions.

Initial cancelled submissions:

- jobs `101119`-`101122` targeted the initial `gpu4090` plan and were cancelled
  before running because the partition/node state was not usable for these
  submissions. They produced no validation outputs.

Active/resubmitted validation jobs:

| validator | side | job | partition | node/state at latest record | output directory |
| --- | --- | ---: | --- | --- | --- |
| MACE | before | 101126 | test | `COMPLETED`, `test001`, exit `0:0`, elapsed `00:04:04` | `outputs/mlip_validation_mace_relax_dpo_strict3mlip_1024_before_20260513` |
| MACE | after | 101127 | test | `COMPLETED`, `test001`, exit `0:0`, elapsed `00:02:57` | `outputs/mlip_validation_mace_relax_dpo_strict3mlip_1024_after_20260513` |
| CHGNet | before | 101128 | test | `COMPLETED`, `test001`, exit `0:0`, elapsed `00:02:59` | `outputs/mlip_validation_chgnet_relax_dpo_strict3mlip_1024_before_20260513` |
| CHGNet | after | 101129 | test | submitted via GPU wrapper; refresh SLURM before final import | `outputs/mlip_validation_chgnet_relax_dpo_strict3mlip_1024_after_20260513` |
| MatGL | before | 101130 | test | running at latest local check; log shows `device=cuda`, `CUDA_VISIBLE_DEVICES=0,1` | `outputs/mlip_validation_matgl_relax_dpo_strict3mlip_1024_before_20260513` |
| MatGL | after | 101131 | test | pending at latest local check | `outputs/mlip_validation_matgl_relax_dpo_strict3mlip_1024_after_20260513` |

Completed normalized outputs so far:

- MACE before: 200 normalized rows, 0 issues, 0 unmatched IDs, 200 F3 proxy
  available rows
- MACE after: 200 normalized rows, 0 issues, 0 unmatched IDs, 200 F3 proxy
  available rows
- CHGNet before: 200 normalized rows, 0 issues, 0 unmatched IDs, 200 F3 proxy
  available rows

Provenance artifacts:

- partial manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/run_manifest_partial.json`
- runbook:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/README.md`
- planned before consensus output:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_before_20260513`
- planned after consensus output:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_after_20260513`
- planned final comparison:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_comparison_10x20_seed20260513`
- prepared readiness check:
  `scripts/check_dpo_offline_validation_ready.py`

Lightweight local validation:

- `pytest -q` passed after the scheduling, batch-prefix, and comparison-report
  code changes.
- `pytest -q tests/test_check_dpo_offline_validation_ready.py tests/test_compare_dpo_before_after_mlip_consensus.py tests/test_mace_validation_batch_builder.py`
  passed.
- `scripts/compare_dpo_before_after_mlip_consensus.py --help` works.
- `python -m py_compile scripts/compare_dpo_before_after_mlip_consensus.py scripts/build_mlip_ensemble_consensus.py scripts/build_mace_validation_batch.py`
  passed.

Pre-completion caveat:

- At this point in the run it was still an in-progress offline-validation
  import. Do not make
  before/after performance claims until all six validator outputs are
  normalized, the strict three-MLIP consensus artifacts are built, and the
  matched comparison report is generated.
- The resulting F3 labels are MACE+CHGNet+MatGL relaxation consensus proxy
  evidence, not DFT evidence and not self-consistent hull-confirmed stability.

## 2026-05-13: Complete 1024 Strict Three-MLIP Before/After Offline Validation

Intent:

- Finish the matched before/after MACE+CHGNet+MatGL relaxation validation gate
  for the 1024 strict-consensus DPO smoke.
- Build local strict three-MLIP consensus artifacts only after the readiness
  gate confirms all six normalized validator outputs exist with matched
  200-row coverage.
- Compare before/after from imported F3 proxy evidence plus diversity/coverage
  checks, without presenting this 10x20 smoke as a production performance
  claim.

Final SLURM job provenance:

| validator | side | job | state | elapsed | node | requested/allocated GPU |
| --- | --- | ---: | --- | ---: | --- | --- |
| MACE | before | 101126 | `COMPLETED`, exit `0:0` | `00:04:04` | `test001` | `gres/gpu=2` |
| MACE | after | 101127 | `COMPLETED`, exit `0:0` | `00:02:57` | `test001` | `gres/gpu=2` |
| CHGNet | before | 101128 | `COMPLETED`, exit `0:0` | `00:02:59` | `test001` | `gres/gpu=2` |
| CHGNet | after | 101129 | `COMPLETED`, exit `0:0` | `00:09:47` | `test001` | `gres/gpu=2` |
| MatGL | before | 101130 | `COMPLETED`, exit `0:0` | `00:12:35` | `test001` | `gres/gpu=2` |
| MatGL | after | 101131 | `COMPLETED`, exit `0:0` | `00:09:38` | `test001` | `gres/gpu=2` |

GPU and wrapper evidence:

- All six jobs ran through existing SLURM wrappers on the `test` GPU partition
  with requested time `00:30:00`.
- The `test` partition was eligible because the explicit time limit was within
  the 30-minute guard; it remained part of normal resource ranking.
- MatGL logs show `device=cuda` and `CUDA_VISIBLE_DEVICES=0,1`; CHGNet logs
  repeatedly reported `CHGNet will run on cuda`; MACE logs used
  `device=cuda`.
- No validation job ran MLIP locally on the login node.

Readiness:

- readiness summary:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/readiness_summary.json`
- readiness result: true
- all six normalized validator JSONL files exist with 200 rows each.

Consensus outputs:

- before consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_before_20260513/`
- after consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_after_20260513/`
- before consensus summary: overlap 200, F3 available 125, stable consensus 52,
  unstable consensus 73, disagreement 75, all-three agreement rate 0.625
- after consensus summary: overlap 200, F3 available 130, stable consensus 58,
  unstable consensus 72, disagreement 70, all-three agreement rate 0.65
- pairwise agreement rates:
  - before: CHGNet/MatGL 0.725, MACE/CHGNet 0.75, MACE/MatGL 0.775
  - after: CHGNet/MatGL 0.72, MACE/CHGNet 0.755, MACE/MatGL 0.825

Final comparison:

- summary:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_comparison_10x20_seed20260513/summary.json`
- report:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_comparison_10x20_seed20260513/report.md`
- final manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_10x20_seed20260513/run_manifest_final.json`
- final log scan: no `Traceback`, `Exception`, `Error`, CPU-only GPU preflight
  marker, or `not gpu` marker was found in the six validation stdout logs.
- final lightweight tests: `pytest -q` passed after the local import/report
  scripts and artifacts were prepared.

Matched before/after metrics:

| metric | before | after | delta |
| --- | ---: | ---: | ---: |
| candidates | 200 | 200 | 0 |
| DPO eligible | 200 | 200 | 0 |
| F1 fail rate | 0.035 | 0.015 | -0.02 |
| F2 fail rate | 0.0 | 0.0 | 0.0 |
| F3 available | 125 | 130 | +5 |
| strict stable consensus | 52 | 58 | +6 |
| unstable consensus | 73 | 72 | -1 |
| disagreement | 75 | 70 | -5 |
| all-three agreement rate | 0.625 | 0.65 | +0.025 |
| stable consensus rate | 0.26 | 0.29 | +0.03 |
| preference-pair yield | 130 | 76 | -54 |
| unique sequence fraction | 1.0 | 1.0 | 0.0 |
| spacegroup count | 46 | 46 | 0 |
| spacegroup entropy | 3.68908 | 3.69188 | +0.00280 |
| formula count | 10 | 10 | 0 |

Interpretation and caveats:

- The 10x20 smoke shows a small positive strict-consensus proxy shift after DPO:
  stable consensus +6, stable consensus rate +0.03, F3 available +5,
  disagreement -5, and F1 fail rate -0.02.
- Diversity/collapse smoke signals did not degrade in this report: formula
  coverage stayed balanced at 10 formulas x 20 samples, unique sequence
  fraction stayed 1.0, and spacegroup count stayed 46.
- Generated preference-pair yield decreased by 54; this should be monitored in
  the larger audit rather than ignored.
- The proxy-divergence screen did not flag this small run, but absence of a
  flag in a 10x20 smoke is not proof that reward hacking is absent.
- These labels are MLIP relaxation consensus proxy evidence, not DFT evidence
  and not self-consistent hull-confirmed stability. Do not use this as a DFT or
  hull-stability claim.

Next gate:

- Run the same matched before/after evaluation at larger scale, starting with
  64 formulas x 20 samples and then 64 formulas x 40 if the first scale-up is
  clean.
- Keep base/after checkpoints, seed, formulas, sampling parameters, and
  candidate count matched.
- Continue reporting agreement, disagreement, diversity/collapse, formula and
  structural coverage, preference-pair yield, and proxy-divergence signals,
  rather than a single stable-rate number.

## 2026-05-13: Defer Larger Before/After Validation Until GPU Resources Are Available

Intent:

- Record that the next larger matched before/after validation gate should not
  be submitted immediately because current GPU compute resources are
  insufficient.
- Leave a clear restart marker for a future session when GPU capacity is
  available.
- Avoid starting any new CrystalFormer generation, MLIP validation, DFT, or
  long evaluation work on the login node.

Deferred marker artifacts:

- marker:
  `outputs/dpo_strict3mlip_1024_before_after/deferred_64x20_gpu_resources_20260513/defer_marker.json`
- runbook:
  `outputs/dpo_strict3mlip_1024_before_after/deferred_64x20_gpu_resources_20260513/README.md`

Deferred gate:

- first scale-up: 64 formulas x 20 samples, matched before/after
- optional follow-up: 64 formulas x 40 samples if the first scale-up is clean
- keep base/after checkpoints, seed, sampling parameters, formulas, and
  candidate count matched
- use only existing SLURM wrappers or project submit wrappers
- keep the `test` partition constrained to explicit jobs of 30 minutes or less;
  otherwise use normal GPU resource ranking

Caveat:

- The completed 10x20 smoke and the deferred larger gate are MLIP relaxation
  consensus proxy evidence, not DFT evidence and not self-consistent
  hull-confirmed stability.

## 2026-05-13: Update Operating Rules For Long SLURM Jobs, GitHub Uploads, And Large GPU Queueing

Intent:

- Make three project operating rules durable in `AGENTS.md`, status docs, and
  the SLURM runbook: do useful safe work while long SLURM jobs run, judge
  GitHub upload at task end, and queue larger GPU jobs across multiple eligible
  partitions/nodes.

Implementation summary:

- Added the long-SLURM waiting rule and end-of-task GitHub upload check to
  `AGENTS.md`.
- Added `FIIR_GPU_QUEUE_MODE=auto|pinned|flexible` to the GPU scheduling
  policy. In auto mode, the planner first keeps the original resource-aware
  pinned GPU selection and uses flexible multi-partition queueing only when no
  eligible long-running GPU node has enough free resources.
- Flexible GPU queueing does not use `--nodelist`; it queues on candidate GPU
  partitions and lets SLURM assign the final node at runtime. The `test`
  partition remains eligible only for explicitly bounded jobs of 30 minutes or
  less.
- Documented that GPU jobs must request actual GPUs with `--gres`, using
  `FIIR_GPU_MIN_GPUS` / `--min-gpus` to set the intended GPU count for larger
  flexible jobs, rather than landing on GPU nodes for CPU-only work.
- Updated the CrystalFormer GPU submitter to pass the queue mode through the
  existing unified SLURM planner rather than adding a separate submission path.

Validation scope:

- Lightweight local tests only:
  `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed with 24 tests, and
  `pytest -q tests/test_imports.py tests/test_mock_fiir_loop.py tests/test_lightweight_fiir_v1.py tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed with 45 tests.
- No CrystalFormer generation, MLIP validation, DFT, DPO training, or long GPU
  work was started from the login node.

GitHub upload check:

- These rule and scheduler changes are durable and should eventually be
  uploaded, but no automatic commit/push was made in this turn because the
  current worktree already contains many pre-existing modified and untracked
  files from earlier DPO/validation work. A safe upload should first choose a
  clean commit scope or finish/stage the earlier artifact-chain changes.

Caveat:

- This is a scheduling/rule update only. It does not change the scientific
  evidence state: existing strict three-MLIP labels remain MLIP relaxation
  proxy evidence, not DFT evidence and not self-consistent hull-confirmed
  stability.

## 2026-05-13: Correct GPU Auto Queue Fallback Policy

Intent:

- Restore the original GPU scheduling priority for `FIIR_GPU_QUEUE_MODE=auto`:
  use the best currently free eligible GPU node first, and only submit a
  flexible multi-partition queue job when no eligible long-running GPU node has
  enough free resources.
- Confirm `h20llm` is handled as CUDA-compatible H20 capacity when selecting GPU
  resources.

Implementation summary:

- Updated `plan_gpu_job()` so `auto` first calls the normal resource-aware
  pinned selector and submits with `--nodelist` when a suitable free node
  exists.
- Kept explicit `FIIR_GPU_QUEUE_MODE=flexible` as an override for callers that
  intentionally want immediate multi-partition queueing.
- Auto fallback now builds a flexible plan only after pinned selection fails;
  the fallback still excludes `test` for jobs without an explicit time limit or
  with a requested time greater than 30 minutes.
- Added a regression test showing a long job with a free H200 node stays pinned,
  another showing auto falls back to flexible queueing only when long-running
  GPU nodes are fully allocated, and another showing an `h20llm` partition uses
  H20 CUDA/GRES parameters.

Validation scope:

- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed with 26 tests.
- `pytest -q tests/test_imports.py tests/test_mock_fiir_loop.py tests/test_lightweight_fiir_v1.py tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed with 47 tests.
- Lightweight local tests only; no CrystalFormer generation, MLIP validation,
  DFT, DPO training, or long GPU work was started from the login node.

Caveat:

- This scheduling correction does not change the scientific evidence state:
  strict three-MLIP labels remain MLIP relaxation proxy evidence, not DFT
  evidence and not self-consistent hull-confirmed stability.

## 2026-05-13: Submit 64x20 Matched Before/After Generation Shards

Intent:

- Start the deferred 64 formulas x 20 samples matched before/after
  CrystalFormer generation gate through the project GPU SLURM wrapper.
- Keep the task on GPU resources, not CPU-only execution on GPU nodes.
- Preserve a non-overwriting artifact chain for later matched
  MACE+CHGNet+MatGL offline validation import.

Prepared artifacts:

- formula bank:
  `configs/generated/dpo_strict3mlip_1024_before_after/perovskite_first64_formula_bank_seed20260513.json`
- before shard configs:
  `configs/generated/dpo_strict3mlip_1024_before_after/before_64x20_seed20260513_shards/`
- after shard configs:
  `configs/generated/dpo_strict3mlip_1024_before_after/after_64x20_seed20260513_shards/`
- submission provenance:
  `outputs/dpo_strict3mlip_1024_before_after/generation_64x20_seed20260513_submission_20260513/submission_manifest.json`
- submission runbook:
  `outputs/dpo_strict3mlip_1024_before_after/generation_64x20_seed20260513_submission_20260513/README.md`

Validation before submission:

- Local lightweight validate-only checks passed for all four shard configs.
- Each shard has 32 formulas x 20 samples, for 640 requested candidates per
  shard and 1280 requested candidates per side.

Initial bad submissions:

- jobs `101184` and `101185` were cancelled before running because the first
  automatic pinned choice used the known-unusable `gpu4090` partition for this
  workflow. SLURM reported `PartitionConfig` / unusable node-style pending
  reasons, consistent with the earlier `gpu4090` caveat.

Active submitted jobs:

- `101205`, `fiir-dpo64-b1-full`: before shard 001
- `101206`, `fiir-dpo64-b2-full`: before shard 002
- `101208`, `fiir-dpo64-a1-full`: after shard 001
- `101210`, `fiir-dpo64-a2-full`: after shard 002

Scheduling policy:

- Submitted through `scripts/slurm/submit_crystalformer_bulk_gpu.sh`.
- Requested `FIIR_GPU_QUEUE_MODE=auto` with explicit homogeneous long-running
  CUDA allowlist `h200,h20,h20llm`, excluding `gpu4090` because it was observed
  unusable for this workflow, excluding `gpu4090_8` and `gpu4090_128` because
  they do not match the H20/H200 8 GPU + 192 CPU full-node shape, excluding
  `test` because the time limit is above 30 minutes, and excluding `h800`
  because the current node is down.
- Effective mode was flexible queueing because no eligible long-running GPU
  node had enough free resources at submission time.
- The intermediate jobs `101187`, `101188`, `101190`, and `101191` were
  cancelled before running because they requested only `gpu:1`.
- The intermediate jobs `101197`, `101198`, `101200`, and `101201` were
  cancelled before running because they requested 8 GPUs but only 32 CPUs.
- Each active job requests `gpu:8`, 192 CPUs, `02:00:00`, account `hmt03`, and
  the `crystalformer` conda environment with JAX GPU preflight enabled. The
  bulk runner will see `FIIR_TOTAL_GPUS=8` and `FIIR_TOTAL_CPU_CORES=192`, so it
  can use eight concurrent GPU workers with the full H20/H200 CPU budget.

Queue snapshot after submission:

- `101205`: `PENDING` at submission snapshot
- `101206`: `PENDING` at submission snapshot
- `101208`: `PENDING` at submission snapshot
- `101210`: `PENDING` at submission snapshot
- No SLURM stdout/stderr files existed yet at the inspected snapshot because
  the jobs had not started.

Next step:

- After jobs complete, inspect the four `bulk_summary.json` files, verify
  matched before/after coverage and candidate counts, then prepare matched
  MACE+CHGNet+MatGL relaxation offline validation batches.

Caveat:

- This run log records submission only. No new generation result or MLIP
  validation evidence exists until the jobs complete. Downstream labels remain
  MLIP relaxation proxy evidence, not DFT evidence and not self-consistent
  hull-confirmed stability.

## 2026-05-13: Resubmit 64x20 Generation Jobs With Whole-Node GPU Requests

Intent:

- Correct the 64x20 generation submission so each larger GPU job requests the
  full GPU count of the target node class rather than a single GPU.

Actions:

- Cancelled intermediate jobs `101187`, `101188`, `101190`, and `101191`
  before they ran because they requested only `gpu:1`.
- Cancelled intermediate jobs `101197`, `101198`, `101200`, and `101201`
  before they ran because they requested 8 GPUs but only 32 CPUs, leaving the
  CPU side of H20/H200 nodes under-requested.
- Resubmitted the four matched before/after generation shards through
  `scripts/slurm/submit_crystalformer_bulk_gpu.sh` with
  `FIIR_GPU_MIN_GPUS=8` and `FIIR_GPU_MIN_CPUS=192`.
- Active jobs:
  - `101205`, `fiir-dpo64-b1-full`: before shard 001
  - `101206`, `fiir-dpo64-b2-full`: before shard 002
  - `101208`, `fiir-dpo64-a1-full`: after shard 001
  - `101210`, `fiir-dpo64-a2-full`: after shard 002

Resource request:

- Each active job requests `gpu:8`, 192 CPUs, `02:00:00`, account `hmt03`, and
  JAX GPU preflight in the `crystalformer` environment.
- The generated plan exports `FIIR_TOTAL_GPUS=8` and
  `FIIR_TOTAL_CPU_CORES=192`, so the bulk runner can use eight concurrent GPU
  workers with the full H20/H200 CPU budget.
- Because no eligible long-running GPU node had enough free resources at
  submission time, the effective mode remains flexible queueing across
  `h200,h20,h20llm`.

Policy update:

- `AGENTS.md`, `docs/status/current_project_state.md`, and
  `scripts/slurm/README.md` now record that larger CrystalFormer generation,
  MLIP validation, DPO smoke/evaluation, and similar GPU compute jobs should
  request and use the full compute-resource shape of the target homogeneous
  partition set. On the current H20/H200 long-running CUDA GPU partitions this
  means `FIIR_GPU_MIN_GPUS=8` and `FIIR_GPU_MIN_CPUS=192`.

Caveat:

- This correction changes scheduling/resource requests only. It does not create
  new generation results yet, and downstream labels remain MLIP relaxation
  proxy evidence, not DFT evidence and not self-consistent hull-confirmed
  stability.

## 2026-05-13: Strengthen SLURM Full-Resource Submission Rule

Intent:

- Make full resource utilization a strict rule for every SLURM submission,
  including smoke and debug jobs.

Policy update:

- Every SLURM job must request and actually use the full compute-resource shape
  of its target node or homogeneous partition set.
- The rule applies to smoke, debug, validation, generation, training, and
  evaluation jobs alike.
- If a workflow cannot use a full node shape, do not submit it to SLURM in that
  form. Reshape the task, choose a matching partition, or keep it local only if
  it is lightweight and allowed by the login-node policy.
- `AGENTS.md`, `docs/status/current_project_state.md`, and
  `scripts/slurm/README.md` were updated to remove the earlier smoke/debug
  exception language.

Validation:

- `pytest -q` passed for the full lightweight suite.
- `git diff --check` passed.

Caveat:

- This is an execution-policy update. It does not change the scientific
  evidence state: strict three-MLIP labels remain MLIP relaxation proxy
  evidence, not DFT evidence and not self-consistent hull-confirmed stability.

## 2026-05-13: Clarify GPU Queue Resource Shape And Resubmit 64x20 Jobs

Intent:

- Update the SLURM resource-use rule to distinguish immediate pinned placement
  from no-free-node queueing.
- Replace the pending 64x20 generation jobs that were queued with a 192-CPU
  H20/H200-only shape by broader 8 GPU + 32 CPU flexible queue submissions.

Policy update:

- If a GPU job can start on a specific currently free eligible node, the pinned
  plan must request and use all currently free GPUs and CPU cores on that node.
- If no eligible GPU node can start the job now, auto fallback uses flexible
  queueing without `--nodelist` and requests the standard queued shape:
  `FIIR_GPU_QUEUE_MIN_GPUS=8` and `FIIR_GPU_QUEUE_MIN_CPUS=32`.
- This keeps jobs eligible for more future 8-GPU CUDA nodes while still
  requesting actual GPUs. `test` remains limited to explicit time limits of 30
  minutes or less.

Implementation:

- Added queue fallback request controls to the GPU planner:
  `queue_min_gpus` / `queue_min_cpus`, CLI flags `--queue-min-gpus` /
  `--queue-min-cpus`, and wrapper environment variables
  `FIIR_GPU_QUEUE_MIN_GPUS` / `FIIR_GPU_QUEUE_MIN_CPUS`.
- Updated `scripts/slurm/submit_crystalformer_bulk_gpu.sh`,
  `scripts/slurm/plan_slurm_job.py`, `scripts/slurm/plan_gpu_job.py`,
  `fiir_crystal/slurm_gpu_policy.py`, `fiir_crystal/slurm_scheduling.py`,
  `AGENTS.md`, `docs/status/current_project_state.md`, and
  `scripts/slurm/README.md`.
- Added regression coverage showing auto fallback can use a 32-CPU queued
  shape even when pinned placement was configured with a larger CPU threshold.

SLURM actions:

- Confirmed old jobs `101205`, `101206`, `101208`, and `101210` were still
  pending, then cancelled them before they ran.
- Resubmitted the four matched 64x20 before/after generation shards through
  `scripts/slurm/submit_crystalformer_bulk_gpu.sh`.
- Active replacement jobs:
  - `101217`, `fiir-dpo64-b1-q32`: before shard 001
  - `101220`, `fiir-dpo64-b2-q32`: before shard 002
  - `101218`, `fiir-dpo64-a1-q32`: after shard 001
  - `101219`, `fiir-dpo64-a2-q32`: after shard 002
- Candidate partition set:
  `h200,h20,h20llm,gpu4090_8,gpu4090_128`.
- Request per active job:
  `--gres gpu:8`, `--cpus-per-task 32`, `--time 02:00:00`, account `hmt03`,
  conda environment `crystalformer`, JAX GPU preflight required.
- `scontrol show job` confirmed `ReqTRES=cpu=32,...,gres/gpu=8` and
  `TresPerTask=cpu=32` for the active jobs. Queue snapshot after resubmission:
  `101217` pending for Resources; `101218`, `101219`, and `101220` pending for
  Priority.

Updated artifacts:

- submission manifest:
  `outputs/dpo_strict3mlip_1024_before_after/generation_64x20_seed20260513_submission_20260513/submission_manifest.json`
- submission runbook:
  `outputs/dpo_strict3mlip_1024_before_after/generation_64x20_seed20260513_submission_20260513/README.md`
- new q32 plan JSON files under `outputs/slurm_gpu_plans/`

Validation:

- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed.
- Full lightweight `pytest -q` passed.
- `git diff --check` passed after the code and documentation updates.
- `python -m json.tool` validated the updated submission manifest.

Caveat:

- This is a scheduling and provenance update only. The active jobs are still
  pending; no new CrystalFormer generation results or MLIP validation evidence
  exists yet. Strict three-MLIP labels remain MLIP relaxation proxy evidence,
  not DFT evidence and not self-consistent hull-confirmed stability.

## 2026-05-13: Set No-Free-Node GPU Queue Memory To 256G

Intent:

- Apply the final clarified memory rule: if a specific GPU node is free now,
  the pinned plan requests all currently free GPUs, CPU cores, and available
  memory on that node, capped at `RealMemory`; if no eligible GPU node can
  start now, flexible queueing uses 8 GPUs, 32 CPUs, and `256000M` memory.

Implementation:

- Changed `DEFAULT_FLEXIBLE_QUEUE_MEMORY_MB` to `256000`.
- Changed the GPU submit wrapper default `FIIR_GPU_QUEUE_MEMORY_MB` to
  `256000`.
- Updated SLURM docs, AGENTS rules, status docs, and scheduler tests to record
  the 256G no-free-node fallback.

SLURM actions:

- Jobs `101274`, `101275`, `101276`, and `101277` were still pending with the
  prior 512G-class memory request and were cancelled before running.
- Resubmitted the four matched 64x20 before/after generation shards through
  `scripts/slurm/submit_crystalformer_bulk_gpu.sh`.
- Active replacement jobs:
  - `101278`, `fiir-dpo64-b1-m256`: before shard 001
  - `101279`, `fiir-dpo64-b2-m256`: before shard 002
  - `101280`, `fiir-dpo64-a1-m256`: after shard 001
  - `101281`, `fiir-dpo64-a2-m256`: after shard 002
- Candidate partition set:
  `h200,h20,h20llm,gpu4090_8,gpu4090_128`.
- Request per active job:
  `--gres gpu:8`, `--cpus-per-task 32`, `--mem 256000M`,
  `--time 02:00:00`, account `hmt03`, conda environment `crystalformer`, JAX
  GPU preflight required.
- `scontrol show job 101278` confirmed
  `ReqTRES=cpu=32,mem=250G,node=1,billing=32,gres/gpu=8` and
  `TresPerTask=cpu=32`. Queue snapshot after resubmission:
  `101278` pending for Resources; `101279`, `101280`, and `101281` pending for
  Priority.

Validation:

- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed with 28 tests.

Caveat:

- This is a scheduling and provenance update only. The active jobs are still
  pending; no new CrystalFormer generation results or MLIP validation evidence
  exists yet. Strict three-MLIP labels remain MLIP relaxation proxy evidence,
  not DFT evidence and not self-consistent hull-confirmed stability.

## 2026-05-13: Refine GPU Queue Memory Request

Intent:

- Avoid SLURM expanding broad flexible GPU queue submissions to a 2TB memory
  request when `--mem` is omitted.
- Keep the user's preferred split:
  pinned jobs use the selected node's currently available memory, while
  no-free-node flexible queue jobs request the smallest total memory size among
  the currently eligible queueable GPU nodes.

Implementation:

- Pinned GPU plans now add `--mem` using the selected node's free memory capped
  at `RealMemory`, because `FreeMem` can be reported slightly above
  `RealMemory` on some nodes.
- Flexible GPU queue plans now treat `FIIR_GPU_QUEUE_MEMORY_MB=0` as auto:
  resolve to the minimum `total_memory_mb` across eligible queueable nodes in
  the candidate partition set.
- For the current `h200,h20,h20llm,gpu4090_8,gpu4090_128` queue set, auto
  resolves to `500000M`, the `gpu4090_8` node memory. `test` is excluded by the
  2-hour time limit, and the known-unusable `gpu4090` partition is not in the
  allowlist.

SLURM actions:

- The 256GB-memory jobs `101253`, `101254`, `101255`, and `101256` were still
  pending and were cancelled before running.
- Resubmitted the four matched 64x20 before/after generation shards through
  `scripts/slurm/submit_crystalformer_bulk_gpu.sh`.
- Active replacement jobs:
  - `101268`, `fiir-dpo64-b1-auto`: before shard 001
  - `101270`, `fiir-dpo64-b2-auto`: before shard 002
  - `101269`, `fiir-dpo64-a1-auto`: after shard 001
  - `101271`, `fiir-dpo64-a2-auto`: after shard 002
- Candidate partition set:
  `h200,h20,h20llm,gpu4090_8,gpu4090_128`.
- Request per active job:
  `--gres gpu:8`, `--cpus-per-task 32`, `--mem 500000M`,
  `--time 02:00:00`, account `hmt03`, conda environment `crystalformer`, JAX
  GPU preflight required.
- `scontrol show job 101268` confirmed
  `ReqTRES=cpu=32,mem=500000M,node=1,billing=32,gres/gpu=8` and
  `TresPerTask=cpu=32`. Queue snapshot after resubmission:
  `101268` pending for Resources; `101269`, `101270`, and `101271` pending for
  Priority.

Validation:

- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed with 28 tests.
- `git diff --check` passed.

Caveat:

- This is a scheduling and provenance update only. The active jobs are still
  pending; no new CrystalFormer generation results or MLIP validation evidence
  exists yet. Strict three-MLIP labels remain MLIP relaxation proxy evidence,
  not DFT evidence and not self-consistent hull-confirmed stability.

## 2026-05-13: Current GPU Queue Memory Correction

- The later active SLURM state supersedes the auto-memory `500000M` submission
  above: jobs `101268`, `101269`, `101270`, and `101271` are no longer active.
- The interim 512G-class jobs `101274`, `101275`, `101276`, and `101277` were
  still pending and were cancelled before running.
- Active jobs are now `101278`, `101279`, `101280`, and `101281`, all submitted
  through `scripts/slurm/submit_crystalformer_bulk_gpu.sh` with
  `--gres gpu:8`, `--cpus-per-task 32`, `--mem 256000M`, and `--time 02:00:00`
  on `h200,h20,h20llm,gpu4090_8,gpu4090_128`.
- `scontrol show job 101278` confirmed
  `ReqTRES=cpu=32,mem=250G,node=1,billing=32,gres/gpu=8` and
  `TresPerTask=cpu=32`.
- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
  passed with 28 tests after the 256G default change.
- Full lightweight `pytest -q` passed.
- `git diff --check` passed.
- `python -m json.tool` validated the updated submission manifest.
- This remains scheduling provenance only; no new generated candidates or MLIP
  validation evidence exists yet. Strict three-MLIP labels remain MLIP
  relaxation proxy evidence, not DFT evidence and not self-consistent
  hull-confirmed stability.
