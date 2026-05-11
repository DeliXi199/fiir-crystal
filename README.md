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
- No MLIP, DFT, database novelty, synthesizability model, or real training is run.
- Pareto ranking is intentionally small and deterministic.
- Active loop rounds reuse mock candidates with metadata hints; no generator is trained.

## Next Steps

- Add optional local adapters for real structure objects.
- Keep FSAL trainer as an adapter boundary until real training is explicitly needed.
- Add richer local validation adapters only when results are already available offline.
- Add config hashes and seed sweeps for larger reproducibility studies.
