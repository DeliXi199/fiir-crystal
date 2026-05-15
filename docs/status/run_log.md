# Run Log

This file records durable, high-signal workflow results for future agents. Keep
entries concise and point to generated artifacts instead of duplicating large
outputs.

## 2026-05-14: Execute Alex-20 F4 StructureMatcher Audit

- Added an external worker:
  `experiments/run_f4_structure_matcher_audit.py`.
  It lives outside the `fiir_crystal` core package, reads local task/reference
  artifacts, runs local pymatgen `StructureMatcher`, and writes `f4-audit-v1`
  JSONL rows.
- Smoke checks:
  - 8-row smoke wrote
    `outputs/f4_novelty_audit/reference_pool_v1/f4_results_smoke.jsonl`.
  - 40-row smoke wrote
    `outputs/f4_novelty_audit/reference_pool_v1/f4_results_smoke40.jsonl`,
    covered the same-formula reference path, and imported with 40 matched rows,
    984 missing rows, and 0 orphans.
- Full command intent:
  run the external StructureMatcher worker over
  `outputs/f4_novelty_audit/reference_pool_v1/f4_audit_tasks.jsonl` using
  `outputs/f4_novelty_audit/reference_pool_v1/reference_pool_manifest.json`.
- Full outputs:
  - `outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl`
  - `outputs/f4_novelty_audit/reference_pool_v1/f4_structure_matcher_audit_summary.json`
  - `outputs/f4_novelty_audit/reference_pool_v1/f4_structure_matcher_audit_report.md`
- Full worker result:
  - 1024 task rows, 1024 result rows.
  - Exact-formula Alex-20 bucket policy.
  - 186 selected same-formula references from the 1,339,618-row Alex-20 pool.
  - 768 candidates had an exact-formula bucket but no StructureMatcher match.
  - 256 candidates had no exact-formula reference bucket.
  - 0 high-leakage StructureMatcher matches.
  - 0 reference parse failures and 0 candidate parse failures.
- Post-result readiness:
  `python scripts/check_f4_novelty_audit_ready.py --plan-json outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json --output-json outputs/f4_novelty_audit/reference_pool_v1/readiness_summary_with_results.json --require-results`
  reported ready true with 1024 result rows.
- Import:
  `python scripts/import_f4_novelty_audit.py --candidate-index outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl --f4-results-jsonl outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl --output-dir outputs/f4_novelty_import_1024_20260514 --fail-on-orphans --fail-on-missing`
  completed with 1024 candidates, 1024 F4 records, 1024 matched, 0 missing, 0
  orphans, and 0 high-leakage candidates.
- Import outputs:
  - `outputs/f4_novelty_import_1024_20260514/candidates_with_f4.jsonl`
  - `outputs/f4_novelty_import_1024_20260514/f4_import_summary.json`
  - `outputs/f4_novelty_import_1024_20260514/f4_import_report.md`
- Verification:
  - `python -m py_compile experiments/run_f4_structure_matcher_audit.py`
  - `pytest -q tests/test_f4_novelty_import.py tests/test_f4_novelty_audit_plan.py tests/test_f4_reference_pool_manifest.py`
- Caveat: this is Alex-20-only, exact-formula, binary StructureMatcher leakage
  evidence. It is not an all-known-materials novelty claim because Materials
  Project, GNoME, and ICSD are not staged in `reference_pool_v1`.

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
- Follow-up broad local scan under `/data/home/yihaoxu` searched for Alex,
  train/training, Materials Project/MP, ICSD, GNoME, reference CSV/JSONL, and
  common dataset cache files. It did not find a production-scale local
  reference snapshot. Production `reference_pool_v1` remains blocked until a
  real local reference source is staged.

## 2026-05-14: Download Alex-20 F4 Reference Snapshot

- Downloaded Hugging Face dataset `zdcao/alex-20` to the gitignored local
  directory `external/datasets/reference_pool_v1/raw/alex20_hf/` using:
  `hf download zdcao/alex-20 --repo-type dataset --local-dir external/datasets/reference_pool_v1/raw/alex20_hf --max-workers 4`
- Downloaded raw files:
  - `alex20/train.csv`: 3,242,832,648 bytes, 1,071,694 rows,
    sha256 `87a3de8bc8bbe245141e2c1727321c37c7fec001446d35b29c4521a3a8050641`
  - `alex20/val.csv`: 406,115,502 bytes, 133,962 rows,
    sha256 `026bc9a48e068ade16d6c68fee1e69111c66e96f441130a0782702ac2527273f`
  - `alex20/test.csv`: 405,090,084 bytes, 133,962 rows,
    sha256 `32390891666c66947cc41ef07fd75f3b3e5102e2f1ab6791f5ae43b05f032b39`
  - `convex_hull_pbe_2023.12.29.json.bz2`: 82,996,526 bytes.
- Updated `.gitignore` to exclude `external/datasets/`; these data files are
  intentionally local artifacts, not repository content.
- Extended `scripts/prepare_f4_reference_source.py` so large CSVs are streamed,
  Alex-20-style inline `structure` columns are accepted, and `--omit-raw-row`
  avoids duplicating huge structure text in metadata.
- Extended `scripts/build_f4_reference_pool_manifest.py` so manifest building
  streams JSONL instead of loading the complete reference pool into memory.
- Prepared Alex-20 reference JSONL sources under
  `outputs/f4_novelty_audit/reference_pool_v1/references/`:
  - `alex20_train_snapshot.structures.jsonl`: 1,071,694 rows,
    sha256 `a7cbb7308fab54dd910546355fd993ee0e91e99c593f88f85f4990ce81f10131`
  - `alex20_val_snapshot.structures.jsonl`: 133,962 rows,
    sha256 `7997dec0c896f1f0c5167ebf5544f52a0604fb679bb684bdea7f76c9ffe22026`
  - `alex20_test_snapshot.structures.jsonl`: 133,962 rows,
    sha256 `c39c7514fc25ed55709a070430d748f51c559419694ad52aec1a7efac6f2bc8d`
- Built `outputs/f4_novelty_audit/reference_pool_v1/reference_pool_manifest.json`
  with 3 sources, 1,339,618 total references, 0 duplicate reference ids, and 0
  missing reference ids.
- Re-ran readiness:
  `python scripts/check_f4_novelty_audit_ready.py --plan-json outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json --output-json outputs/f4_novelty_audit/reference_pool_v1/readiness_summary.json`
  and it reported `ready: true`.
- Local provenance for the ignored data is at
  `external/datasets/reference_pool_v1/provenance/alex20_hf_download.json`.
- Caveat: `reference_pool_v1` now covers Alex-20, including train/val/test
  splits. Materials Project, GNoME, and ICSD are still not staged, so this is a
  strong training/known-Alex-20 leakage audit base, not yet an exhaustive
  all-known-materials reference library.

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

## 2026-05-14: Complete 64x20 Generation And Fix Matched QA Namespace

Intent:

- Record that the four matched 64-formula x 20-sample before/after generation
  jobs completed cleanly.
- Fix local QA/collection so matched before/after roots can be scanned together
  without treating reused CrystalFormer candidate ids as cross-root duplicates.
- Prepare the project for matched MACE+CHGNet+MatGL relaxation validation.

Completed generation jobs:

