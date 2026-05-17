# Current Project State

Last updated: 2026-05-17, Asia/Shanghai.

This file is the compact project memory for future Codex sessions. Read it
after `AGENTS.md` and before making roadmap, experiment, or implementation
decisions.

## Current Stage

- FIIR Crystal has a local-first scaffold, mock loop, CrystalFormer adapter,
  bulk orchestration, offline validation import boundary, comparison reports,
  active-loop simulation, and CrystalFormer DPO handoff boundary.
- The repository should not run real DPO training, DFT, MLIP execution, or
  external model installation inside the core `fiir_crystal` package.
- Current matched CrystalFormer DPO audits are complete through 64 formulas x
  80 samples for the revised F3-isolated follow-up checkpoint. The original
  aggregate strict-consensus DPO checkpoint did not improve strict three-MLIP
  stable consensus rate in the 64x20 proxy audit. A revised F3-isolated DPO
  artifact was built from after-64x20 all-agree three-MLIP consensus rows, with
  F1/F2 controlled to passing values and same-formula stable-vs-unstable pairs
  only. The one-epoch external CrystalFormer follow-up from that F3-only
  artifact completed and produced checkpoint epoch 46002. Its matched 64x20
  follow-up audit improved strict stable consensus from 456 to 465 (+9) versus
  the previous DPO-after checkpoint baseline. The larger matched 64x80 audit
  improved strict stable consensus from 1800 to 1882 (+82), stable consensus
  rate from 0.351562 to 0.367578 (+0.016016), all-three agreement rate from
  0.641728 to 0.642169 (+0.000440), and disagreement from 1791 to 1782 (-9),
  while F3-available count decreased from 3208 to 3198 (-10), F1 fail rate
  increased from 0.023633 to 0.027344 (+0.003711), and diversity signals dipped
  slightly. A fixed-candidate log-probability audit then scored the same 861
  selected candidates under checkpoints 46001 and 46002: after-minus-before
  median logp moved `+39.6` for stable consensus candidates, `-78235.5` for
  unstable consensus candidates, and `-22306.5` for disagreement candidates,
  giving a positive stable-minus-unstable delta gap of `+572318.6`. Treat this
  as a stronger positive MLIP-proxy and model-likelihood signal with a
  conservative proxy-divergence flag, not a performance claim. A bounded
  continuation probe then trained one additional epoch from 46002 to 46003 and
  re-scored the same panel: 46003-vs-46002 median logp moved `+25.0` for stable
  consensus candidates, `-84341.25` for unstable candidates, and `-24775.55`
  for disagreement candidates, with stable-minus-unstable gap `+560338.4`.
  The matched 64x20 generation+MLIP gate for 46003 vs 46002 is now complete:
  strict stable consensus improved from 465 to 507 (+42), stable consensus
  rate from 0.363281 to 0.396094 (+0.032813), F3-available count from 806 to
  844 (+38), all-three agreement rate from 0.647390 to 0.673046 (+0.025657),
  disagreement fell from 439 to 410 (-29), and F1 fail rate fell from 0.027344
  to 0.020313 (-0.007031). The only remaining proxy-divergence flag in this
  64x20 gate is a slight space-group coverage dip from 75 to 74 while stable
  consensus improved. The matched 64x80 generation+MLIP confirmation for
  46003 versus 46002 is now complete: strict stable consensus increased only
  slightly from 1882 to 1889 (+7), stable consensus rate from 0.367578 to
  0.368945 (+0.001367), stable vote count rose from 8324 to 8462 (+138),
  average stable votes per generated structure rose from 1.6258/3 to
  1.6527/3 (+0.0270), average stable vote fraction across all generated
  structures rose from 0.541927 to 0.550911 (+0.008984), F1 fail rate fell
  from 0.027344 to 0.022070 (-0.005273), and unique sequence fraction rose
  from 0.972656 to 0.977930 (+0.005273). Treat average stable vote fraction
  as an important primary no-DFT model-improvement metric alongside strict
  stable consensus and F1 fail rate. However, F3-available count fell from
  3198 to 3156 (-42),
  all-three agreement rate fell from 0.642169 to 0.630318 (-0.011851),
  disagreement rose from 1782 to 1851 (+69), preference-pair yield fell from
  12651 to 9584 (-3067), and space-group count dipped from 86 to 85 (-1).
  The 64x80 proxy-divergence screen is therefore flagged. Treat checkpoint
  46003 as a plausible current MLIP-proxy candidate with weaker large-audit
  confirmation than the 64x20 result, not a DFT-backed performance claim. Do
  not run another DPO epoch yet. DFT is deferred as a future extension; first
  finish the current no-DFT project flow end to end. All labels are MLIP
  relaxation proxy evidence, not DFT or hull-confirmed stability.
- Formula-holdout generalization audit
  `outputs/f3_formula_holdout_64x80_20260517` is complete. It compares the
  original CrystalFormer checkpoint against F3 continuation-2 checkpoint 46003
  on 64 held-out ABO3 formulas from
  `configs/formula_banks/perovskite_128.json` positions 65-128, which were not
  used in the F3 rank-neighbor DPO pair mining formula bank. The matched setup
  is 64 formulas x 80 samples, seed 20260517, top-k 40, with three-MLIP
  relaxation consensus. Original-vs-46003 strict stable consensus improved
  from 1493 to 1694 (+201), stable consensus rate from 0.291602 to 0.330859
  (+0.039258), stable vote count from 7062 to 7730 (+668), average stable vote
  fraction across all generated structures from 0.459766 to 0.503255
  (+0.043490), F1 fail rate from 0.024023 to 0.021875 (-0.002148), unique
  sequence fraction from 0.975977 to 0.978125 (+0.002148), and space-group
  count from 84 to 85 (+1). F3-available count decreased from 3218 to 3193
  (-25), all-three agreement rate decreased from 0.643986 to 0.637580
  (-0.006407), disagreement increased from 1779 to 1815 (+36), and
  preference-pair yield decreased from 11199 to 9737 (-1462), so keep the
  conservative proxy-divergence flag. CHGNet and MatGL F3-cont2 strict SLURM
  tasks each had one failed row; their raw 5008-row outputs were normalized to
  5007 F3-available rows and final report job 106148 completed successfully.
  The generated holdout submission script has been corrected to use non-strict
  MLIP validation (`FIIR_MACE_STRICT=0`, `FIIR_MLIP_STRICT=0`) so single
  failed relaxations are recorded as unavailable rows instead of blocking the
  whole dependency chain. Bare `gpu4090` remains excluded; allowed GPU
  partitions are `h200,h20,h20llm,gpu4090_8,gpu4090_128`.
