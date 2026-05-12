# CrystalFormer DPO Data Schema

This document defines the preference-pair payload for CrystalFormer DPO data.
This stage can build small schema-valid preference-pair files from FIIR audit
outputs. It does not train CrystalFormer and does not build a large DPO
dataset.

## Pair Schema

```json
{
  "pair_id": "...",
  "condition": {
    "mode": "csp",
    "formula": "BaTiO3",
    "spacegroup": null,
    "generation": {
      "source_checkpoint": "...",
      "temperature": "...",
      "top_k": "..."
    }
  },
  "chosen_candidate_id": "...",
  "rejected_candidate_id": "...",
  "chosen_sequence": {
    "g": "...",
    "W": "...",
    "A": "...",
    "X": "...",
    "L": "..."
  },
  "rejected_sequence": {
    "g": "...",
    "W": "...",
    "A": "...",
    "X": "...",
    "L": "..."
  },
  "chosen_score": 0.0,
  "rejected_score": 0.0,
  "preference_margin": 0.0,
  "preference_type": "geometry_chemistry_only",
  "preference_reason": [],
  "chosen_failure_vector": {},
  "rejected_failure_vector": {},
  "metadata": {}
}
```

## Boundary Rules

- DPO pairs must come from the same formula and the same generation condition.
- Do not pair candidates across formulas.
- If a spacegroup condition is specified, both candidates must come from that
  same spacegroup condition.
- Generation condition fields are provenance keys such as checkpoint,
  temperature, and top-k/K sampling settings. If present, they must match.
- Each side must retain CrystalFormer-native `g` / `W` / `A` / `X` / `L`
  fields, or an explicitly documented equivalent raw sequence representation.
- Without F3 validation, only `geometry_chemistry_only` preferences may be
  constructed.
- When both sides have successful imported offline validation evidence, the
  preference type may be `stability_aware_offline_validation`.
- If only one side has imported F3 evidence, the pair is skipped and counted as
  `mixed_f3_validation_availability`.
- Stability preferences require imported offline validation, MLFF relaxation
  results, or DFT results. The smoke audit must not claim stability
  optimization.

## Current Stage

The current implementation writes `dpo_eligible` and
`dpo_ineligible_reasons` into the CrystalFormer smoke audit, then the
preference builder can consume `audit_candidates.jsonl` and emit
`preference_pairs.jsonl` using the schema above.

If all eligible candidates have equal FIIR scores or no comparable margin, the
builder emits zero pairs and records `no_comparable_margin` in the summary
rather than fabricating preferences. DPO training is explicitly out of scope
for this stage.

The smoke-run preparer can additionally materialize a non-overwriting external
training handoff:

- `chosen_sequences.jsonl`
- `rejected_sequences.jsonl`
- `pair_index.jsonl`
- `dpo_smoke_manifest.json`
- `run_training.sh`

Each sequence JSONL row contains parsed native CrystalFormer `g`, `L`, `X`,
`A`, and `W` arrays. The recommended command must use the base checkpoint only
as `--restore_path` and must write any after checkpoint under a separate
`--folder` output root. The smoke-run preparer records both the restored epoch
and target epoch; its `--epochs` option is additional epochs from the latest
base checkpoint, not permission to overwrite that checkpoint.

If the generated command is executed, it must happen in the external
CrystalFormer environment on an allocated compute node, for example through
`scripts/slurm/run_crystalformer_dpo_smoke.slurm`. FIIR still does not execute
DPO training as part of the core package.