| side | shard | job | node | completed | candidates | DPO eligible | generated pairs |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| before | 001 | 101278 | gpu40902 | 2026-05-14 02:32:59 CST | 640 | 640 | 392 |
| before | 002 | 101279 | gpuh2001 | 2026-05-14 04:13:48 CST | 640 | 640 | 424 |
| after | 001 | 101280 | gpuh2001 | 2026-05-14 04:03:52 CST | 640 | 640 | 337 |
| after | 002 | 101281 | gpuh2001 | 2026-05-14 04:08:51 CST | 640 | 640 | 466 |

Generation summary:

- all four logs contain `CrystalFormer bulk generation orchestration complete`.
- all four stderr files are empty.
- aggregate totals: 128/128 formulas completed, 2560 candidates, 2560
  DPO-eligible candidates, and 1619 generated geometry/chemistry preference
  pairs.
- before totals: 64 formulas, 1280 candidates, 1280 DPO eligible, 816 generated
  preference pairs, 40 F1 failures, 0 F2 failures, and 1280 F3-unknown
  candidates.
- after totals: 64 formulas, 1280 candidates, 1280 DPO eligible, 803 generated
  preference pairs, 37 F1 failures, 0 F2 failures, and 1280 F3-unknown
  candidates.

Implementation:

- Updated `fiir_crystal/artifact_qa.py` so candidate lookup and duplicate
  checks are scoped by input root.
- Updated `fiir_crystal/collection.py` so candidate and preference-pair counts
  are root-scoped before formula-level aggregation.
- Added regression coverage in `tests/test_crystalformer_artifact_qa.py` and
  `tests/test_crystalformer_bulk_collection.py`.

Validation:

- `pytest -q tests/test_crystalformer_artifact_qa.py tests/test_crystalformer_bulk_collection.py`
  passed.
- Combined 64x20 QA now reports `ready: true`, `critical_count: 0`, with 136
  documented warnings from empty/zero-pair artifacts.
- Combined 64x20 collection now reports 64 formulas, 2560 candidates, 2560
  audit candidates, 2560 DPO eligible, and 1619 preference pairs.

Next gate:

- Build prefixed before/after MLIP validation batches from the four 64x20
  roots.
- Submit matched MACE+CHGNet+MatGL relaxation jobs through existing SLURM
  wrappers only; do not run MLIP validation on the login node.
- Build strict three-MLIP consensus artifacts and compare before/after only
  after all six normalized validator outputs exist.

Caveat:

- This is still generation evidence only. F3/stability is unknown for all
  64x20 candidates until matched MLIP relaxation consensus validation is run
  and imported. The downstream labels remain MLIP relaxation proxy evidence,
  not DFT evidence and not self-consistent hull-confirmed stability.

## 2026-05-14: Submit 64x20 Matched Three-MLIP Offline Validation

Intent:

- Prepare root-scoped before/after validation batches for the completed 64x20
  generation gate.
- Submit matched MACE, CHGNet, and MatGL relaxation validation jobs through the
  project SLURM wrappers only.
- Keep all downstream claims blocked until normalized validator outputs and
  strict three-MLIP consensus artifacts exist.

Prepared batches:

- before:
  `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_64x20_20260514_batch/before/`
  with 1240 selected candidates across 64 formulas, prefix `before64__`, and
  40 F1/F2-gated candidates skipped.
- after:
  `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_64x20_20260514_batch/after/`
  with 1243 selected candidates across 64 formulas, prefix `after64__`, and
  37 F1/F2-gated candidates skipped.
- persistent combined QA:
  `outputs/dpo_strict3mlip_1024_before_after/qa_64x20_seed20260513/`
- persistent combined collection:
  `outputs/dpo_strict3mlip_1024_before_after/collection_64x20_seed20260513/`

Submission artifacts:

- runbook:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/README.md`
- prepared manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/run_manifest_prepared.json`
- submitted manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/run_manifest_submitted.json`
- submission script:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/submit_validation_jobs.sh`

Submitted jobs:

| validator | side | job | startup state | node | output directory |
| --- | --- | ---: | --- | --- | --- |
| MACE | before | 101697 | RUNNING | gpuh2001 | `outputs/mlip_validation_mace_relax_dpo_strict3mlip_1024_64x20_before_20260514` |
| MACE | after | 101698 | PENDING |  | `outputs/mlip_validation_mace_relax_dpo_strict3mlip_1024_64x20_after_20260514` |
| CHGNet | before | 101699 | PENDING |  | `outputs/mlip_validation_chgnet_relax_dpo_strict3mlip_1024_64x20_before_20260514` |
| CHGNet | after | 101700 | PENDING |  | `outputs/mlip_validation_chgnet_relax_dpo_strict3mlip_1024_64x20_after_20260514` |
| MatGL | before | 101701 | PENDING |  | `outputs/mlip_validation_matgl_relax_dpo_strict3mlip_1024_64x20_before_20260514` |
| MatGL | after | 101702 | RUNNING | gpuh2002 | `outputs/mlip_validation_matgl_relax_dpo_strict3mlip_1024_64x20_after_20260514` |

Scheduler shape:

- candidate partitions: `h200,h20,h20llm,gpu4090_8,gpu4090_128`
- time limit: `02:00:00`
- each submitted job requested `gpu:8`; the pinned plans selected H200 nodes
  where available.
- MACE jobs used precision profile `fp64`; CHGNet and MatGL jobs used `tf32`.
- MatGL used the local model path under
  `outputs/mlip_models/matgl/M3GNet-PES-MatPES-PBE-2025.2/`.

Startup check:

- `scripts/slurm/monitor_slurm_startup.sh --job-id 101697 --seconds 300`
  saw job `101697` running on `gpuh2001` with CUDA devices `0,1,2,3,4,5,6,7`.
- The monitor exited nonzero because stderr was non-empty. The stderr content
  was MACE/e3nn `torch.load` UserWarning messages, not a traceback.
- Job `101702` was also running on `gpuh2002`; checked MatGL stderr contained
  MatGL/PyTorch warnings only. A grep over checked MACE/MatGL log tails found
  no `Traceback`, `Exception`, `Error`, `not gpu`, or CPU-only marker.

Next gate:

- Refresh SLURM status until all six jobs complete.
- Run readiness checks for 1240 before rows and 1243 after rows.
- Build before/after strict three-MLIP consensus artifacts.
- Run the matched 64x20 before/after comparison.

Caveat:

- This is submission/startup evidence only. F3/stability remains unknown until
  all six validators complete and consensus is imported. Labels remain MLIP
  relaxation proxy evidence, not DFT evidence and not self-consistent
  hull-confirmed stability.

## 2026-05-14: Add Batch-Aware GPU Reserved-Node Planning

Intent:

- Prevent multiple jobs submitted in the same batch from repeatedly pinning to
  the same node snapshot before SLURM has reflected the earlier submissions.
- Preserve immediate pinned placement for the first jobs that can truly start
  now, then let excess jobs fall back to flexible multi-partition queueing.

Changes:

- Added `reserved_nodes` to `GpuSchedulingConfig` and the GPU plan JSON.
- Added `--reserved-node` to both GPU planner CLIs:
  `scripts/slurm/plan_slurm_job.py --kind gpu` and
  `scripts/slurm/plan_gpu_job.py`.
- Updated `scripts/slurm/submit_crystalformer_bulk_gpu.sh` with optional
  `FIIR_GPU_RESERVED_NODES` and `FIIR_GPU_RESERVED_NODES_FILE` inputs.
  When the file is set, the wrapper reads previously selected pinned nodes
  before planning and appends the newly selected pinned node after successful
  submission.
