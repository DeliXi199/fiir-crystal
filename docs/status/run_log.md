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