- A new user-requested larger formal F3 training/evaluation chain has been
  submitted as
  `outputs/f3_big_rank_neighbor_from_original_128x160_20260517`. It follows
  the baseline rule: generate pair-mining samples from the original
  CrystalFormer checkpoint `external/checkpoints/crystalformer/alex20s_csp`,
  build F3 good-vs-near-miss same-formula rank-neighbor pairs from three-MLIP
  relaxation force evidence, train one DPO epoch from the original checkpoint,
  then generate matched after samples and run the same three-MLIP evaluation.
  Scale: 128 ABO3 formulas x 160 samples = 20480 generated candidates per
  side, seed 20260517, top-k 40, temperature 1.0, top-p 1.0. The chain uses
  non-strict MLIP validation and the allowed GPU partition list
  `h200,h20,h20llm,gpu4090_8,gpu4090_128`; bare `gpu4090` remains excluded.
  Submitted SLURM jobs: base generation 106544-106547, base collect 106548,
  base MLIP 106549-106551, pair build / DPO prepare 106552, train 106553,
  after generation 106554-106557, after collect 106558, after MLIP
  106559-106561, final report 106562. As of submission, 106544 was running on
  `gpu4090_8` / `gpu40902`; all later jobs were pending on dependencies.
  When results are ready, compare against the original baseline using the full
  reporting template: settings, F1/F2, F3 consensus, per-MLIP stable counts,
  average stable vote fraction, force mean/median/p90/p95, disagreement,
  pairwise agreement, pair yield, uniqueness/diversity, formula-level
  improvements/regressions, and proxy-divergence caveats.

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
- Baseline rule for all future F-metric experiments: compare trained models
  against the original CrystalFormer checkpoint
  `external/checkpoints/crystalformer/alex20s_csp`, and start each DPO training
  run from that same original checkpoint unless the user explicitly asks for a
  continuation experiment. Once a matching original-model baseline dataset has
  been generated and MLIP/other validation evidence has been computed for a
  fixed formula bank, sampling setup, and validator setup, reuse that original
  baseline artifact for later comparisons instead of regenerating it. New
  trained checkpoints should generate their own matched after samples and be
  compared back to the cached original-model baseline.
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
  - External Alex-20-only StructureMatcher worker exists at:
    `experiments/run_f4_structure_matcher_audit.py`. It is intentionally outside
    the `fiir_crystal` core package.
  - First real F4 audit results now exist:
    `outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl`
    with 1024 rows.
  - F4 worker summary:
    `outputs/f4_novelty_audit/reference_pool_v1/f4_structure_matcher_audit_summary.json`
    reports exact-formula Alex-20 bucket matching, 186 selected same-formula
    references across the 64 candidate formulas, 0 reference parse failures, 0
    candidate parse failures, 768 same-formula no-match candidates, 256
    no-exact-formula-bucket candidates, and 0 high-leakage StructureMatcher
    matches.
  - Post-result readiness check:
    `outputs/f4_novelty_audit/reference_pool_v1/readiness_summary_with_results.json`
    reports ready true with 1024 result rows.
  - Imported F4 candidates:
    `outputs/f4_novelty_import_1024_20260514/candidates_with_f4.jsonl`
    with summary
    `outputs/f4_novelty_import_1024_20260514/f4_import_summary.json`.
    Import matched 1024/1024 candidates with 0 missing rows, 0 orphan rows, and
    0 high-leakage candidates.
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
  chooses the best currently free eligible non-`test` GPU partition and submits
  with `--partition` and `--gres`, deliberately without `--nodelist`; SLURM
  assigns the final node at runtime. GPU start-now eligibility is based on free
  GPU count only, not idle CPU or free-memory counts. CPU and memory are request
  sizing knobs.
- The global GPU policy blocks the bare `gpu4090` partition by default because
  the project account cannot submit there. Named 4090 partitions such as
  `gpu4090_8` and `gpu4090_128` remain eligible in both auto and explicit
  allowlist modes.
- Do not treat `gpu4090_8` or `gpu4090_128` as forbidden. For many small
  CrystalFormer/MLIP relaxation loops they can be competitive with or faster
  than H200 because Python/ASE/model orchestration and per-structure overhead
  can dominate raw GPU throughput. Use controlled same-job benchmarks before
  drawing hardware conclusions.
- `FIIR_GPU_RESERVED_NODES_FILE` is retained only for backward-compatible
  provenance. The GPU submitter no longer appends selected nodes or treats a
  submitted partition-wide job as claiming a fixed node.
- Flexible GPU queueing records the candidate partition set and intentionally
  does not use `--nodelist`; it requests the queued compatibility shape and
  leaves final node assignment to SLURM runtime.
- For larger GPU work, set `FIIR_GPU_MIN_GPUS` / `--min-gpus` to the GPU count
  the job should actually use. Flexible mode still requests GPUs with `--gres`
  and must not be used as a CPU-only placement shortcut.
- For larger CrystalFormer generation, MLIP validation, DPO smoke/evaluation,
  and similar GPU compute jobs, request 8 GPUs on current long-running CUDA GPU
  partitions unless the workflow has a documented smaller target partition.
- General GPU request rule: use `FIIR_GPU_QUEUE_MIN_GPUS=8` and
  `FIIR_GPU_QUEUE_MIN_CPUS=32` for normal 8-GPU generation/validation jobs,
  plus an explicit right-sized memory request
  `FIIR_GPU_QUEUE_MEMORY_MB=256000`, so partition-wide submissions can start on
  any compatible GPU node without inheriting a 2TB full-node memory default.
  Match task-level concurrency to the requested allocation.