- Updated the 64x20 MLIP submission script to create and pass a per-batch
  reserved-node file for future reruns:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/submit_validation_jobs.sh`.
- Documented the behavior in `scripts/slurm/README.md` and
  `docs/status/current_project_state.md`.

Verification:

- `bash -n scripts/slurm/submit_crystalformer_bulk_gpu.sh`
- `bash -n outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/submit_validation_jobs.sh`
- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py tests/test_slurm_scheduling.py`
- `pytest -q`

## 2026-05-14: Complete 64x20 Three-MLIP Offline Validation Comparison

Intent:

- Finish the 64 formulas x 20 samples matched before/after offline-validation
  gate after all six MLIP relaxation jobs completed.
- Build strict MACE+CHGNet+MatGL consensus artifacts and compare before/after
  using imported F3 proxy evidence, not generation-only outputs.

SLURM completion:

| validator | side | job | state | elapsed | node |
| --- | --- | ---: | --- | ---: | --- |
| MACE | before | 101697 | `COMPLETED`, exit `0:0` | `00:06:46` | `gpuh2001` |
| MACE | after | 101698 | `COMPLETED`, exit `0:0` | `00:05:57` | `gpuh2001` |
| CHGNet | before | 101699 | `COMPLETED`, exit `0:0` | `00:06:30` | `gpuh2001` |
| CHGNet | after | 101700 | `COMPLETED`, exit `0:0` | `00:05:28` | `gpuh2001` |
| MatGL | before | 101701 | `COMPLETED`, exit `0:0` | `00:06:14` | `gpuh2001` |
| MatGL | after | 101702 | `COMPLETED`, exit `0:0` | `00:07:37` | `gpuh2002` |

Readiness:

- before readiness:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/readiness_before_summary.json`
  with MACE/CHGNet/MatGL each at 1240 rows.
- after readiness:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/readiness_after_summary.json`
  with MACE/CHGNet/MatGL each at 1243 rows.
- readiness result: true for both sides.

Consensus outputs:

- before consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_64x20_before_20260514/`
- after consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_64x20_after_20260514/`
- before consensus summary: overlap 1240, F3 available 807, stable consensus
  456, unstable consensus 351, disagreement 433, all-three agreement rate
  0.650806.
- after consensus summary: overlap 1243, F3 available 805, stable consensus
  456, unstable consensus 349, disagreement 438, all-three agreement rate
  0.647627.

Final comparison:

- generation sanity summary:
  `outputs/dpo_strict3mlip_1024_before_after/comparison_64x20_seed20260513/summary.json`
- comparison summary:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_comparison_64x20_seed20260513/summary.json`
- comparison report:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_comparison_64x20_seed20260513/report.md`
- final manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/run_manifest_final.json`

Matched before/after metrics:

| metric | before | after | delta |
| --- | ---: | ---: | ---: |
| candidates | 1280 | 1280 | 0 |
| DPO eligible | 1280 | 1280 | 0 |
| F1 fail rate | 0.03125 | 0.02890625 | -0.00234375 |
| F2 fail rate | 0.0 | 0.0 | 0.0 |
| F3 available | 807 | 805 | -2 |
| strict stable consensus | 456 | 456 | 0 |
| unstable consensus | 351 | 349 | -2 |
| disagreement | 433 | 438 | +5 |
| all-three agreement rate | 0.650806 | 0.647627 | -0.00318 |
| stable consensus rate | 0.35625 | 0.35625 | 0.0 |
| preference-pair yield | 816 | 803 | -13 |
| unique sequence fraction | 0.96875 | 0.971094 | +0.00234 |
| spacegroup count | 75 | 75 | 0 |
| spacegroup entropy | 3.91662 | 3.91351 | -0.00312 |

Interpretation:

- The 64x20 matched proxy audit does not show a strict three-MLIP stable-rate
  improvement for the DPO after checkpoint.
- The proxy-divergence screen is flagged because stable consensus rate did not
  improve; this is a conservative stop signal against making a DPO-improvement
  claim from this checkpoint.
- The labels remain MACE+CHGNet+MatGL relaxation consensus proxy evidence, not
  DFT evidence and not self-consistent hull-confirmed stability.

Verification:

- `pytest -q tests/test_compare_dpo_before_after_mlip_consensus.py`
- `python -m py_compile scripts/compare_dpo_before_after_mlip_consensus.py scripts/build_mlip_ensemble_consensus.py scripts/check_dpo_offline_validation_ready.py`
- `pytest -q`

## 2026-05-14: Diagnose 64x20 DPO After Checkpoint Non-Improvement

Intent:

- Explain why the 64x20 after checkpoint did not improve strict three-MLIP
  stable consensus rate.
- Split the global before/after result by formula across preference-pair yield,
  F1/F2 filtering, F3 consensus availability, stable/unstable consensus, and
  validator disagreement.

Outputs:

- diagnosis summary:
  `outputs/dpo_strict3mlip_1024_before_after/diagnostics_64x20_seed20260513/summary.json`
- formula deltas:
  `outputs/dpo_strict3mlip_1024_before_after/diagnostics_64x20_seed20260513/formula_deltas.jsonl`
- report:
  `outputs/dpo_strict3mlip_1024_before_after/diagnostics_64x20_seed20260513/report.md`

Global delta:

| signal | delta |
| --- | ---: |
| stable consensus count | 0 |
| F3 available count | -2 |
| disagreement count | +5 |
| preference-pair count | -13 |
| F1 fail count | -3 |

Main contributors:

- largest stable-consensus losses: CaThO3 -3, PbZrO3 -3, SrCeO3 -3,
  BaSnO3 -2, CaCeO3 -2, CaTiO3 -2, DyScO3 -2, GdInO3 -2.
- largest stable-consensus gains: BaHfO3 +4, HoScO3 +3, SmGaO3 +3,
  BaZrO3 +2, CaZrO3 +2, DyInO3 +2, PrInO3 +2, SmScO3 +2.
- largest F3-available losses: LaScO3 -4, CaThO3 -3, PbThO3 -3,
  SrCeO3 -3, CaCeO3 -2, CaTiO3 -2, DyScO3 -2, GdAlO3 -2.
- largest disagreement increases: LaScO3 +4, CaThO3 +3, CaTiO3 +3,
  SrCeO3 +3, CaCeO3 +2, CaSiO3 +2, DyAlO3 +2, DyScO3 +2.
- largest preference-pair losses: BaSnO3 -19, BaThO3 -19, BaZrO3 -19,
  PbGeO3 -19, PrGaO3 -19, SrThO3 -19, CaTiO3 -18, CaZrO3 -18.

Interpretation:

- The flat global stable count is not a uniform null result; formula-level
  stable gains are offset by formula-level losses.
- The after checkpoint slightly reduced F3-available consensus rows and raised
  validator disagreement, so the proxy screen remains conservative.
- The unchanged next-step recommendation is to avoid claiming improvement for
  this DPO checkpoint. Before retraining, build a revised DPO preference
  artifact emphasizing high-agreement stable-vs-unstable MLIP consensus pairs
  and reducing zero/low-margin geometry-only pair sources.

Verification:

- `python -m json.tool outputs/dpo_strict3mlip_1024_before_after/diagnostics_64x20_seed20260513/summary.json`
- `wc -l outputs/dpo_strict3mlip_1024_before_after/diagnostics_64x20_seed20260513/formula_deltas.jsonl` reported 64 rows.

## 2026-05-14: Build F3-Isolated DPO Preference Artifact

Intent:

- Remove aggregate-FIIR-score confounding from the next DPO data artifact.
- Emit only same-formula stable-vs-unstable pairs where both sides pass F1/F2
  and the three MLIP validators all agree on the F3 proxy label.
- Use the after-checkpoint 64x20 candidate distribution as the follow-up
  training source; do not pair before and after candidates together.

Implementation:

- Added `scripts/build_f3_isolated_dpo_preferences.py`.
- Added `tests/test_build_f3_isolated_dpo_preferences.py`.
- The script joins prefixed consensus candidate ids such as
  `after64__crystalformer_output_...` back to raw audit candidates, strips only
  for lookup, and writes prefixed ids into the DPO artifact to preserve
  provenance and avoid collisions.
- Each pair has:
  - `preference_type: stability_aware_offline_validation`
  - `preference_reason: [f3_consensus_only, three_mlip_all_agree, f1_f2_controlled]`
  - `chosen_score: 0.0`, `rejected_score: 1.0`
  - chosen `f3_stability: 0.0`, rejected `f3_stability: 1.0`
  - metadata flag `f3_only_preference: true`

Outputs:

- F3-only preference artifact:
  `outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/dpo_preferences/preference_pairs.jsonl`
- preference summary:
  `outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/dpo_preferences/preference_summary.json`
- matched F3 candidate index:
  `outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/matched_f3_candidates.jsonl`
- training-boundary manifest:
  `outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/training_boundary/trainer_manifest.json`

Counts:

| signal | count |
| --- | ---: |
| consensus input rows | 1243 |
| retained F3 candidates after F1/F2 control | 801 |
| retained stable candidates | 456 |
| retained unstable candidates | 345 |
| skipped non-agreement or missing F3 | 438 |
| skipped F1/F2 not passing | 4 |
| emitted preference pairs | 2156 |
| valid training pairs | 2156 |
| invalid training pairs | 0 |

Training boundary:

- ready for external training: true.
- blocking reasons: none.
- warning: CrystalFormer is a normal clone; fork/submodule is recommended for
  future training work.
- FIIR still does not train DPO internally; this is an external CrystalFormer
  handoff artifact only.

Verification:

- `pytest -q tests/test_build_f3_isolated_dpo_preferences.py tests/test_crystalformer_dpo_training_boundary.py`
- `pytest -q`

## 2026-05-14: Run F3-Isolated DPO Follow-Up And 64x20 Proxy Audit

Intent:

- Execute the next step after building the F3-isolated DPO preference artifact.
- Train one external CrystalFormer DPO epoch from the previous DPO-after
  checkpoint using only F3-isolated stable-vs-unstable pairs with F1/F2
  controlled.
- Generate a matched 64 formulas x 20 samples follow-up from the new checkpoint
  and compare it to the previous DPO-after checkpoint under the same
  MACE+CHGNet+MatGL relaxation consensus proxy gate.

Training:

- prepared package:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_smoke_prepare/`
- input pairs: 2156
- start epoch: 46001
- target epoch: 46002
- SLURM job: `101758`, `fiir-f3only-dpo`, `COMPLETED`, exit `0:0`,
  elapsed `00:04:09`, node `gpuh2001`, requested `gpu:8`
