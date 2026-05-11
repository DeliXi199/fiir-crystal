# CrystalFormer DPO Data Schema

This document defines the future preference-pair payload for CrystalFormer DPO
data. This stage does not train CrystalFormer and does not build a large DPO
dataset. It only preserves raw sequence fields and marks audit candidates for
DPO eligibility.

## Pair Schema

```json
{
  "pair_id": "...",
  "condition": {
    "mode": "csp",
    "formula": "BaTiO3",
    "spacegroup": null
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
- Each side must retain CrystalFormer-native `g` / `W` / `A` / `X` / `L`
  fields, or an explicitly documented equivalent raw sequence representation.
- Without F3 validation, only `geometry_chemistry_only` preferences may be
  constructed.
- Stability preferences require imported offline validation, MLFF relaxation
  results, or DFT results. The smoke audit must not claim stability
  optimization.

## Current Stage

The current implementation writes `dpo_eligible` and
`dpo_ineligible_reasons` into the CrystalFormer smoke audit. The next stage is
a preference-pair builder that consumes audit outputs and writes the schema
above. DPO training is explicitly out of scope for this stage.
