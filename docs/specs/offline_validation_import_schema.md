# Offline Validation Import Schema

This schema describes local validation results that were produced outside FIIR
Crystal and can be imported into a CrystalFormer smoke audit. This stage does
not run DFT, MLIP, Materials Project, or any external API. It only reads local
JSONL evidence.

## Record Schema

```json
{
  "candidate_id": "cf_fake_good_001",
  "formula": "BaTiO3",
  "condition": {
    "mode": "csp",
    "formula": "BaTiO3",
    "spacegroup": null,
    "generation": {
      "source_checkpoint": "local-checkpoint-id",
      "temperature": "1.0",
      "top_k": "40",
      "K": "40"
    }
  },
  "validation_source": "offline_dft",
  "validation_status": "completed",
  "is_stable": true,
  "e_above_hull": 0.01,
  "relaxed_structure_ref": "local/path/to/relaxed.cif",
  "error_reason": null,
  "metadata": {}
}
```

## Required Fields

- `candidate_id`
- `formula`
- `validation_source`

`condition.generation` should be provided whenever CrystalFormer sampling
settings are known. FIIR matches validation rows to audit candidates by
candidate id, formula, optional spacegroup, and generation condition. Mismatches
are skipped and counted.

## Status Rules

- Successful rows use `validation_status` values such as `completed`,
  `success`, `succeeded`, or `validated`.
- Failed rows should set `validation_status` to `failed` or `error`, or provide
  `error_reason`.
- A failed validation row may be attached as evidence, but it does not make F3
  available and must not create a stability-aware preference.
- If `is_stable` is omitted, FIIR can infer it from `e_above_hull` using the
  local import threshold. This is still imported evidence, not a calculation
  performed by FIIR.

## DPO Boundary

Without imported offline validation, preference pairs remain
`geometry_chemistry_only`. When both sides of a same-condition pair have
successful imported F3 evidence, the preference builder may emit
`stability_aware_offline_validation`.

This is still data preparation only. No DPO trainer is run in this phase.
