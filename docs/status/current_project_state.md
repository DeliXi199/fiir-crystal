# Current Project State

Last updated: 2026-05-12, Asia/Shanghai.

This file is the compact project memory for future Codex sessions. Read it
after `AGENTS.md` and before making roadmap, experiment, or implementation
decisions.

## Current Stage

- FIIR Crystal has a local-first scaffold, mock loop, CrystalFormer adapter,
  bulk orchestration, offline validation import boundary, comparison reports,
  active-loop simulation, and CrystalFormer DPO handoff boundary.
- The repository should not run real DPO training, DFT, MLIP execution, or
  external model installation inside the core `fiir_crystal` package.
- Current best next step: implement/use the external CrystalFormer-side DPO
  training adapter or fork/submodule, using the 284 stability-aware preference
  pairs listed below.

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

### Existing CrystalFormer / MACE Evidence

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

### Current DPO Preference Artifact

The current best DPO preference artifact is:

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

Implement or use a CrystalFormer-side DPO training adapter in a recorded fork or
submodule. Use the 284 stability-aware pairs above as the initial external
training handoff. Keep training outside FIIR core and preserve provenance.