- GPU evidence: `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`, JAX backend `gpu`,
  8 CUDA devices visible.
- produced checkpoint:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046002.pkl`
- checkpoint sha256:
  `7860e7c79f1fca24d2ac3f57281d91fd6c000c1cf726d20a9a9000b6281367bd`
- training row: epoch 46002 loss / dpo_loss `405.355835 / 405.355835`,
  validation loss / validation dpo_loss `474.216217 / 474.216217`.

Follow-up generation:

- configs:
  `configs/generated/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/after_64x20_seed20260513_shards/`
- output roots:
  - `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/after_64x20_seed20260513_shard_001`
  - `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/after_64x20_seed20260513_shard_002`
- generation jobs:
  - `101762`, `fiir-f3after-s2`, `COMPLETED`, exit `0:0`, elapsed
    `00:05:06`, node `gpuh2002`
  - `101763`, `fiir-f3after-s1flex`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:57`, node `gpuh2002`
- scheduling behavior: an initial stale pinned job was cancelled; the rerun used
  the batch reserved-node strategy. Runnable jobs pinned to free nodes first,
  while the excess job used flexible queueing and started when `gpuh2002`
  became free.
- collection summary:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/collection_after_64x20_seed20260513/collection_summary.json`
- generation counts: 64/64 formulas completed, 1280 candidates, 1280
  DPO-eligible candidates, 708 generated geometry/chemistry preference pairs.
- strict QA note: generation-stage empty/zero-pair artifacts still trigger
  warnings for formulas with no comparable margins; this is not a blocker for
  MLIP validation because candidates and audits were complete.

MLIP validation:

- batch:
  `outputs/mlip_validation_f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_batch/after/`
- selected candidates: 1245
- selected formulas: 64
- skipped candidates: 35, all `f1_not_pass`
- validation jobs:
  - `101767`, `fiir-mace-f3after64`, `COMPLETED`, exit `0:0`, elapsed
    `00:05:13`, node `gpuh2001`, normalized rows 1245
  - `101768`, `fiir-chgnet-f3after64`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:40`, node `gpuh2002`, normalized rows 1245
  - `101769`, `fiir-matgl-f3after64`, `COMPLETED`, exit `0:0`, elapsed
    `00:06:27`, node `gpuh2002`, normalized rows 1245
- validation placement: MACE pinned to free `gpuh2001`, CHGNet pinned to free
  `gpuh2002`, and MatGL submitted flexible while both nodes were occupied, then
  started on `gpuh2002` after CHGNet completed.
- GPU evidence: all three validation jobs requested `gpu:8` and logged
  `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`. A transient MatGL probe saw partial
  utilization while the job was between worker completions, but the job
  completed successfully with all 1245 rows normalized.
- readiness summary:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/offline_validation_after_64x20_seed20260513/readiness_after_summary.json`
- SLURM provenance:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/offline_validation_after_64x20_seed20260513/slurm_execution_provenance.json`
- fatal-log scan: no traceback, exception, OOM, killed, failed, or cancelled
  markers were found in the inspected validation SLURM logs; stderr warnings
  were library/model warnings.

Consensus and comparison:

- new after consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_64x20_after_20260514/`
- comparison:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/offline_validation_comparison_after64_to_f3after64_seed20260513/`

Matched comparison versus the previous DPO-after checkpoint:

| metric | previous DPO after | F3-only follow-up | delta |
| --- | ---: | ---: | ---: |
| candidates | 1280 | 1280 | 0 |
| F1 fail rate | 0.0289063 | 0.0273438 | -0.0015625 |
| F2 fail rate | 0 | 0 | 0 |
| F3 available | 805 | 806 | +1 |
| strict stable consensus | 456 | 465 | +9 |
| unstable consensus | 349 | 341 | -8 |
| disagreement | 438 | 439 | +1 |
| all-three agreement rate | 0.647627 | 0.647390 | -0.000237 |
| stable consensus rate | 0.35625 | 0.363281 | +0.00703125 |
| preference-pair yield | 803 | 708 | -95 |
| unique sequence fraction | 0.971094 | 0.972656 | +0.0015625 |
| spacegroup count | 75 | 75 | 0 |

Interpretation:

- The F3-only follow-up is the first 64x20 proxy audit to show a positive
  strict stable-consensus delta over the previous DPO-after checkpoint (+9).