- The `test` partition is non-preferred CUDA-compatible GPU capacity. It is
  eligible only for short GPU jobs with an explicit time limit of 30 minutes or
  less, and only after no non-`test` GPU partition has enough free GPUs to
  start now. Flexible queueing excludes `test` whenever any normal GPU
  partition is queueable. Use an explicit `FIIR_GPU_PARTITIONS=test` allowlist
  only for a deliberate short test-only job.

## Latest Durable Results

These are the currently important artifacts and counts.

### Clean Original-Baseline F3 Rank-Neighbor Run

- Run root:
  `outputs/f3_rank_neighbor_from_initial_64x80_20260515/`
- This is the first completed F3 rank-neighbor run that follows the current
  baseline rule end to end: pair mining used original-model 64x80 samples,
  training started from the original CrystalFormer checkpoint, and validation
  compares the trained checkpoint back to the original-model baseline.
- Formula bank and generation settings:
  64 formulas x 80 samples, seed `20260514`, `top_k=40`,
  `temperature=1.0`, `top_p=1.0`.
- Original baseline checkpoint:
  `external/checkpoints/crystalformer/alex20s_csp`
- Trained checkpoint:
  `outputs/crystalformer_dpo_runs/f3_rank_neighbor_from_initial_64x80_20260515/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1`
- Training manifest:
  `outputs/crystalformer_dpo_runs/f3_rank_neighbor_from_initial_64x80_20260515/dpo_smoke_manifest.json`
  records `base_checkpoint_dir=external/checkpoints/crystalformer/alex20s_csp`,
  checkpoint start epoch `46000`, target epoch `46001`, and 7311 prepared
  F3 DPO pairs.
- Pair build:
  `outputs/dpo_preferences/f3_rank_neighbor_from_initial_64x80_20260515/dpo_preferences/preference_summary.json`
  matched 4961 F3 candidates from original samples, with 1830 good candidates,
  320 near-miss candidates, and 7311 same-formula rank-neighbor pairs using
  `good_force_max=0.05`, `near_miss_force_max=0.10`, and
  `rank_neighbor_count=5`.
- All submitted SLURM jobs `103486`-`103499` completed with exit code `0:0`.
  The only notable log line was CrystalFormer training reporting
  `failed to update opt_state from checkpoint`; the job completed and wrote the
  expected after checkpoint.
- Original/base generation:
  64/64 formulas completed, 5120 candidates, 5120 DPO eligible, 146 F1
  failures, 0 F2 failures, 4974 selected for MLIP validation.
- Trained/after generation:
  64/64 formulas completed, 5120 candidates, 5120 DPO eligible, 103 F1
  failures, 0 F2 failures, 5017 selected for MLIP validation.
- Final original-vs-after comparison:
  `outputs/f3_rank_neighbor_from_initial_64x80_20260515/offline_validation_comparison_base_vs_after_64x80_seed20260514/summary.json`
- Detailed analysis:
  `outputs/f3_rank_neighbor_from_initial_64x80_20260515/detailed_validation_analysis_base_vs_after_64x80_seed20260514/summary.json`
- Main MLIP-proxy deltas versus the original model:
  strict three-MLIP stable consensus 1830 -> 1928 (+98), stable consensus rate
  0.357422 -> 0.376563 (+0.019141), F3-available count 3225 -> 3281 (+56),
  all-three agreement rate 0.648372 -> 0.653976 (+0.005605),
  disagreement 1749 -> 1736 (-13), unstable consensus 1395 -> 1353 (-42),
  stable vote count 8128 -> 8402 (+274), and average stable vote fraction over
  all generated structures 0.529167 -> 0.547005 (+0.017839).
- Secondary generation-quality/diversity deltas:
  F1 fail rate 0.028516 -> 0.020117 (-0.008398), unique sequence fraction
  0.971484 -> 0.979883 (+0.008398), space-group count 84 -> 83 (-1), and
  space-group entropy 4.022043 -> 4.027174 (+0.005131).
- Per-validator stable labels increased:
  CHGNet 2506 -> 2651 (+145), MACE 2735 -> 2785 (+50), MatGL 2887 -> 2966
  (+79).
- Three-MLIP per-sample mean `force_max` stats are stored at
  `outputs/f3_rank_neighbor_from_initial_64x80_20260515/detailed_validation_analysis_base_vs_after_64x80_seed20260514/ensemble_mean_force_stats.json`.
  Across all validated samples, the median three-MLIP mean force moved
  0.090740 -> 0.085374 eV/Angstrom (-0.005366) and the mean moved
  0.297173 -> 0.267028 (-0.030145). For strict stable-consensus samples, the
  median moved 0.042012 -> 0.041577 (-0.000435) and the mean moved
  0.036820 -> 0.035409 (-0.001412).
- High-confidence after candidates:
  1928 candidates pass all three MLIPs at force <= 0.05 eV/Angstrom across all
  64 formulas; tier A <= 0.03 has 284 candidates, tier B <= 0.04 has 78
  candidates, and tier C has 1566 candidates.
- Top improved formulas by strict stable consensus count:
  SrThO3 +13, DyAlO3 +11, GdAlO3 +11, BaSiO3 +11, LaScO3 +10.
- Top regressed formulas:
  SmAlO3 -17, CaTiO3 -13, CaSiO3 -8, HoAlO3 -8, BaSnO3 -7, YInO3 -7.
- Proxy-divergence screen remains flagged because stable consensus improved
  while space-group count dipped by 1. This is a caution flag only; the main
  no-DFT MLIP-proxy signal is positive versus the original model.
- Caveat: all F3 labels here are MACE+CHGNet+MatGL relaxation proxy evidence,
  not DFT or hull-confirmed stability.

### F3 Rank-Neighbor Continuation Probe

- Run root:
  `outputs/f3_rank_neighbor_continuation_64x80_20260516/`
- This was an explicit user-requested continuation probe, so it is an exception
  to the default "start every new experiment from the original checkpoint"
  rule. It started from the current F3 checkpoint above, mined fresh F3 pairs
  from current-checkpoint 64x80 samples, trained one more DPO epoch, and then
  compared both current-vs-continued and original-vs-continued.
