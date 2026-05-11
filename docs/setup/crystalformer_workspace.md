# CrystalFormer Workspace Setup

FIIR Crystal treats `deepmodeling/CrystalFormer` as a managed external
workspace. CrystalFormer, JAX, torch, ASE, pymatgen, checkpoints, and generated
outputs stay outside the `fiir_crystal` core runtime dependency set.

## Recommended Layout

```text
fiir-crystal/
  fiir_crystal/
  external/CrystalFormer/
  external/checkpoints/
  outputs/crystalformer_raw/
  outputs/crystalformer_run/
  outputs/crystalformer_audit/
  outputs/dpo_preferences/
```

`external/checkpoints/` is for local model checkpoints. `outputs/` directories
are local run artifacts. Checkpoints and outputs are not committed to git.

## Local Clone Mode

Use this when you only need to run upstream CrystalFormer locally and do not
plan to modify its code as part of this repository:

```bash
mkdir -p external
git clone https://github.com/deepmodeling/CrystalFormer external/CrystalFormer
```

If `external/CrystalFormer/` is a plain local clone, it is reasonable to ignore
the entire directory in your local git excludes. The repository `.gitignore`
only ignores heavy generated subdirectories so that a submodule can still be
tracked if you choose that mode.

## Fork Or Submodule Mode

Use this when you expect to modify CrystalFormer training code later, for
example for DPO training:

```bash
git submodule add <your-fork-or-upstream-url> external/CrystalFormer
git submodule update --init --recursive
```

For future DPO work, prefer a fork recorded as a submodule. Avoid editing an
upstream clone without recording a branch. Keep checkpoints out of git. Keep
CrystalFormer outputs out of git.

## CrystalFormer Environment

Create a separate environment inside the CrystalFormer workspace:

```bash
cd external/CrystalFormer
conda create -n crystalformer python=3.10
conda activate crystalformer
pip install -U "jax[cpu]"
pip install .
```

For GPU runs, follow the JAX/CUDA installation instructions that match the
local driver and CUDA version. FIIR Crystal does not install CUDA packages or
manage the CrystalFormer environment.

## Small Batch Generation Example

Run this from `external/CrystalFormer` after placing a checkpoint under
`../checkpoints/crystalformer`:

```bash
python ./main.py \
  --optimizer none \
  --restore_path ../checkpoints/crystalformer \
  --K 40 \
  --num_samples 100 \
  --formula BaTiO3 \
  --save_path ../../outputs/crystalformer_raw/BaTiO3
```

This is only a small local generation example. It is not FIIR training, not DPO
training, not DFT, and not MLFF relaxation.

## awl2struct Conversion Example

Run this from `external/CrystalFormer` to convert AWL-style output into struct
CSV files:

```bash
python ./scripts/awl2struct.py \
  --output_path ../../outputs/crystalformer_raw/BaTiO3 \
  --formula BaTiO3
```

The FIIR adapter keeps raw `g` / `W` / `A` / `X` / `L` sequence fields whenever
they are available, because later DPO preference pairs need CrystalFormer-native
sequence information.

## FIIR Smoke Audit Example

Return to the FIIR Crystal repository root and audit the generated files:

```bash
python scripts/audit_crystalformer_outputs.py \
  --input-dir outputs/crystalformer_raw/BaTiO3 \
  --formula BaTiO3 \
  --output-dir outputs/crystalformer_audit/BaTiO3 \
  --parser-backend none \
  --stability-mode unavailable_without_offline_validation
```

The audit writes normalized candidates, failure vectors, per-candidate audit
records, and a Markdown report. Without imported offline validation, F3 is
reported as unknown/unavailable and no candidate is reported as stable.
