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
CrystalFormer output -> FIIR audit -> DPO eligibility marking.

Future DPO preference pairs must come from the same formula and generation
condition. If a spacegroup condition is specified, pairs must share it. Each
pair must retain CrystalFormer-native `g` / `W` / `A` / `X` / `L` fields, or a
documented equivalent raw sequence. Without F3 validation, future pairs can only
represent geometry/chemistry preferences; they must not claim stability
optimization. The schema is documented in
`docs/specs/crystalformer_dpo_data_schema.md`.

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
- `fiir_crystal.generation`: generator interfaces and external adapter boundaries.
- `fiir_crystal.evaluation`: experiment metrics and JSON-serializable reports.
- `fiir_crystal.io`: JSON/JSONL helpers.
- `fiir_crystal.config`: lightweight config loader.
- `fiir_crystal.reporting`: Markdown report generator.
- `fiir_crystal.validation`: offline validation result records and joins.
- `fiir_crystal.comparison`: pair mode comparison and run aggregation.
- `fiir_crystal.feedback`: feedback buffer and mock active loop simulation.

## Current Limitations

- Mock structures are not physical crystal objects.
- F2 chemistry and F3 stability are lightweight placeholders.
- CrystalFormer adapter parsing is conservative and does not parse CIF contents
  without an optional external parser.
- No MLIP, DFT, database novelty, synthesizability model, or real training is run.
- Pareto ranking is intentionally small and deterministic.
- Active loop rounds reuse mock candidates with metadata hints; no generator is trained.

## Next Steps

- Add optional local adapters for real structure objects.
- Keep FSAL trainer as an adapter boundary until real training is explicitly needed.
- Add richer local validation adapters only when results are already available offline.
- Add config hashes and seed sweeps for larger reproducibility studies.