- Training manifest:
  `outputs/crystalformer_dpo_runs/f3_rank_neighbor_continuation_64x80_20260516/dpo_smoke_manifest.json`
  records checkpoint start epoch `46001`, target epoch `46002`, and 8272
  prepared F3 DPO pairs.
- Pair build:
  `outputs/dpo_preferences/f3_rank_neighbor_continuation_64x80_20260516/dpo_preferences/preference_summary.json`
  matched 5004 F3 candidates from current-model samples, with 1928 good
  candidates, 332 near-miss candidates, and 8272 same-formula rank-neighbor
  pairs using `good_force_max=0.05`, `near_miss_force_max=0.10`, and
  `rank_neighbor_count=5`.
- All submitted continuation SLURM jobs `104227`-`104234` completed with exit
  code `0:0`.
- Continuation-after generation:
  64/64 formulas completed, 5120 candidates, 5120 DPO eligible, 116 F1
  failures, 0 F2 failures, and 5004 selected for MLIP validation.
- Current-vs-continued comparison:
  `outputs/f3_rank_neighbor_continuation_64x80_20260516/offline_validation_comparison_current_vs_continued_64x80_seed20260514/summary.json`
  shows strict three-MLIP stable consensus 1928 -> 2066 (+138), stable
  consensus rate 0.376563 -> 0.403516 (+0.026953), F3-available count
  3281 -> 3280 (-1), all-three agreement rate 0.653976 -> 0.655476
  (+0.001499), disagreement 1736 -> 1724 (-12), unstable consensus
  1353 -> 1214 (-139), stable vote count 8402 -> 8750 (+348), and average
  stable vote fraction over all generated structures 0.547005 -> 0.569661
  (+0.022656). F1 fail rate worsened slightly from 0.020117 to 0.022656
  (+0.002539), and unique sequence fraction fell from 0.979883 to 0.977344
  (-0.002539), while space-group count improved from 83 to 85 and entropy
  improved from 4.027174 to 4.042433. The current-vs-continued
  proxy-divergence screen remains flagged due the slight F1/unique-fraction
  tradeoff.
- Original-vs-continued comparison:
  `outputs/f3_rank_neighbor_continuation_64x80_20260516/offline_validation_comparison_original_vs_continued_64x80_seed20260514/summary.json`
  shows cumulative strict stable consensus 1830 -> 2066 (+236), stable
  consensus rate 0.357422 -> 0.403516 (+0.046094), F3-available count
  3225 -> 3280 (+55), all-three agreement rate 0.648372 -> 0.655476
  (+0.007104), disagreement 1749 -> 1724 (-25), unstable consensus
  1395 -> 1214 (-181), stable vote count 8128 -> 8750 (+622), average stable
  vote fraction over all generated structures 0.529167 -> 0.569661
  (+0.040495), F1 fail rate 0.028516 -> 0.022656 (-0.005859), unique
  sequence fraction 0.971484 -> 0.977344 (+0.005859), space-group count
  84 -> 85 (+1), and entropy 4.022043 -> 4.042433 (+0.020390). The
  original-vs-continued proxy-divergence screen is false.
- Three-MLIP per-sample mean `force_max`:
  - Current-vs-continued all-validated mean force 0.267028 -> 0.263901
    eV/Angstrom (-0.003128, -1.17%); strict-stable mean force
    0.035409 -> 0.034400 (-0.001009, -2.85%).
  - Original-vs-continued all-validated mean force 0.297173 -> 0.263901
    (-0.033273, -11.20%); strict-stable mean force 0.036820 -> 0.034400
    (-0.002420, -6.57%).
- High-confidence continued candidates:
  2066 candidates pass all three MLIPs at force <= 0.05 eV/Angstrom across all
  64 formulas; tier A <= 0.03 has 365 candidates, tier B <= 0.04 has 80
  candidates, and tier C has 1621 candidates.
- Top current-vs-continued improved formulas:
  CaTiO3 +15, SmAlO3 +13, SrCeO3 +12, PrAlO3 +12, NdInO3 +9, BaZrO3 +9,
  HoAlO3 +9, SrThO3 +7.
- Top current-vs-continued regressed formulas:
  HoInO3 -14, NdScO3 -9, DyInO3 -6, YGaO3 -6, BaSiO3 -5, NdGaO3 -5,
  PrScO3 -5.
- Interpretation: one additional F3 rank-neighbor DPO epoch still improved the
  MLIP proxy stability signal substantially, but because F1 fail rate and
  unique sequence fraction degraded slightly versus the current checkpoint,
  avoid blindly continuing many more epochs without a smaller gate or a fixed
  candidate likelihood/stability audit. Against the original baseline, the
  continuation checkpoint is the strongest no-DFT MLIP-proxy result so far.

### F3 Rank-Neighbor Second Continuation Probe

- Run root:
  `outputs/f3_rank_neighbor_continuation2_64x80_20260516/`
- This was a second explicit user-requested continuation probe. It started from
  the `epoch_046002` F3 continuation checkpoint, mined fresh F3 pairs from that
  checkpoint's 64x80 samples, trained one more DPO epoch to `epoch_046003`, and
  compared both latest-vs-continuation2 and original-vs-continuation2.
- Training manifest:
  `outputs/crystalformer_dpo_runs/f3_rank_neighbor_continuation2_64x80_20260516/dpo_smoke_manifest.json`
  records checkpoint start epoch `46002`, target epoch `46003`, and 8006
  prepared F3 DPO pairs.
- Pair build:
  `outputs/dpo_preferences/f3_rank_neighbor_continuation2_64x80_20260516/dpo_preferences/preference_summary.json`
  matched 4993 F3 candidates from latest-model samples, with 2065 good
  candidates, 307 near-miss candidates, and 8006 same-formula rank-neighbor
  pairs. Two formulas lacked either good or near-miss candidates.
- All submitted second-continuation SLURM jobs `104503`-`104510` completed with
  exit code `0:0`.