- The result is still conservative: all-three agreement decreased very slightly
  and disagreement increased by one, so the proxy-divergence screen remains
  flagged.
- Treat this as a small positive MLIP-proxy signal, not a DFT-backed
  performance claim. The next gate should be a fixed-candidate audit, larger
  matched audit, or carefully bounded additional epoch sweep before scaling the
  training strategy.

## 2026-05-14: Complete F3-Isolated 64x80 Matched Proxy Audit

Intent:

- Scale the F3-isolated follow-up checkpoint audit from 64x20 to 64x80.
- Compare the previous DPO-after checkpoint epoch 46001 against the F3-only
  follow-up checkpoint epoch 46002 under the same strict MACE+CHGNet+MatGL
  relaxation consensus proxy gate.

Generation and collection:

- output root:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/`
- generation jobs:
  - `101785`, `fiir-f3x80-b1`, `COMPLETED`, exit `0:0`
  - `101786`, `fiir-f3x80-b2`, `COMPLETED`, exit `0:0`
  - `101787`, `fiir-f3x80-a1`, `COMPLETED`, exit `0:0`
  - `101788`, `fiir-f3x80-a2`, `COMPLETED`, exit `0:0`
- counts: 5120 before candidates and 5120 after candidates, 64 formulas per
  side, 80 samples per formula, 5120 DPO-eligible candidates per side.
- collection summaries:
  - `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/collection_before_64x80_seed20260514/collection_summary.json`
  - `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/collection_after_64x80_seed20260514/collection_summary.json`
  - `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/collection_combined_64x80_seed20260514/collection_summary.json`
- generation summary for comparison:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/offline_validation_comparison_64x80_seed20260514/generation_summary.json`

MLIP validation:

- batch:
  `outputs/mlip_validation_f3_only_mace_chgnet_matgl_consensus_64x80_20260514_batch/`
- selected before candidates: 4999; skipped 121, all `f1_not_pass`.
- selected after candidates: 4980; skipped 140, all `f1_not_pass`.
- validation jobs:
  - `101802`, `fiir-mace-f3x80-b`, `COMPLETED`, exit `0:0`, elapsed
    `00:29:02`, node `gpuh2002`, normalized rows 4999
  - `101803`, `fiir-mace-f3x80-a`, `COMPLETED`, exit `0:0`, elapsed
    `00:18:06`, node `gpu40904`, normalized rows 4980
  - `101804`, `fiir-chgnet-f3x80-b`, `COMPLETED`, exit `0:0`, elapsed
    `00:31:48`, node `gpuh2002`, normalized rows 4999
  - `101805`, `fiir-chgnet-f3x80-a`, `COMPLETED`, exit `0:0`, elapsed
    `00:17:26`, node `gpu40904`, normalized rows 4980
  - `101806`, `fiir-matgl-f3x80-b`, `COMPLETED`, exit `0:0`, elapsed
    `00:20:10`, node `gpu40904`, normalized rows 4999
  - `101807`, `fiir-matgl-f3x80-a`, `COMPLETED`, exit `0:0`, elapsed
    `00:30:46`, node `gpuh2002`, normalized rows 4980
- readiness summaries:
  - `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/offline_validation_64x80_seed20260514/readiness_before_summary.json`
  - `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/offline_validation_64x80_seed20260514/readiness_after_summary.json`
- fatal-log scan over the six validation SLURM logs found no traceback,
  exception, OOM, killed, failed, cancelled, CUDA error, or runtime-error
  markers.

Consensus and comparison:

- before consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_64x80_before_20260514/`
- after consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_64x80_after_20260514/`
- comparison:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/offline_validation_comparison_64x80_seed20260514/`
- formula-level diagnosis:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/diagnostics_64x80_seed20260514/`
  with `summary.json`, `formula_deltas.jsonl`, and `report.md`.

Matched comparison versus the previous DPO-after checkpoint:

| metric | previous DPO after | F3-only follow-up | delta |
| --- | ---: | ---: | ---: |
| candidates | 5120 | 5120 | 0 |
| F1 fail rate | 0.0236328 | 0.0273438 | +0.00371094 |
| F2 fail rate | 0 | 0 | 0 |
| F3 available | 3208 | 3198 | -10 |
| strict stable consensus | 1800 | 1882 | +82 |
| unstable consensus | 1408 | 1316 | -92 |
| disagreement | 1791 | 1782 | -9 |
| all-three agreement rate | 0.641728 | 0.642169 | +0.000440 |
| stable consensus rate | 0.351562 | 0.367578 | +0.016016 |
| preference-pair yield | 10944 | 12651 | +1707 |
| unique sequence fraction | 0.976367 | 0.972656 | -0.003711 |
| spacegroup count | 86 | 86 | 0 |
| spacegroup entropy | 4.03697 | 4.01794 | -0.01904 |

Interpretation:

- The 64x80 matched proxy audit strengthens the F3-only DPO signal: strict
  stable consensus increased by 82, all-three agreement increased slightly, and
  disagreement decreased by 9.
- The proxy-divergence screen remains flagged because stable consensus rate
  improved while F1 fail rate increased and diversity signals dipped slightly.
- Formula-level diagnosis shows the largest stable-consensus gains from
  GdAlO3 +12, YGaO3 +9, PbZrO3 +8, LaGaO3 +8, and CaCeO3 +8; the largest
  losses are CaGeO3 -8, PbHfO3 -8, SrCeO3 -8, HoAlO3 -7, and DyScO3 -5.
  Largest F1-fail increases include PbTiO3 +5 and
  YAlO3/PrAlO3/NdScO3/DyScO3 +3 each.
- Treat this as positive MLIP-relaxation proxy evidence, not DFT or
  hull-confirmed stability. Next step: fixed-candidate audit using the
  formula-level gain/loss and F1-regression panel before another training-scale
  escalation.

## 2026-05-14: Run Fixed-Candidate Log-Probability Audit For F3-Isolated Checkpoint

Intent:

- Separate checkpoint likelihood changes from sampling variance after the
  positive 64x80 matched proxy audit.
- Score the same compact candidate panel under before checkpoint epoch 46001
  and after checkpoint epoch 46002.
- Use formulas from the 64x80 formula diagnosis, covering stable gains, stable
  losses, F1 regressions, and disagreement regressions.

Implementation:

- Added external CrystalFormer scorer:
  `experiments/run_crystalformer_fixed_candidate_logp_audit.py`.
- The scorer runs outside the FIIR core package, imports CrystalFormer/JAX only
  in `main`, uses checkpoint-local CrystalFormer parameters, and writes local
  JSONL/JSON/Markdown artifacts. It does not run generation, MLIP validation,
  DFT, training, downloads, or external APIs.
