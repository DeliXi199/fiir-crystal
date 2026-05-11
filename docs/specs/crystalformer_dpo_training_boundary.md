# CrystalFormer DPO Training Boundary

This document defines the handoff boundary between FIIR Crystal preference
artifacts and future external CrystalFormer DPO training. FIIR Crystal does not
implement DPO training and does not add CrystalFormer, JAX, torch, pymatgen, or
ASE to core dependencies.

## Scope

The boundary can:

- validate a `preference_pairs.jsonl` artifact;
- check whether `external/CrystalFormer` is missing, a normal clone, or
  submodule-like;
- write `trainer_manifest.json`;
- write a Markdown readiness report;
- optionally execute an explicit external command only when `--run-training`
  is provided.

The boundary cannot:

- implement a DPO loss;
- import JAX or torch;
- install dependencies;
- clone CrystalFormer;
- download checkpoints or datasets;
- run DFT, MLIP, Materials Project, or other external APIs.

## Manifest

`trainer_manifest.json` is a local handoff artifact for a future CrystalFormer
fork/submodule. It includes:

- preference pair path and SHA256;
- pair counts and validation summary;
- preference type breakdown;
- CrystalFormer workspace state;
- checkpoint directory path;
- optional external training command string;
- explicit notes that training happens outside FIIR.

## Readiness Rules

The boundary blocks readiness when:

- the preference file is missing;
- no preference pairs are available;
- any pair is schema-invalid;
- the CrystalFormer workspace is missing and workspace presence is required;
- submodule mode is required but not detected.

Pair validation checks:

- required ids and condition fields;
- positive preference margin;
- chosen score no worse than rejected score;
- full `g` / `W` / `A` / `X` / `L` sequences on both sides;
- supported preference type;
- F3 evidence on both sides for `stability_aware_offline_validation`.

## Explicit Command Boundary

The CLI defaults to manifest/report generation only. It never executes the
provided command unless `--run-training` is also present.

```bash
python scripts/prepare_crystalformer_dpo_training_boundary.py \
  --preference-pairs-jsonl outputs/crystalformer_smoke_fake_validated/dpo_preferences/BaTiO3/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_training_boundary/BaTiO3 \
  --crystalformer-work-dir external/CrystalFormer \
  --training-command "python ./train_dpo.py --manifest ../../outputs/crystalformer_dpo_training_boundary/BaTiO3/trainer_manifest.json"
```

To execute the external command, add `--run-training`. This should only be used
from a prepared CrystalFormer environment or fork/submodule. FIIR records
stdout, stderr, return code, cwd, and command in
`training_command_provenance.json`.
