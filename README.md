# FIIR Crystal

FIIR Crystal is a lightweight, local-first framework for testing
Failure-Informed Iterative Refinement data flow for crystal generation. The
current stage is an engineering scaffold and mock experiment runner, not a real
materials-discovery stack.

The package intentionally does not run heavy external workflows:

- no deep learning training implementation;
- no DFT execution;
- no MLIP execution;
- no Materials Project, CSLLM, ICSD, GNoME, or other external API calls;
- no dataset downloads.

## Current Status

Implemented today:

- `StructureLike` / `CrystalRecord` mock candidate model.
- Stdlib-only `CrystalStructureRecord` for real external generator outputs.
- Lightweight F1/F2/F3 `FailureOracle`.
- Matched axis-aligned preference pairs.
- Baseline pair modes: `axis_aligned`, `weighted_sum`, `random_negative`, `binary_success_failure`.
- Evaluation reports with failure, pair, and ranking metrics.
- Mock discovery ranking with `utility` and lightweight `pareto` modes.
- JSONL/JSON I/O for candidates, failure vectors, pairs, reports, ranking, feedback, and summaries.
- Configurable experiment runner and Markdown report generation.
- Pair mode comparison across `axis_aligned`, `weighted_sum`, `random_negative`, and `binary_success_failure`.
- Multi-run experiment aggregation from existing output directories.
- Offline validation result JSONL import and validation-aware metrics.
- Mock feedback buffer and multi-round active discovery loop simulation.
- External generator adapter boundary plus a first CrystalFormer output adapter
  for `deepmodeling/CrystalFormer` outputs.
- CrystalFormer real-smoke integration pipeline that connects local raw outputs
  to audit artifacts and schema-first DPO preference artifacts.
- Offline validation import boundary for CrystalFormer smoke audits, including
  validation-aware F3 labels and stability-aware preference artifacts when
  local evidence is available.

## Install

```bash
python -m pip install -e ".[dev]"
```

The core package uses the Python standard library only. `pytest` is the only
development test dependency.

## Run The Original Mock Loop

```bash
python scripts/run_mock_fiir_loop.py
```

This prints the in-memory closed loop: mock candidates, `FailureOracle` vectors,
matched pairs, evaluation report, discovery ranking, and feedback records.

## Run A Configured Experiment

```bash
python scripts/run_fiir_experiment.py --config configs/mock_fiir_loop.yaml
```

Useful overrides:

```bash
python scripts/run_fiir_experiment.py \
  --config configs/mock_fiir_loop.yaml \
  --input examples/mock_candidates.jsonl \
  --output-dir outputs/mock_run \
  --pair-mode axis_aligned \
  --top-k 5
```

Optional offline validation import:

```bash
python scripts/run_fiir_experiment.py \
  --config configs/mock_fiir_loop.yaml \
  --validation examples/mock_validation_results.jsonl
```

## Compare Pair Modes

```bash
python scripts/compare_pair_modes.py --config configs/mock_fiir_loop.yaml
```

With offline validation metrics:

```bash
python scripts/compare_pair_modes.py \
  --config configs/mock_fiir_loop.yaml \
  --validation examples/mock_validation_results.jsonl
```

## Aggregate Existing Runs

```bash
python scripts/compare_experiments.py \
  --runs outputs/pair_mode_comparison/axis_aligned outputs/pair_mode_comparison/weighted_sum \
  --output-dir outputs/aggregate_report
```

## Run A Mock Active Loop

```bash
python scripts/run_mock_active_loop.py \
  --config configs/mock_fiir_loop.yaml \
  --validation examples/mock_validation_results.jsonl \
  --rounds 2
```

## Normalize CrystalFormer Outputs

FIIR Crystal can read outputs produced by the external
`deepmodeling/CrystalFormer` project and convert them into standard
`CrystalStructureRecord` JSONL candidates:

```bash
python scripts/run_crystalformer_adapter.py \
  --config configs/crystalformer_adapter.yaml \
  --output-dir outputs/crystalformer_run
```

By default this is load-only: it reads an existing output directory configured
under `generation.output_dir`, writes `candidates.jsonl`, then runs the
lightweight FIIR failure/ranking/report flow in `fiir_run/`.

An optional subprocess mode is available only when the user supplies the exact
command:

```bash
python scripts/run_crystalformer_adapter.py \
  --config configs/crystalformer_adapter.yaml \
  --run-generation
```

