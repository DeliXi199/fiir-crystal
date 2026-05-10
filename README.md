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

## Package Layout

- `fiir_crystal.failure`: F1/F2/F3 vectors, lightweight labelers, oracle, and data models.
- `fiir_crystal.fsal`: matched pair mining and baseline pair construction.
- `fiir_crystal.discovery`: mock screening, ranking, validation-task metadata, and feedback.
- `fiir_crystal.evaluation`: experiment metrics and JSON-serializable reports.
- `fiir_crystal.io`: JSON/JSONL helpers.
- `fiir_crystal.config`: lightweight config loader.
- `fiir_crystal.reporting`: Markdown report generator.

## Current Limitations

- Mock structures are not physical crystal objects.
- F2 chemistry and F3 stability are lightweight placeholders.
- No MLIP, DFT, database novelty, synthesizability model, or real training is run.
- Pareto ranking is intentionally small and deterministic.

## Next Steps

- Add optional local adapters for real structure objects.
- Add JSONL import for offline validation results.
- Keep FSAL trainer as an adapter boundary until real training is explicitly needed.
- Expand reports with comparison tables across pair modes.
