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
