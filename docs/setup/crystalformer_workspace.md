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

## Recommended Phase A Workflow

This phase is the real-smoke integration layer, not DPO training:

1. Check the external workspace.
2. Run CrystalFormer externally, or point FIIR at already existing raw outputs.
3. Run the FIIR smoke pipeline.
4. Inspect the audit artifacts.
5. Inspect the DPO preference artifact.

Future real training belongs to a later phase: a CrystalFormer fork/submodule,
a trainer adapter boundary, and DPO loss integration inside that external
workspace. FIIR Crystal core remains standard-library only.

## Readiness Check

Run this from the FIIR Crystal repository root:

```bash
python scripts/check_crystalformer_workspace.py --output-dir outputs/workspace_check
```

The check is local-only. It reports whether `external/CrystalFormer` is missing,
a normal clone, or submodule-like; whether `external/checkpoints` exists; and
whether the local output directories exist. It does not clone, install,
download, or modify CrystalFormer.

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

Run this from `external/CrystalFormer` after placing a checkpoint directory
with direct `*.pkl` files under `../checkpoints/crystalformer/alex20s_csp`:

```bash
mkdir -p ../../outputs/crystalformer_raw/BaTiO3
python ./main.py \
  --optimizer none \
  --restore_path ../checkpoints/crystalformer/alex20s_csp \
  --K 40 \
  --num_samples 100 \
  --formula BaTiO3 \
  --save_path ../../outputs/crystalformer_raw/BaTiO3/output.csv
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

## Real-Smoke Pipeline

Load-only mode reads existing raw outputs and is the default:

```bash
python scripts/run_crystalformer_smoke_pipeline.py \
  --input-dir outputs/crystalformer_raw/BaTiO3 \
  --formula BaTiO3 \
  --output-root outputs \
  --parser-backend none \
  --stability-mode unavailable_without_offline_validation
```

The pipeline writes:

- `outputs/crystalformer_audit/BaTiO3/`
- `outputs/dpo_preferences/BaTiO3/`
- `outputs/crystalformer_smoke_pipeline/BaTiO3/provenance.json`
- `outputs/crystalformer_smoke_pipeline/BaTiO3/pipeline_summary.json`
- `outputs/crystalformer_smoke_pipeline/BaTiO3/report.md`

For an end-to-end local fake fixture:

```bash
python scripts/run_crystalformer_smoke_pipeline.py \
  --input-dir examples/crystalformer_raw/BaTiO3_fake \
  --formula BaTiO3 \
  --output-root outputs/crystalformer_smoke_fake \
  --parser-backend none \
  --stability-mode unavailable_without_offline_validation
```

To import already-computed local validation evidence, first check the join:

```bash
python scripts/check_offline_validation_import.py \
  --audit-candidates-jsonl outputs/crystalformer_smoke_fake/crystalformer_audit/BaTiO3/audit_candidates.jsonl \
  --validation-jsonl examples/crystalformer_validation/BaTiO3_fake_validation.jsonl \
  --output-dir outputs/validation_import_check_fake
```

Then pass the validation JSONL to the smoke pipeline:

```bash
python scripts/run_crystalformer_smoke_pipeline.py \
  --input-dir examples/crystalformer_raw/BaTiO3_fake \
  --formula BaTiO3 \
  --output-root outputs/crystalformer_smoke_fake_validated \
  --parser-backend none \
  --stability-mode unavailable_without_offline_validation \
  --offline-validation-jsonl examples/crystalformer_validation/BaTiO3_fake_validation.jsonl
```

Validation import remains local-only. Rows must match candidate id, formula,
optional spacegroup, and generation condition. Failed validation rows and
mismatches are reported but do not make F3 available.

Explicit-command mode is opt-in. The subprocess is executed only when
`--run-generation` is present:

```bash
python scripts/run_crystalformer_smoke_pipeline.py \
  --input-dir outputs/crystalformer_raw/BaTiO3 \
  --formula BaTiO3 \
  --crystalformer-work-dir external/CrystalFormer \
  --crystalformer-command "python ./main.py ..." \
  --run-generation