FIIR Crystal does not clone CrystalFormer, install its dependencies, download
checkpoints, download datasets, train CrystalFormer, run DFT, run MLIP, or call
Materials Project or other external APIs. CrystalFormer outputs are candidate
structures only; they are not relaxed stable materials. F3 stability remains
unavailable or low-confidence unless offline validation, MLIP relaxation, or DFT
results are imported.

## CrystalFormer Workspace

Use `deepmodeling/CrystalFormer` as an external workspace under
`external/CrystalFormer/`. It may be a local clone for load-only generation
runs, or a fork/submodule if later DPO training code changes need to be tracked.
Checkpoints go under `external/checkpoints/`; generated files go under
`outputs/crystalformer_raw/`, `outputs/crystalformer_run/`, and
`outputs/crystalformer_audit/`. These artifacts are ignored by git.

See `docs/setup/crystalformer_workspace.md` for clone/submodule commands and
environment guidance. CrystalFormer, JAX, torch, pymatgen, and ASE are not core
runtime dependencies of `fiir_crystal`; the core package remains stdlib-only.

Check the local workspace without cloning, installing, or downloading anything:

```bash
python scripts/check_crystalformer_workspace.py --output-dir outputs/workspace_check
```

This writes `workspace_check.json` and `workspace_check.md`, checks whether
`external/CrystalFormer` is missing, a normal clone, or submodule-like, and can
create the FIIR output directories if they are absent.

## CrystalFormer Real-Smoke Pipeline

The recommended workflow for this phase is:

1. Check the external workspace.
2. Run CrystalFormer externally or point FIIR at already existing raw outputs.
3. Run the smoke pipeline.
4. Inspect the audit artifacts.
5. Build and inspect the DPO preference artifact.

Load-only mode is the default and is safe for local tests:

```bash
python scripts/run_crystalformer_smoke_pipeline.py \
  --input-dir examples/crystalformer_raw/BaTiO3_fake \
  --formula BaTiO3 \
  --output-root outputs/crystalformer_smoke_fake \
  --parser-backend none \
  --stability-mode unavailable_without_offline_validation
```

This writes audit artifacts under
`outputs/crystalformer_smoke_fake/crystalformer_audit/BaTiO3/`, DPO preference
artifacts under
`outputs/crystalformer_smoke_fake/dpo_preferences/BaTiO3/`, and pipeline
provenance/report files under
`outputs/crystalformer_smoke_fake/crystalformer_smoke_pipeline/BaTiO3/`.

Explicit-command mode is opt-in. FIIR only runs the command when
`--run-generation` is present:

```bash
python scripts/run_crystalformer_smoke_pipeline.py \
  --input-dir outputs/crystalformer_raw/BaTiO3 \
  --formula BaTiO3 \
  --crystalformer-work-dir external/CrystalFormer \
  --crystalformer-command "python ./main.py ..." \
  --run-generation
```

The subprocess command, cwd, stdout, stderr, and return code are recorded in
`provenance.json` before audit and DPO artifact construction continues. If F3
offline validation is not imported, F3 is explicitly unavailable/unknown and no
candidate is reported as stable.

Optional offline validation import reads local JSONL evidence only:

```bash
python scripts/check_offline_validation_import.py \
  --audit-candidates-jsonl outputs/crystalformer_smoke_fake/crystalformer_audit/BaTiO3/audit_candidates.jsonl \
  --validation-jsonl examples/crystalformer_validation/BaTiO3_fake_validation.jsonl \
  --output-dir outputs/validation_import_check_fake

python scripts/run_crystalformer_smoke_pipeline.py \
  --input-dir examples/crystalformer_raw/BaTiO3_fake \
  --formula BaTiO3 \
  --output-root outputs/crystalformer_smoke_fake_validated \
  --parser-backend none \
  --stability-mode unavailable_without_offline_validation \
  --offline-validation-jsonl examples/crystalformer_validation/BaTiO3_fake_validation.jsonl
```

Validation rows are matched by candidate id, formula, optional spacegroup, and
generation condition. Failed or mismatched rows are counted in the import
summary and do not make F3 available. This is still not DFT, not MLIP, and not
DPO training.

## CrystalFormer Bulk Generation

Bulk orchestration is for existing-checkpoint CrystalFormer generation. It
plans one explicit command per formula and can route each completed formula
through the smoke pipeline. It is not DPO training.

Dry-run is the default:

```bash
python scripts/run_crystalformer_bulk_generation.py \
  --config configs/crystalformer_bulk_generation.json \
  --output-root outputs/crystalformer_bulk_fake
```

Validate a real-command template before submitting generation:

