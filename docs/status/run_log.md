# Run Log

This file records durable, high-signal workflow results for future agents. Keep
entries concise and point to generated artifacts instead of duplicating large
outputs.

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