- Built fixed panel:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/`
  with `manifest.json`, `panel_sequences.jsonl`, `report.md`, and
  `run_fixed_candidate_logp_audit.sh`.
- Panel size: 861 candidates.
- Panel formulas:
  BaSiO3, CaCeO3, CaGeO3, DyAlO3, DyScO3, GdAlO3, HoAlO3, LaGaO3, NdScO3,
  PbCeO3, PbHfO3, PbTiO3, PbZrO3, PrAlO3, SrCeO3, SrZrO3, YAlO3, YGaO3.

SLURM execution:

- job: `102594`, `fiir-f3x80-logp-audit`
- partition/node: `test` / `test001`
- state: `COMPLETED`, exit `0:0`
- elapsed: `00:01:25`
- requested GPUs: `gpu:rtx4090:2`
- JAX preflight: `jax_default_backend=gpu`, devices
  `[CudaDevice(id=0), CudaDevice(id=1)]`
- logs:
  - `logs/slurm/fiir-f3x80-logp-audit_102594.log`
  - `logs/slurm/fiir-f3x80-logp-audit_102594.err`
- stderr contained XLA autotuning warnings only in the inspected tail.

Outputs:

- score directory:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/logp_scores/`
- score rows:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/logp_scores/logp_rows.jsonl`
  with 1722 rows.
- summary:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/logp_scores/summary.json`
- report:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/logp_scores/report.md`

After-minus-before log-probability deltas by consensus label:

| label | count | mean delta | median delta |
| --- | ---: | ---: | ---: |
| disagreement | 288 | -179172 | -22306.5 |
| stable | 288 | 151988 | 39.6328 |
| unstable | 285 | -420331 | -78235.5 |

After-minus-before log-probability deltas by panel reason:

| reason | count | mean delta | median delta |
| --- | ---: | ---: | ---: |
| disagreement_regression | 192 | -122100 | -63.058 |
| f1_regression | 192 | -155121 | -128.745 |
| stable_gain | 237 | -173510 | -1826.12 |
| stable_loss | 144 | -93715.5 | -19841.8 |
| stable_loss+disagreement_regression | 48 | -477315 | -104099 |
| stable_loss+f1_regression | 48 | 65232.3 | -39.4123 |

Interpretation:

- The fixed panel supports the same direction as the 64x80 matched proxy audit:
  checkpoint 46002 raises likelihood for stable consensus candidates relative
  to unstable candidates.
- The stable-minus-unstable delta gap is positive at `+572318.5687`.
- The signal is mostly relative suppression of unstable/disagreement candidates
  plus a small stable median increase, not a broad unconditional likelihood
  increase across every formula panel.
- This is a model-likelihood audit, not generation, MLIP validation, DFT, or
  hull-confirmed stability. The next GPU step should remain a bounded epoch
  sweep or targeted validation, with the fixed panel re-used as a cheap guard
  before any larger generation+MLIP campaign.

## 2026-05-14: Run Bounded Epoch 46003 Continuation And Fixed-Panel Guard

Intent:

- Take only one additional external CrystalFormer DPO epoch after checkpoint
  46002.
- Avoid a broad training-scale escalation; use the same F3-isolated 2156-pair
  preference artifact and immediately re-score the existing 861-candidate fixed
  panel.
- Decide whether another generation+MLIP validation gate is worth running.

Preparation:

- package:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_epoch46003_prepare/`
- preference pairs:
  `outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/dpo_preferences/preference_pairs.jsonl`
- base checkpoint:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1`
- prepared pairs: 2156
- checkpoint start epoch: 46002
- checkpoint target epoch: 46003
- run script:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_epoch46003_prepare/run_training.sh`

DPO continuation execution:

- job: `102595`, `fiir-f3only-ep46003`
- partition/node: `test` / `test001`
- state: `COMPLETED`, exit `0:0`
- elapsed: `00:02:47`
- requested GPUs: `gpu:rtx4090:2`
- JAX preflight: `jax_default_backend=gpu`, devices
  `[CudaDevice(id=0), CudaDevice(id=1)]`