```bash
python scripts/run_crystalformer_bulk_generation.py \
  --config configs/crystalformer_bulk_generation.real.example.json \
  --output-root outputs/crystalformer_bulk_real_validate \
  --validate-only
```

Validate-only writes `bulk_plan.json`, `bulk_validation_summary.json`, and
`validate_report.md`. Missing `external/CrystalFormer` or a referenced
checkpoint directory is reported as a blocking readiness issue, but no
CrystalFormer command or smoke audit is run.

Run generation only when explicitly requested:

```bash
python scripts/run_crystalformer_bulk_generation.py \
  --config configs/crystalformer_bulk_generation.real.example.json \
  --output-root outputs/crystalformer_bulk_real_smoke \
  --run-generation
```

After the 5-sample smoke succeeds, use the checked-in 20-sample BaTiO3
template to verify that preference artifacts become non-empty before moving to
larger batches:

```bash
FIIR_CONDA_ENV=crystalformer \
FIIR_RUN_GENERATION=1 \
FIIR_ONLY_FORMULA=BaTiO3 \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real_batio3_n20.example.json \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke_BaTiO3_n20 \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

After that, use the 3-formula perovskite template to verify bulk behavior
across formula boundaries:

```bash
FIIR_CONDA_ENV=crystalformer \
FIIR_RUN_GENERATION=1 \
FIIR_BULK_CONFIG=configs/crystalformer_bulk_generation.real_perovskite_3x20.example.json \
FIIR_OUTPUT_ROOT=outputs/crystalformer_bulk_real_smoke_perovskite_3x20 \
bash scripts/slurm/submit_crystalformer_bulk.sh
```

The SLURM template now passes the full node CPU budget to the runner. With
`--run-generation`, the runner automatically runs formulas concurrently and
assigns CPU threads to each CrystalFormer subprocess. On the 64-core test node,
the 3x20 template runs three CrystalFormer commands at once with thread
allocations like `22, 21, 21`. The resolved allocation is written to
`bulk_summary.json` and each formula's `generation_provenance.json`.

Use `scripts/slurm/submit_crystalformer_bulk.sh` for submissions. It prefers an
idle `test` node for jobs expected to finish within 30 minutes, otherwise checks
`regular256`, `regular128`, `regular6430`, `regular`, then `test`; if no idle
node exists, it queues on all of those partitions. It requests one exclusive
node and uses 56 cores on `regular` or 64 cores on the other CPU partitions.
All SLURM stdout/stderr files are written under `logs/slurm/` by default.

The example config uses `examples/crystalformer_bulk/fake_generate.py` so tests
remain offline and stdlib-only. The real example config is a template for an
existing local CrystalFormer workspace and checkpoint; it is not expected to
run until those paths are prepared. Each formula writes generation provenance,
smoke audit outputs, DPO preference artifacts, and a bulk `bulk_summary.json` /
`report.md`.

## Smoke Audit for CrystalFormer Outputs

Run a smoke audit over real CrystalFormer output files:

```bash
python scripts/audit_crystalformer_outputs.py \
  --input-dir outputs/crystalformer_raw/BaTiO3 \
  --formula BaTiO3 \
  --output-dir outputs/crystalformer_audit/BaTiO3 \
  --parser-backend none \
  --stability-mode unavailable_without_offline_validation
```

The audit writes `candidates.jsonl`, `audit_candidates.jsonl`,
`audit_summary.json`, `failure_vectors.jsonl`, `error_audit_table.md`, and
`report.md`. It records parse status, F1 geometry labels, F2 chemistry labels,
F3 unknown/unavailable status, raw sequence preservation, and DPO eligibility.
Without offline validation, F3 must not be reported as stable.

## DPO Data Preparation Boundary

This stage is not DPO training. The goal is to run the engineering loop:
CrystalFormer output -> FIIR audit -> DPO preference artifact.

Future DPO preference pairs must come from the same formula and generation
condition. If a spacegroup condition is specified, pairs must share it. Each
pair must retain CrystalFormer-native `g` / `W` / `A` / `X` / `L` fields, or a
documented equivalent raw sequence. Without F3 validation, future pairs can only
represent geometry/chemistry preferences; they must not claim stability
optimization. The schema is documented in
`docs/specs/crystalformer_dpo_data_schema.md`.
When both sides of a same-condition pair have successful imported offline F3
evidence, the builder may emit `stability_aware_offline_validation`.

To build the current schema-only preference-pair artifact from an audit:

```bash
python scripts/build_crystalformer_dpo_preferences.py \
  --audit-dir outputs/crystalformer_audit/BaTiO3 \
  --formula BaTiO3 \
  --output-dir outputs/dpo_preferences/BaTiO3