- Second-continuation-after generation:
  64/64 formulas completed, 5120 candidates, 5120 DPO eligible, 99 F1
  failures, 0 F2 failures, and 5021 selected for MLIP validation.
- Latest-vs-continuation2 comparison:
  `outputs/f3_rank_neighbor_continuation2_64x80_20260516/offline_validation_comparison_latest_vs_continuation2_64x80_seed20260514/summary.json`
  shows strict three-MLIP stable consensus 2066 -> 2208 (+142), stable
  consensus rate 0.403516 -> 0.431250 (+0.027734), F3-available count
  3280 -> 3405 (+125), all-three agreement rate 0.655476 -> 0.678152
  (+0.022676), disagreement 1724 -> 1616 (-108), unstable consensus
  1214 -> 1197 (-17), stable vote count 8750 -> 9075 (+325), and average
  stable vote fraction over all generated structures 0.569661 -> 0.590820
  (+0.021159). F1 fail rate improved from 0.022656 to 0.019336 (-0.003320)
  and unique sequence fraction improved from 0.977344 to 0.980664
  (+0.003320). Space-group count fell from 85 to 84 and entropy fell from
  4.042433 to 4.004449, so latest-vs-continuation2 still has a
  proxy-divergence caution flag for diversity/coverage.
- Original-vs-continuation2 comparison:
  `outputs/f3_rank_neighbor_continuation2_64x80_20260516/offline_validation_comparison_original_vs_continuation2_64x80_seed20260514/summary.json`
  shows cumulative strict stable consensus 1830 -> 2208 (+378), stable
  consensus rate 0.357422 -> 0.431250 (+0.073828), F3-available count
  3225 -> 3405 (+180), all-three agreement rate 0.648372 -> 0.678152
  (+0.029780), disagreement 1749 -> 1616 (-133), unstable consensus
  1395 -> 1197 (-198), stable vote count 8128 -> 9075 (+947), average stable
  vote fraction over all generated structures 0.529167 -> 0.590820
  (+0.061654), F1 fail rate 0.028516 -> 0.019336 (-0.009180), unique
  sequence fraction 0.971484 -> 0.980664 (+0.009180), and space-group count
  remained 84. Entropy is slightly lower than original, 4.022043 -> 4.004449
  (-0.017594), but the original-vs-continuation2 proxy-divergence screen is
  false.
- Three-MLIP per-sample mean `force_max`:
  - Latest-vs-continuation2 all-validated mean force 0.263901 -> 0.258733
    eV/Angstrom (-0.005167, -1.96%); strict-stable mean force
    0.034400 -> 0.034327 (-0.000073, -0.21%).
  - Original-vs-continuation2 all-validated mean force 0.297173 -> 0.258733
    (-0.038440, -12.94%); strict-stable mean force 0.036820 -> 0.034327
    (-0.002493, -6.77%).
- High-confidence continuation2 candidates:
  2208 candidates pass all three MLIPs at force <= 0.05 eV/Angstrom across all
  64 formulas; tier A <= 0.03 has 381 candidates, tier B <= 0.04 has 82
  candidates, and tier C has 1745 candidates.
- Stable-consensus trajectory at 64x80:
  original 1830 -> F3 from original 1928 -> continuation1 2066 ->
  continuation2 2208.
- Interpretation: the second continuation still improved the main MLIP-proxy
  stability metrics and improved F1/unique sequence rate versus continuation1,
  so the optimization has not obviously saturated. However, pair yield and
  near-miss candidates are thinning, and space-group entropy declined versus
  continuation1. Treat `epoch_046003` as the strongest no-DFT MLIP-proxy
  checkpoint so far, but run a fixed-candidate likelihood/stability audit or a
  smaller gate before continuing many more epochs.

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

The current preferred F3-isolated follow-up DPO preference artifact is:

```text
outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/dpo_preferences/preference_pairs.jsonl
```

Summary:

- source candidates: after checkpoint 64 formulas x 20 samples audit.
- source validation:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_64x20_after_20260514/consensus_validation_results.jsonl`
- consensus input rows: 1243
- all-agree F3 candidates retained after F1/F2 control: 801
- retained stable / unstable candidates: 456 / 345
- skipped candidates: 438 non-agreement or missing F3, 4 F1/F2 not passing
- preference pairs: 2156
- valid training pairs: 2156
- invalid training pairs: 0
- preference type: `stability_aware_offline_validation`
- preference reason: `f3_consensus_only`, `three_mlip_all_agree`,
  `f1_f2_controlled`
- important difference from the 1024 aggregate artifact: pair ordering is
  F3-only, with chosen/rejected both constrained to F1/F2 passing values, so
  F1/F2 no longer determine the preference direction.
- caveat: this is still all-agree MLIP relaxation proxy evidence, not DFT or
  self-consistent hull-confirmed stability.

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

The current F3-isolated handoff artifact is:

```text
outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/training_boundary/trainer_manifest.json
```

Summary:

- ready for external training: true
- input pairs: 2156
- valid pairs: 2156
- invalid pairs: 0
- stability-aware pair count: 2156
- train DPO in FIIR: false
- preference source:
  `outputs/dpo_preferences/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514/dpo_preferences/preference_pairs.jsonl`
- evidence context:
  - input candidates: 1243
  - strict consensus F3-available candidates: 805
  - disagreement candidates excluded from F3: 438
  - source validation:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_64x20_after_20260514/consensus_validation_results.jsonl`
- caveat: the F3-only labels are MLIP relaxation proxy evidence, not DFT
  evidence and not self-consistent hull-confirmed stability.
- warning: CrystalFormer is a normal clone; fork/submodule is recommended for
  future training work.

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

### Completed F3-Isolated Follow-Up DPO Audit

The F3-isolated preference artifact above has now been used for a one-epoch
external CrystalFormer DPO follow-up and a matched 64 formulas x 20 samples
after-generation audit. This comparison uses the previous DPO-after checkpoint
epoch 46001 as the baseline and the F3-only follow-up checkpoint epoch 46002 as
the new after checkpoint; it is not the original base-model comparison.

Training package and checkpoint:

- package:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_smoke_prepare/`
- prepared pairs: 2156
- checkpoint start epoch: 46001
- checkpoint target epoch: 46002
- produced checkpoint:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046002.pkl`
- checkpoint sha256:
  `7860e7c79f1fca24d2ac3f57281d91fd6c000c1cf726d20a9a9000b6281367bd`
- SLURM job: `101758`, `fiir-f3only-dpo`, `COMPLETED`, exit `0:0`,
  elapsed `00:04:09`, node `gpuh2001`, requested `gpu:8`
- GPU evidence: `CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7`, JAX default backend
  `gpu`, and 8 CUDA devices visible in the startup log.
- training row: epoch 46002 loss / dpo_loss `405.355835 / 405.355835`,
  validation loss / validation dpo_loss `474.216217 / 474.216217`.

Follow-up generation and validation:

- generation configs:
  `configs/generated/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/after_64x20_seed20260513_shards/`
- generation outputs:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/after_64x20_seed20260513_shard_001`
  and
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/after_64x20_seed20260513_shard_002`
- generation jobs:
  - `101762`, `fiir-f3after-s2`, `COMPLETED`, exit `0:0`, elapsed
    `00:05:06`, node `gpuh2002`, requested `gpu:8`
  - `101763`, `fiir-f3after-s1flex`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:57`, node `gpuh2002`, requested `gpu:8`
- collection:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/collection_after_64x20_seed20260513/collection_summary.json`
  reports 64/64 formulas, 1280 candidates, 1280 DPO-eligible candidates, and
  708 generated geometry/chemistry preference pairs.
- MLIP validation batch:
  `outputs/mlip_validation_f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_batch/after/`
  with 1245 selected candidates, 64 formulas, 35 skipped candidates, and
  skipped reason `f1_not_pass`.
- validation jobs:
  - `101767`, `fiir-mace-f3after64`, `COMPLETED`, exit `0:0`, elapsed
    `00:05:13`, node `gpuh2001`, normalized rows 1245
  - `101768`, `fiir-chgnet-f3after64`, `COMPLETED`, exit `0:0`, elapsed
    `00:04:40`, node `gpuh2002`, normalized rows 1245
  - `101769`, `fiir-matgl-f3after64`, `COMPLETED`, exit `0:0`, elapsed
    `00:06:27`, node `gpuh2002`, normalized rows 1245
- submission strategy: MACE pinned to free `gpuh2001`, CHGNet pinned to free
  `gpuh2002`, and MatGL submitted flexible while both nodes were reserved by
  the batch, then started on `gpuh2002` after CHGNet released it.
- readiness:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x20_before_after/offline_validation_after_64x20_seed20260513/readiness_after_summary.json`
  reports ready true for all three normalized validator files.
- consensus:
  `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_64x20_after_20260514/`
  with overlap 1245, F3 available 806, stable consensus 465, unstable
  consensus 341, disagreement/unavailable 439, and agreement rate 0.647390.
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

- F3-only DPO produced a small positive strict stable-consensus delta (+9) at
  the matched 64x20 scale.
- The proxy-divergence screen remains flagged because stable rate increased
  while all-three agreement decreased very slightly and disagreement increased
  by one candidate.
- This is better than the previous aggregate checkpoint, but still not enough
  for a performance claim. The next gate should be a fixed-candidate audit,
  larger matched sample, or additional carefully bounded epoch sweep before any
  training-scale escalation.
- Evidence caveat: these labels are MACE+CHGNet+MatGL relaxation consensus
  proxy evidence, not DFT evidence and not self-consistent hull-confirmed
  stability.

### Completed F3-Isolated 64x80 Matched Proxy Audit

The F3-isolated follow-up checkpoint epoch 46002 has also been evaluated in a
larger matched 64 formulas x 80 samples audit against the previous DPO-after
checkpoint epoch 46001.

Generation and validation:

- generation outputs:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/`
- generation jobs:
  - `101785`, `fiir-f3x80-b1`, `COMPLETED`, exit `0:0`
  - `101786`, `fiir-f3x80-b2`, `COMPLETED`, exit `0:0`
  - `101787`, `fiir-f3x80-a1`, `COMPLETED`, exit `0:0`
  - `101788`, `fiir-f3x80-a2`, `COMPLETED`, exit `0:0`
- generation counts: 64 formulas x 80 samples for before and after, 5120
  candidates per side, 5120 DPO-eligible candidates per side.
- before collection:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/collection_before_64x80_seed20260514/collection_summary.json`
- after collection:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/collection_after_64x80_seed20260514/collection_summary.json`
- MLIP validation batches:
  `outputs/mlip_validation_f3_only_mace_chgnet_matgl_consensus_64x80_20260514_batch/`
  with 4999 selected before candidates and 4980 selected after candidates.
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
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/offline_validation_64x80_seed20260514/readiness_before_summary.json`
  and
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/offline_validation_64x80_seed20260514/readiness_after_summary.json`
  both report ready true.
- strict three-MLIP consensus artifacts:
  - before:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_64x80_before_20260514/`
  - after:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_f3_only_64x80_after_20260514/`
- final matched comparison:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/offline_validation_comparison_64x80_seed20260514/`
- formula-level diagnosis:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/diagnostics_64x80_seed20260514/`
  with `summary.json`, `formula_deltas.jsonl`, and `report.md`.