```

The command, cwd, stdout, stderr, and return code are written to provenance JSON.
If the command or workdir is missing, the pipeline exits with a clear error.
Without imported offline validation, F3 is reported as unavailable/unknown and
no candidate is reported as stable.

## Bulk Generation Orchestration

After one formula works, prepare a bulk dry-run:

```bash
python scripts/run_crystalformer_bulk_generation.py \
  --config configs/crystalformer_bulk_generation.json \
  --output-root outputs/crystalformer_bulk_fake
```

Validate the real-command template before submitting work to a test node:

```bash
python scripts/run_crystalformer_bulk_generation.py \
  --config configs/crystalformer_bulk_generation.real.example.json \
  --output-root outputs/crystalformer_bulk_real_validate \
  --validate-only
```

This expands commands, checks `external/CrystalFormer`, checks a referenced
checkpoint directory such as `external/checkpoints/crystalformer/alex20s_csp`,
checks for direct `*.pkl` checkpoint files, and writes
`bulk_validation_summary.json`. Missing paths or checkpoint files are reported
as blocking readiness issues. Validate-only never runs CrystalFormer and never
enters the smoke pipeline.

Then run a small explicit generation batch:

```bash
python scripts/run_crystalformer_bulk_generation.py \
  --config configs/crystalformer_bulk_generation.real.example.json \
  --output-root outputs/crystalformer_bulk_real_smoke \
  --run-generation
```

If the 5-sample run succeeds, the next conservative scale-up is the 20-sample
BaTiO3 template:

```bash
FIIR_CONDA_ENV=crystalformer \
FIIR_RUN_GENERATION=1 \
FIIR_ONLY_FORMULA=BaTiO3 \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real_batio3_n20.example.json \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke_BaTiO3_n20 \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

Then check multi-formula behavior with the 3x20 perovskite template:

```bash
FIIR_CONDA_ENV=crystalformer \
FIIR_RUN_GENERATION=1 \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real_perovskite_3x20.example.json \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke_perovskite_3x20 \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

Once that passes, the next small batch is 10 perovskite-like formulas x 20
samples:

```bash
FIIR_CONDA_ENV=crystalformer \
FIIR_RUN_GENERATION=1 \
FIIR_CONTINUE_ON_ERROR=1 \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real_perovskite_10x20.example.json \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke_perovskite_10x20 \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

For a longer smoke that should occupy a test node for roughly 25 minutes, use
10 formulas x 400 samples:

```bash
FIIR_CONDA_ENV=crystalformer \
FIIR_RUN_GENERATION=1 \
FIIR_CONTINUE_ON_ERROR=1 \
FIIR_EXPECTED_MINUTES=25 \
FIIR_SKIP_EXISTING_MODE=no-skip \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real_perovskite_10x400.example.json \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke_perovskite_10x400 \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

For a roughly three-hour, broader formula sweep, use 32 formulas x 1600 samples.
This produces 51200 generated structures. Cap generation concurrency at 16 so
the job uses one node fully without launching 32 CrystalFormer/JAX processes at
once:

```bash
FIIR_CONDA_ENV=crystalformer \
FIIR_RUN_GENERATION=1 \
FIIR_CONTINUE_ON_ERROR=1 \
FIIR_EXPECTED_MINUTES=180 \
FIIR_TIME_LIMIT=04:00:00 \
FIIR_SKIP_EXISTING_MODE=no-skip \
FIIR_MAX_CONCURRENT_GENERATIONS=16 \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real_perovskite_32x1600_3h.example.json \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke_perovskite_32x1600_3h \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

With `FIIR_GENERATION_CPU_THREADS=auto`, the runner divides the available node
cores across the 16 subprocesses: 4 threads each on 64-core nodes, or a 3/4
thread mix on `regular`'s 56 cores.

For multi-node generation, submit independent one-node shards. The checked-in
128-formula bank and generated shard configs are:

```text
configs/formula_banks/perovskite_128.json
configs/generated/crystalformer_shards/perovskite_128_32x1600/shard_001.json
configs/generated/crystalformer_shards/perovskite_128_32x1600/shard_002.json
configs/generated/crystalformer_shards/perovskite_128_32x1600/shard_003.json
configs/generated/crystalformer_shards/perovskite_128_32x1600/shard_004.json
```

Each shard is `32 formulas x 1600 samples = 51200` generated structures.
Submitting all four shards produces 204800 structures and can use up to four
nodes concurrently:

```bash
for shard in configs/generated/crystalformer_shards/perovskite_128_32x1600/shard_[0-9][0-9][0-9].json; do
  name="$(basename "${shard}" .json)"
  FIIR_CONDA_ENV=crystalformer \
  FIIR_RUN_GENERATION=1 \
  FIIR_CONTINUE_ON_ERROR=1 \
  FIIR_EXPECTED_MINUTES=180 \
  FIIR_TIME_LIMIT=04:00:00 \
  FIIR_SKIP_EXISTING_MODE=no-skip \
  FIIR_MAX_CONCURRENT_GENERATIONS=16 \
  FIIR_BULK_CONFIG="${shard}" \
  FIIR_OUTPUT_ROOT="outputs/crystalformer_bulk_real_smoke_perovskite_128_32x1600_${name}" \
  bash scripts/slurm/submit_crystalformer_bulk.sh
done
```

Regenerate the shard configs from the formula bank with:

```bash
python scripts/make_crystalformer_bulk_shards.py \
  --formula-bank configs/formula_banks/perovskite_128.json \
  --formulas-per-shard 32 \
  --num-samples 1600 \
  --top-k 40 \
  --output-dir configs/generated/crystalformer_shards/perovskite_128_32x1600 \
  --output-root-prefix outputs/crystalformer_bulk_real_smoke_perovskite_128_32x1600
```

For longer generation jobs, watch only the startup window with the SLURM
monitor:

```bash
scripts/slurm/monitor_slurm_startup.sh --job-id <job-id>
```

Use the default 120-second window for stable long jobs. Use
`--seconds 300` for a new template, new environment, or new scale. The monitor
checks `squeue`, stdout, and stderr under `logs/slurm/`; if the job is still
listed and stderr is empty after that startup window, leave it to finish under
SLURM and inspect `bulk_summary.json` afterward.

By default, the SLURM wrapper passes `FIIR_TOTAL_CPU_CORES=$ncpu` to the bulk
runner. The runner uses that budget for formula-level concurrency plus
per-process CPU threading. For example, a 64-core node with three formulas
gets three concurrent CrystalFormer subprocesses with thread allocations like
`22, 21, 21`. Override this only when needed with
`FIIR_MAX_CONCURRENT_GENERATIONS` or `FIIR_GENERATION_CPU_THREADS`.
`bulk_summary.json` records wall time, total generation seconds, total smoke
seconds, and formula-level duration statistics.

The recommended submitter is `scripts/slurm/submit_crystalformer_bulk.sh`. It
uses `test` for jobs expected within 30 minutes when an idle test node exists;
otherwise it checks `regular256`, `regular128`, `regular6430`, `regular`, then
`test`. If no idle node exists, it queues on all listed partitions. It requests
one exclusive node and lets the runner use 56 cores on `regular` or 64 cores on
the other CPU partitions. SLURM stdout/stderr files are collected under
`logs/slurm/` by default. If `sinfo` displays `regular256*`, the `*` only marks
the default partition; the actual partition name is `regular256`.

The default checked-in config uses a fake stdlib-only generator. The real
example config keeps `num_samples` small and assumes a prepared external
CrystalFormer workspace plus checkpoint. Use `--only-formula BaTiO3` for a
single formula, `--no-skip-existing` to force regeneration, and
`--continue-on-error` only when you want later formulas to run after a failure.

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

## DPO Training Boundary Manifest

After a validated smoke run has produced `preference_pairs.jsonl`, prepare a
handoff manifest for external CrystalFormer training:

```bash
python scripts/prepare_crystalformer_dpo_training_boundary.py \
  --preference-pairs-jsonl outputs/crystalformer_smoke_fake_validated/dpo_preferences/BaTiO3/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_training_boundary/BaTiO3 \
  --crystalformer-work-dir external/CrystalFormer
```

This validates the preference schema and writes:

- `trainer_manifest.json`
- `training_boundary_summary.json`
- `training_command_provenance.json`
- `report.md`

The CLI does not run training by default. If a `--training-command` is supplied,
it is recorded in the manifest and provenance. It is only executed when
`--run-training` is also present. For real DPO work, prefer a CrystalFormer
fork/submodule so trainer changes and DPO loss integration are tracked outside
FIIR Crystal core.