```

This writes `preference_pairs.jsonl`, `preference_summary.json`, and
`report.md`. If all eligible candidates have equal FIIR scores, the builder
emits zero pairs and records `no_comparable_margin`; it does not fabricate DPO
labels.

## CrystalFormer DPO Training Boundary

FIIR Crystal can prepare a handoff manifest for future external CrystalFormer
DPO training. This still does not implement or run training in core:

```bash
python scripts/prepare_crystalformer_dpo_training_boundary.py \
  --preference-pairs-jsonl outputs/crystalformer_smoke_fake_validated/dpo_preferences/BaTiO3/preference_pairs.jsonl \
  --output-dir outputs/crystalformer_dpo_training_boundary/BaTiO3 \
  --crystalformer-work-dir external/CrystalFormer
```

The command validates pair schema, checks the CrystalFormer workspace, writes
`trainer_manifest.json`, `training_boundary_summary.json`, `report.md`, and
`training_command_provenance.json`. If `--training-command` is provided, it is
recorded but not executed unless `--run-training` is also present.

For real training later, use a prepared CrystalFormer fork/submodule and an
explicit external command. FIIR records stdout, stderr, return code, cwd, and
command provenance, but it does not import JAX/torch or provide a DPO loss.

## Output Files

The configured runner writes:

- `candidates.jsonl`
- `failure_vectors.jsonl`
- `preference_pairs.jsonl`
- `evaluation_report.json`
- `discovery_ranking.jsonl`
- `feedback_records.jsonl`
- `experiment_summary.json`
- `report.md`

Pair mode comparison writes `comparison_summary.json`, `comparison_table.md`,
and `report.md`, plus one full experiment output directory per mode.

Aggregate comparison writes `aggregate_summary.json`, `aggregate_table.md`, and
`report.md`.

Mock active loop writes `round_001/`, `round_002/`, ... experiment directories,
plus `feedback_buffer.jsonl`, `active_loop_state.json`,
`active_loop_summary.json`, and `active_loop_report.md`.

## Package Layout

- `fiir_crystal.failure`: F1/F2/F3 vectors, lightweight labelers, oracle, and data models.
- `fiir_crystal.fsal`: matched pair mining and baseline pair construction.
- `fiir_crystal.discovery`: mock screening, ranking, validation-task metadata, and feedback.
- `fiir_crystal.structures`: stdlib-only standard structure records for external outputs.
- `fiir_crystal.generation`: generator interfaces, CrystalFormer smoke pipeline,
  workspace checks, and bulk orchestration.
- `fiir_crystal.evaluation`: experiment metrics and JSON-serializable reports.
- `fiir_crystal.io`: JSON/JSONL helpers.
- `fiir_crystal.config`: lightweight config loader.
- `fiir_crystal.reporting`: Markdown report generator.
- `fiir_crystal.validation`: offline validation result records and joins.
- `fiir_crystal.validation.offline_import`: local validation import into
  CrystalFormer smoke audits.
- `fiir_crystal.dpo.training_boundary`: external CrystalFormer DPO trainer
  manifest and readiness checks.
- `fiir_crystal.comparison`: pair mode comparison and run aggregation.
- `fiir_crystal.feedback`: feedback buffer and mock active loop simulation.

## Current Limitations

- Mock structures are not physical crystal objects.
- F2 chemistry is a lightweight placeholder. F3 is unavailable unless local
  offline validation is imported.
- CrystalFormer adapter parsing is conservative and does not parse CIF contents
  without an optional external parser.
- No MLIP, DFT, database novelty, synthesizability model, or in-core real training is run.
- Pareto ranking is intentionally small and deterministic.
- Active loop rounds reuse mock candidates with metadata hints; no generator is trained.

## Next Steps

Phase A: real-smoke pipeline

- Keep the CrystalFormer smoke pipeline reproducible on fake and local raw outputs.
- Use validate-only bulk orchestration and the SLURM test template to move from
  single-formula smoke tests to small multi-formula existing-checkpoint runs.

Phase B: offline validation / MLIP import boundary

- Expand already-computed validation imports to additional local formats.
- Keep validation imports local and optional; do not run DFT, MLIP, or external APIs from core.

Phase C: CrystalFormer DPO training adapter boundary

- Use the trainer manifest with a recorded CrystalFormer fork/submodule.
- Implement DPO loss integration in that external workspace, without adding torch/JAX/pymatgen/ASE to `fiir_crystal` core dependencies.