- fixed-candidate log-probability audit:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/`
  with panel `manifest.json`, `panel_sequences.jsonl`, run script
  `run_fixed_candidate_logp_audit.sh`, and scored outputs under `logp_scores/`.
- fatal-log scan over the six validation SLURM logs found no traceback,
  exception, OOM, killed, failed, cancelled, CUDA error, or runtime-error
  markers. Stderr/log warnings were library/model warnings.

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
  stable consensus increased by 82 and all-three agreement increased slightly,
  while disagreement decreased.
- The proxy-divergence screen remains flagged because stable consensus rate
  improved while F1 fail rate increased and diversity signals decreased
  slightly.
- Formula-level diagnosis shows the largest stable-consensus gains from
  GdAlO3 +12, YGaO3 +9, PbZrO3 +8, LaGaO3 +8, and CaCeO3 +8; the largest
  losses are CaGeO3 -8, PbHfO3 -8, SrCeO3 -8, HoAlO3 -7, and DyScO3 -5.
  Largest F1-fail increases include PbTiO3 +5 and YAlO3/PrAlO3/NdScO3/DyScO3
  +3 each.
- Fixed-candidate log-probability audit job `102594` completed on `test001`
  with JAX GPU backend and two CUDA devices visible. It scored 861 candidates
  under before checkpoint epoch 46001 and after checkpoint epoch 46002, writing
  1722 score rows. Median after-minus-before logp was `+39.6` for stable
  consensus candidates, `-78235.5` for unstable consensus candidates, and
  `-22306.5` for disagreement candidates; the stable-minus-unstable delta gap
  was `+572318.6`.
- Treat this as positive MLIP-relaxation proxy and model-likelihood evidence,
  not a DFT-backed performance claim. The fixed panel supports that checkpoint
  46002 learned to favor stable consensus candidates relative to unstable ones,
  but the F1/diversity proxy-divergence flag means the next GPU step should
  remain a small bounded epoch sweep or targeted validation, not broad
  training-scale escalation.

### Completed Bounded Epoch 46003 Continuation Guard

After the positive fixed-candidate audit for epoch 46002, a deliberately small
continuation probe trained one more external CrystalFormer DPO epoch from
checkpoint 46002 to checkpoint 46003 using the same F3-isolated 2156-pair
preference artifact.

Training package:

- package:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_epoch46003_prepare/`
- base checkpoint:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_smoke_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1`
- produced checkpoint:
  `outputs/crystalformer_dpo_runs/f3_only_mace_chgnet_matgl_consensus_64x20_after_20260514_epoch46003_prepare/after_checkpoint/beta_0.1_label_0_gamma_0_adam_bs_32_lr_1e-05_decay_0_clip_1_A_119_W_28_N_21_Nf_5_Kx_16_Kl_4_h0_256_l_16_H_8_k_32_m_256_e_256_drop_0.1/epoch_046003.pkl`
- checkpoint sha256:
  `f6d26488bd95602f1ab72369aa1dc0e1e14bb5a08ba7feb2c28adc570b19f065`
- SLURM job: `102595`, `fiir-f3only-ep46003`, `COMPLETED`, exit `0:0`,
  elapsed `00:02:47`, node `test001`, requested `gpu:rtx4090:2`.
- training row: epoch 46003 loss / dpo_loss `447.105591 / 447.105591`,
  validation loss / validation dpo_loss `222.710953 / 222.710953`.
- fatal-log scan found no traceback, exception, OOM, killed, failed,
  cancelled, CUDA error, runtime-error, or `Error` markers. Stderr contained
  XLA autotuning warnings only.

Fixed-candidate log-probability guard:

- run script:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/run_fixed_candidate_logp_audit_epoch46003_vs_46002.sh`
- score directory:
  `outputs/f3_only_mace_chgnet_matgl_consensus_64x80_before_after/fixed_candidate_logp_audit_64x80_seed20260514/logp_scores_epoch46003_vs_46002/`
- SLURM job: `102598`, `fiir-f3ep3-logp-audit`, `COMPLETED`, exit `0:0`,
  elapsed `00:00:38`, node `test001`, requested `gpu:rtx4090:2`.
- score rows: 1722, covering 861 fixed candidates x 2 checkpoints.
- 46003-vs-46002 median after-minus-before logp: stable `+25.0478`,
  unstable `-84341.25`, disagreement `-24775.55`.
- 46003-vs-46002 stable-minus-unstable delta gap: `+560338.35`.
- cumulative 46003-vs-46001 fixed-panel median deltas from the two logp audits:
  stable `+93.17`, unstable `-173380.06`, disagreement `-66843.56`, with
  stable-minus-unstable mean gap about `+1132656.92`.

Interpretation:

- The second epoch did not immediately reverse the fixed-panel likelihood
  signal. It continued to favor stable consensus candidates relative to
  unstable/disagreement candidates.
- The signal still looks more like suppressing unstable/disagreement sequences
  than broadly raising stable sequence likelihood across every formula panel.
- Do not train another epoch before a matched generation+MLIP validation gate
  for checkpoint 46003. A 64x20 or 64x40 proxy audit should decide whether
  epoch 46003 is actually better than checkpoint 46002 in generated outputs.

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

### Completed 64-Formula Before/After MLIP Consensus Gate

The larger matched before/after generation and three-MLIP offline-validation
gate completed through the project SLURM wrappers:

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
- completed generation jobs:
  - before shard 001: job `101278`, `fiir-dpo64-b1-m256`, completed at
    2026-05-14 02:32:59 CST, output root
    `outputs/dpo_strict3mlip_1024_before_after/before_64x20_seed20260513_shard_001`
  - before shard 002: job `101279`, `fiir-dpo64-b2-m256`, completed at
    2026-05-14 04:13:48 CST, output root
    `outputs/dpo_strict3mlip_1024_before_after/before_64x20_seed20260513_shard_002`
  - after shard 001: job `101280`, `fiir-dpo64-a1-m256`, completed at
    2026-05-14 04:03:52 CST, output root
    `outputs/dpo_strict3mlip_1024_before_after/after_64x20_seed20260513_shard_001`
  - after shard 002: job `101281`, `fiir-dpo64-a2-m256`, completed at
    2026-05-14 04:08:51 CST, output root
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
- completion summary: all four jobs ended with `CrystalFormer bulk generation
  orchestration complete`; all four stderr files are empty.
- aggregate 64x20 generation counts: 128/128 formulas completed, 2560
  candidates, 2560 DPO-eligible candidates, and 1619 generated
  geometry/chemistry preference pairs.
- before totals: 64 formulas, 1280 candidates, 1280 DPO eligible, 816 generated
  preference pairs, 40 F1 failures, 0 F2 failures, and 1280 F3-unknown
  candidates.