- produced checkpoint:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_epoch46003_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046003.pkl`
- checkpoint sha256:
  `f6d26488bd95602f1ab72369aa1dc0e1e14bb5a08ba7feb2c28adc570b19f065`
- data row:
  - epoch: 46003
  - loss / dpo_loss: `447.105591 / 447.105591`
  - chosen / rejected logp: `-239462.250000 / -1685722.000000`
  - validation loss / validation dpo_loss: `222.710953 / 222.710953`
  - validation chosen / rejected logp: `-178254.906250 / -2148126.500000`
- fatal-log scan found no traceback, exception, OOM, killed, failed,
  cancelled, CUDA error, runtime-error, or `Error` markers. Stderr contained
  XLA autotuning warnings only.

Fixed-panel guard:

- added run script:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/run_fixed_candidate_logp_audit_epoch46003_vs_46002.sh`
- job: `102598`, `fiir-f3ep3-logp-audit`
- partition/node: `test` / `test001`
- state: `COMPLETED`, exit `0:0`
- elapsed: `00:00:38`
- requested GPUs: `gpu:rtx4090:2`
- output directory:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/logp_scores_epoch46003_vs_46002/`
- score rows: 1722, covering 861 candidates under checkpoints 46002 and 46003.

46003 minus 46002 log-probability deltas by consensus label:

| label | count | mean delta | median delta |
| --- | ---: | ---: | ---: |
| disagreement | 288 | -184637 | -24775.6 |
| stable | 288 | 109245 | 25.0478 |
| unstable | 285 | -451094 | -84341.2 |

46003 minus 46002 log-probability deltas by panel reason:

| reason | count | mean delta | median delta |
| --- | ---: | ---: | ---: |
| disagreement_regression | 192 | -134993 | -126.582 |
| f1_regression | 192 | -176590 | -136.837 |
| stable_gain | 237 | -262995 | -185.5 |
| stable_loss | 144 | -99307.5 | -20720.7 |
| stable_loss+disagreement_regression | 48 | -397617 | -86203.9 |
| stable_loss+f1_regression | 48 | 109680 | -46.3985 |

Additional fixed-panel aggregation:

- 46003-vs-46002 stable-minus-unstable mean delta gap: `+560338.35`.
- Cumulative 46003-vs-46001 median deltas from the two fixed-panel audits:
  stable `+93.17`, unstable `-173380.06`, disagreement `-66843.56`.
- Cumulative 46003-vs-46001 stable-minus-unstable mean delta gap:
  `+1132656.92`.

Interpretation:

- The second epoch did not reverse the fixed-candidate likelihood signal.
- It continues to prefer stable consensus candidates relative to unstable
  candidates, but most of the effect is still relative suppression of
  unstable/disagreement candidates rather than large broad stable uplift.
- Do not run another DPO epoch yet. The next evidence gate should be matched
  generation+MLIP validation for checkpoint 46003, starting at 64x20 or 64x40
  before deciding whether 46003 is better than checkpoint 46002 in generated
  outputs.

## 2026-05-14: Make GPU `test` Partition A Short-Job Fallback Only

Intent:

- Prevent the GPU planner from selecting `test` simply because it is idle.
- Keep `test` available only for small bounded GPU jobs when no normal GPU node
  can start immediately.
- Preserve explicit test-only usage for deliberate short test jobs.

Implementation:

- Updated `fiir_crystal/slurm_gpu_policy.py` so pinned GPU selection first ranks
  eligible non-`test` nodes only. `test` is considered only if that non-`test`
  pool is empty and the existing 30-minute time guard passes.
- Updated flexible GPU queue partition selection so `test` is excluded whenever
  any normal GPU partition is queueable. `test` remains available when it is
  the only allowed/queueable partition and the job is short enough.
- Updated planner/submitter summary text:
  - `scripts/slurm/plan_slurm_job.py`
  - `scripts/slurm/plan_gpu_job.py`
  - `scripts/slurm/submit_crystalformer_bulk_gpu.sh`
- Updated docs:
  - `scripts/slurm/README.md`
  - `docs/status/current_project_state.md`
- Added tests covering:
  - `test` loses to a normal GPU node even when `test` has a higher raw GPU
    score.
  - `test` is used for a short job when no non-`test` GPU node is free.
  - flexible GPU queueing excludes `test` when a normal GPU partition is
    queueable.

Policy summary:

- Normal GPU nodes always win when they can start the job now.
- `test` requires an explicit time limit of 30 minutes or less.
- `test` is only a fallback after no non-`test` GPU node has enough free
  GPUs/CPUs to start now.
- Explicit `FIIR_GPU_PARTITIONS=test` remains the opt-in path for deliberate
  short test-only jobs.

Verification:

- `python -m py_compile fiir_crystal/slurm_gpu_policy.py scripts/slurm/plan_slurm_job.py scripts/slurm/plan_gpu_job.py`
- `pytest -q tests/test_slurm_gpu_policy.py`
- `pytest -q tests/test_slurm_submission_template.py tests/test_slurm_gpu_policy.py`

## 2026-05-14: Switch GPU Submissions From Node-Pinned To Partition-Wide

Trigger:

- During the epoch 46003 matched 64x20 generation gate, job `102599`
  remained pending on `gpu40903` even after `gpu40904` was idle.
- Root cause: the old auto plan emitted `--nodelist gpu40903`, so SLURM could
  not move the pending job to another free node in `gpu4090_128`.
- Desired policy: GPU availability should be determined by free GPU count, not
  idle CPU or free-memory counts; submissions should fix the partition, not a
  single node.

Implementation:

- Updated `fiir_crystal/slurm_gpu_policy.py`:
  - `node_is_eligible` now uses free GPU count for start-now GPU eligibility
    and no longer rejects nodes because idle CPU or free memory is low.
  - Auto selected plans now submit partition-wide with `--partition` and
    `--gres`, intentionally omitting `--nodelist`.
  - CPU and memory are request-shape knobs (`FIIR_GPU_QUEUE_MIN_CPUS=32`,
    `FIIR_GPU_QUEUE_MEMORY_MB=256000` by default), not GPU availability
    filters.
  - The plan records the selected node as a reference node for partition/GRES
    choice, while `FIIR_GPU_NODE=slurm_assigned_at_runtime`.
- Updated:
  - `scripts/slurm/submit_crystalformer_bulk_gpu.sh`
  - `scripts/slurm/plan_slurm_job.py`
  - `scripts/slurm/plan_gpu_job.py`
  - `scripts/slurm/README.md`
  - `tests/test_slurm_gpu_policy.py`
  - `tests/test_slurm_submission_template.py`
  - `docs/status/current_project_state.md`

Dry-run evidence after the change:

- command context: 8-GPU, 32-CPU, 256G, `FIIR_TIME_LIMIT=02:00:00`
- reference node: `gpu40903`
- selected partition: `gpu4090_128`
- generated sbatch command:
  `sbatch --nodes 1 --partition gpu4090_128 --job-name fiir-policy-dryrun --gres gpu:rtx4090:8 --account hmt03 --time 02:00:00 --mem 256000M --ntasks 1 --cpus-per-task 32 ...`
- no `--nodelist`
- no `test` partition in the normal long-job path

Verification:

- `python -m py_compile fiir_crystal/slurm_gpu_policy.py scripts/slurm/plan_slurm_job.py scripts/slurm/plan_gpu_job.py`
- `pytest -q tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`
- `git diff --check fiir_crystal/slurm_gpu_policy.py scripts/slurm/plan_slurm_job.py scripts/slurm/plan_gpu_job.py scripts/slurm/submit_crystalformer_bulk_gpu.sh scripts/slurm/README.md tests/test_slurm_gpu_policy.py tests/test_slurm_submission_template.py`

## 2026-05-14: Complete Epoch 46003 Matched 64x20 Generation+MLIP Gate

Intent:

- Validate checkpoint epoch 46003 against checkpoint epoch 46002 in generated
  outputs before considering any additional training.
- Use the same 64 formulas, 20 samples/formula, seed `20260513`, `K=40`, and
  strict MACE+CHGNet+MatGL relaxation consensus proxy gate.

Generation:

- configs:
  `configs/generated/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x20/after_46003_64x20_seed20260513_shards/`
- output roots:
  - `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x20/after_46003_64x20_seed20260513_shard_001`
  - `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x20/after_46003_64x20_seed20260513_shard_002`
- original shard 001 job `102599` was cancelled while pending because it was
  node-pinned to `gpu40903`; shard 001 was resubmitted as `102604` to the free
  `gpu4090_128` capacity.
- completed generation jobs:
  - `102600`, `fiir-f3ep3-64x20-s2`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:15`, node `gpu40904`
  - `102604`, `fiir-f3ep3-64x20-s1r`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:03`, node `gpu40904`
- collection:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x20/collection_after_46003_64x20_seed20260513/collection_summary.json`
- generation counts: 64/64 formulas completed, 1280 candidates, 1280
  DPO-eligible candidates, 544 generated geometry/chemistry preference pairs.
- strict QA note: 42 empty/zero preference-pair artifacts were reported, the
  same non-blocking pattern as earlier generation audits; candidate and audit
  artifacts were complete.

MLIP validation:

- batch:
  `outputs/mlip_validation_f3_only_mace_chgnet_matgl_consensus_epoch46003_64x20_20260514_batch/after/`
- selected candidates: 1254
- selected formulas: 64
- skipped candidates: 26, all `f1_not_pass`
- validation jobs:
  - `102606`, `fiir-mace-f3ep3-64x20`, `COMPLETED`, exit `0:0`, elapsed
    `00:05:37`, node `gpu40903`, normalized rows 1254
  - `102608`, `fiir-chgnet-f3ep3-64x20`, `COMPLETED`, exit `0:0`, elapsed
    `00:03:38`, node `gpu40904`, normalized rows 1254
  - `102610`, `fiir-matgl-f3ep3-64x20`, `COMPLETED`, exit `0:0`, elapsed
    `00:05:17`, node `gpu40904`, normalized rows 1254