- after totals: 64 formulas, 1280 candidates, 1280 DPO eligible, 803 generated
  preference pairs, 37 F1 failures, 0 F2 failures, and 1280 F3-unknown
  candidates.
- combined local QA is now ready after root-scoping candidate IDs for matched
  before/after scans; the remaining 136 warnings are documented empty/zero-pair
  artifacts for formulas with no comparable margin. Combined collection now
  reports the expected 2560 candidates and 1619 preference pairs.
- optional follow-up if clean: 64 formulas x 40 samples
- execution policy: submit only through existing SLURM wrappers or project
  submit wrappers; do not run CrystalFormer generation, MLIP validation, DFT,
  or long evaluation on the login node.
- scheduler caveat: use normal GPU resource ranking first, and use flexible
  multi-partition queueing only when no eligible long-running GPU node has
  enough free resources; `test` remains limited to explicitly bounded jobs of
  30 minutes or less.
- matched 64x20 offline-validation batches are prepared under
  `outputs/mlip_validation_dpo_strict3mlip_1024_before_after_64x20_20260514_batch/`:
  before has 1240 selected candidates and after has 1243 selected candidates,
  using `before64__` and `after64__` candidate-id prefixes.
- submitted matched 64x20 MACE+CHGNet+MatGL relaxation jobs:
  - `101697`, `fiir-mace-dpo64-before`, `COMPLETED`, exit `0:0`
  - `101698`, `fiir-mace-dpo64-after`, `COMPLETED`, exit `0:0`
  - `101699`, `fiir-chgnet-dpo64-before`, `COMPLETED`, exit `0:0`
  - `101700`, `fiir-chgnet-dpo64-after`, `COMPLETED`, exit `0:0`
  - `101701`, `fiir-matgl-dpo64-before`, `COMPLETED`, exit `0:0`
  - `101702`, `fiir-matgl-dpo64-after`, `COMPLETED`, exit `0:0`
- offline-validation runbook and manifests:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/README.md`
  and
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/run_manifest_submitted.json`;
  final manifest:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/run_manifest_final.json`
- readiness summaries:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/readiness_before_summary.json`
  and
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_64x20_seed20260513/readiness_after_summary.json`
- strict three-MLIP consensus artifacts:
  - before:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_64x20_before_20260514/`
  - after:
    `outputs/mlip_validation_ensemble_mace_chgnet_matgl_relax_dpo_strict3mlip_1024_64x20_after_20260514/`
- final matched comparison:
  `outputs/dpo_strict3mlip_1024_before_after/offline_validation_comparison_64x20_seed20260513/`
- imported 64x20 comparison counts:
  - before: 1280 candidates, 1280 DPO eligible, F1 fail rate 0.03125, F2 fail
    rate 0.0, F3 available 807, stable consensus 456, unstable consensus 351,
    disagreement 433, all-three agreement rate 0.650806, stable consensus
    rate 0.35625, preference-pair yield 816
  - after: 1280 candidates, 1280 DPO eligible, F1 fail rate 0.02890625, F2
    fail rate 0.0, F3 available 805, stable consensus 456, unstable consensus
    349, disagreement 438, all-three agreement rate 0.647627, stable consensus
    rate 0.35625, preference-pair yield 803
  - deltas: stable consensus 0, stable consensus rate 0.0, F3 available -2,
    all-three agreement rate -0.00318, disagreement +5, F1 fail rate
    -0.00234, preference-pair yield -13
  - diversity/collapse signal: formula coverage remained 64 formulas, unique
    sequence fraction increased from 0.96875 to 0.971094, spacegroup count
    remained 75, and spacegroup entropy changed from 3.91662 to 3.91351.
  - proxy-divergence screen: flagged because the strict-consensus stable rate
    did not improve in the matched proxy audit.
- interpretation: the 64x20 matched proxy audit does not show a strict
  three-MLIP stable-rate improvement for the DPO after checkpoint. It is not a
  DFT-backed conclusion, but it is enough to avoid claiming DPO improvement
  from this checkpoint without additional evidence.
- formula-level diagnosis:
  `outputs/dpo_strict3mlip_1024_before_after/diagnostics_64x20_seed20260513/`
  with `summary.json`, `formula_deltas.jsonl`, and `report.md`.
- diagnosis highlights:
  - global delta: stable consensus 0, F3 available -2, disagreement +5,
    preference-pair yield -13, F1 failures -3.
  - largest stable-consensus losses: CaThO3 -3, PbZrO3 -3, SrCeO3 -3,
    BaSnO3 -2, CaCeO3 -2, CaTiO3 -2, DyScO3 -2, GdInO3 -2.
  - largest stable-consensus gains: BaHfO3 +4, HoScO3 +3, SmGaO3 +3,
    BaZrO3 +2, CaZrO3 +2, DyInO3 +2, PrInO3 +2, SmScO3 +2.
  - largest F3-available losses: LaScO3 -4, CaThO3 -3, PbThO3 -3,
    SrCeO3 -3.
  - largest preference-pair losses: BaSnO3 -19, BaThO3 -19, BaZrO3 -19,
    PbGeO3 -19, PrGaO3 -19, SrThO3 -19.
- diagnosis recommendation: do not retrain from the same geometry/chemistry-only
  signal unchanged. Build a revised DPO data artifact emphasizing
  high-agreement stable-vs-unstable MLIP consensus pairs and reducing zero or
  low-margin geometry-only pair sources.
- evidence caveat: the completed 10x20 smoke and 64x20 gate are MLIP
  relaxation consensus proxy evidence, not DFT evidence and not
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

Do not claim a finished performance improvement yet, but checkpoint 46003 is
now the current strongest bounded MLIP-proxy candidate. The immediate next
step is to wait for the formula-holdout audit jobs 106115-106126 and compare
original versus 46003 on formulas that were not used for F3 pair mining. If the
holdout audit also improves strict stable consensus, F3 availability, average
stable vote fraction, force summaries, and F1/unique/diversity diagnostics,
then checkpoint 46003 becomes a much stronger no-DFT generalization candidate.
The evidence remains MLIP relaxation proxy and model-likelihood evidence, not
DFT or hull-confirmed stability.