- readiness:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x20/offline_validation_after_46003_64x20_seed20260513/readiness_after_summary.json`
  reports ready true for all three normalized validator files.
- fatal-log scan: no traceback, exception, OOM, killed, failed, cancelled,
  timeout, or runtime-error markers in the inspected validation logs; stderr
  warnings were model/library warnings.

Consensus and comparison:

- consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_epoch46003_64x20_after_20260514/`
- comparison:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x20/offline_validation_comparison_64x20_seed20260513/`

Matched comparison versus checkpoint 46002:

| metric | epoch 46002 | epoch 46003 | delta |
| --- | ---: | ---: | ---: |
| candidates | 1280 | 1280 | 0 |
| F1 fail rate | 0.0273438 | 0.0203125 | -0.00703125 |
| F2 fail rate | 0 | 0 | 0 |
| F3 available | 806 | 844 | +38 |
| strict stable consensus | 465 | 507 | +42 |
| unstable consensus | 341 | 337 | -4 |
| disagreement | 439 | 410 | -29 |
| all-three agreement rate | 0.647390 | 0.673046 | +0.025657 |
| stable consensus rate | 0.363281 | 0.396094 | +0.0328125 |
| preference-pair yield | 708 | 544 | -164 |
| unique sequence fraction | 0.972656 | 0.979688 | +0.00703125 |
| spacegroup count | 75 | 74 | -1 |

Interpretation:

- Epoch 46003 passed the first matched generated-output proxy gate versus
  epoch 46002 at 64x20.
- The improvement is broad across strict stable consensus, F3 availability,
  all-three agreement, disagreement reduction, F1 pass rate, and unique
  sequence fraction.
- The comparison still raises a conservative proxy-divergence flag only because
  spacegroup coverage decreased by one while stable consensus improved.
- Treat checkpoint 46003 as the current strongest bounded MLIP-proxy candidate,
  but do not run another DPO epoch yet. The next evidence step should be a
  larger matched 64x80 generation+MLIP confirmation or a carefully scoped
  fixed-candidate DFT pilot if compute policy allows.

## 2026-05-14: Start Epoch 46003 Matched 64x80 No-DFT Confirmation

Intent:

- Defer DFT as a future extension and finish the current no-DFT MLIP-proxy
  project flow first.
- Confirm checkpoint epoch 46003 against epoch 46002 at the larger matched
  64-formula x80-sample scale before making any next training/discovery
  decision.

Generation and batch preparation:

- configs:
  `configs/generated/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/after_46003_64x80_seed20260514_shards/`
- output roots:
  - `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/after_46003_64x80_seed20260514_shard_001`
  - `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/after_46003_64x80_seed20260514_shard_002`
- completed generation jobs:
  - `102636`, `fiir-f3ep3-x80-s1`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:12`, node `gpu40904`
  - `102637`, `fiir-f3ep3-x80-s2`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:13`, node `gpu40904`
- collection:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/collection_after_46003_64x80_seed20260514/collection_summary.json`
- generation counts: 64/64 formulas completed, 5120 candidates, 5120
  DPO-eligible candidates, 9584 generated geometry/chemistry preference pairs.
- strict QA note: 16 empty/zero preference-pair artifacts were reported; this
  is the same non-blocking pattern as earlier generation audits. Candidate and
  audit artifacts were complete.
- MLIP batch:
  `outputs/mlip_validation_f3_only_mace_chgnet_matgl_consensus_epoch46003_64x80_20260514_batch/after/`
- selected candidates: 5007
- selected formulas: 64
- skipped candidates: 113, all `f1_not_pass`

Validation jobs:

- `102643`, `fiir-mace-f3ep3-x80`, submitted with
  `--partition h200,h20,h20llm,gpu4090_128 --gres gpu:8`, no `--nodelist`;
  startup monitor saw it running on `gpu40904` with expected MACE/e3nn
  `torch.load` warnings only.
- `102644`, `fiir-chgnet-f3ep3-x80`, submitted with the same partition-wide
  8-GPU policy; startup monitor window ended while pending `(Resources)` and
  stderr empty.
- `102645`, `fiir-matgl-f3ep3-x80`, submitted with the same partition-wide
  8-GPU policy; startup monitor window ended while pending `(Priority)` and
  stderr empty.

Prepared follow-up artifacts:

- generation summary for the final comparison:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/offline_validation_comparison_64x80_seed20260514/generation_summary.json`
- finalization helper to run after all three normalized validation files exist:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/offline_validation_after_46003_64x80_seed20260514/finalize_after_validation.sh`

When the three jobs finish:

- Confirm each normalized validation file has 5007 rows.
- Run the finalization helper to create readiness, consensus, and comparison
  artifacts.
- Update this log with the matched 64x80 46003-vs-46002 comparison metrics.

## 2026-05-15: Complete Epoch 46003 Matched 64x80 No-DFT Confirmation

Validation completion:

- Slurm queue was empty after completion.
- completed validation jobs:
  - `102643`, `fiir-mace-f3ep3-x80`, `COMPLETED`, exit `0:0`, elapsed
    `00:17:59`, node `gpu40904`, MaxRSS `8824108K`
  - `102644`, `fiir-chgnet-f3ep3-x80`, `COMPLETED`, exit `0:0`, elapsed
    `00:16:52`, node `gpu40904`, MaxRSS `8057440K`
  - `102645`, `fiir-matgl-f3ep3-x80`, `COMPLETED`, exit `0:0`, elapsed
    `00:18:43`, node `gpu40904`, MaxRSS `9434184K`
- normalized validation rows:
  - MACE: 5007
  - CHGNet: 5007
  - MatGL: 5007
- readiness:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/offline_validation_after_46003_64x80_seed20260514/readiness_after_summary.json`
  reports ready true for all three normalized validator files.
- normalization summaries report 0 issues, 0 malformed rows, 0 formula
  mismatches, 0 unmatched candidate ids, and 5007 completed rows per
  validator.
- fatal-log scan found no traceback, exception, OOM, killed, cancelled,
  timeout, or runtime-error markers in the validation logs.

Consensus and comparison:

- consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_epoch46003_64x80_after_20260514/`
- comparison:
  `outputs/f3_only_mace_chgnet_matgl_consensus_epoch46003_vs_46002_64x80/offline_validation_comparison_64x80_seed20260514/`

Matched comparison versus checkpoint 46002:

| metric | epoch 46002 | epoch 46003 | delta |
| --- | ---: | ---: | ---: |
| candidates | 5120 | 5120 | 0 |
| F1 fail rate | 0.0273438 | 0.0220703 | -0.00527344 |
| F2 fail rate | 0 | 0 | 0 |
| F3 available | 3198 | 3156 | -42 |
| strict stable consensus | 1882 | 1889 | +7 |
| unstable consensus | 1316 | 1267 | -49 |
| disagreement | 1782 | 1851 | +69 |
| stable vote count | 8324 | 8462 | +138 |
| average stable votes/generated candidate | 1.62578 | 1.65273 | +0.026953 |
| average stable vote fraction/all generated | 0.541927 | 0.550911 | +0.008984 |
| average stable votes/validated candidate | 1.67149 | 1.69003 | +0.018548 |
| average stable vote fraction/validated | 0.557162 | 0.563345 | +0.006183 |
| all-three agreement rate | 0.642169 | 0.630318 | -0.0118511 |
| stable consensus rate | 0.367578 | 0.368945 | +0.00136719 |
| preference-pair yield | 12651 | 9584 | -3067 |
| unique sequence fraction | 0.972656 | 0.977930 | +0.00527344 |
| spacegroup count | 86 | 85 | -1 |
| spacegroup entropy | 4.01794 | 4.03207 | +0.0141293 |

Pairwise agreement:

| pair | epoch 46002 | epoch 46003 | delta |
| --- | ---: | ---: | ---: |
| CHGNet__MatGL | 0.753012 | 0.749351 | -0.003661 |
| MACE__CHGNet | 0.777309 | 0.760336 | -0.016974 |
| MACE__MatGL | 0.754016 | 0.750949 | -0.003067 |

Interpretation:

- The larger 64x80 audit weakly confirms a stable-consensus gain for epoch
  46003 over 46002, but the gain is much smaller than the 64x20 result.
- Average stable vote fraction is now treated as an important primary no-DFT
  model-improvement metric alongside strict stable consensus and F1 fail rate.
  By this average-stability metric, 46003 improves over 46002 both across all
  generated structures and within the MLIP-validated subset.
- The same audit raises a proxy-divergence flag because stable consensus rate
  increased while all-three agreement decreased, disagreement increased, and
  space-group count decreased.
- Treat checkpoint 46003 as a plausible current MLIP-proxy candidate, not a
  settled performance improvement and not a DFT-backed result.
- Do not run another DPO epoch from this evidence alone. DFT remains deferred
  as a future extension; the current track should close the no-DFT project
  flow with reporting, candidate triage, and reproducibility artifacts.
