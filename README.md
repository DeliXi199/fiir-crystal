# FIIR Crystal

FIIR Crystal is a lightweight project skeleton for Failure-Informed Iterative
Refinement in crystal generation. The current repository stage focuses on
engineering contracts: dataclasses, abstract interfaces, configuration
placeholders, and minimal tests.

The package intentionally does not run heavy external workflows:

- no deep learning training implementation;
- no DFT execution;
- no MLIP execution;
- no Materials Project, CSLLM, or other external API calls;
- no dataset downloads.

## Package Layout

- `fiir_crystal.failure`: F1/F2/F3 failure vectors, failure labels, labeler
  interfaces, and calibration-tier metadata.
- `fiir_crystal.predictor`: abstract Failure Predictor interface; no concrete
  GNN is implemented.
- `fiir_crystal.fsal`: preference pair dataclasses, matched axis-aligned pair
  miner contract, and DPO trainer adapter contract.
- `fiir_crystal.generation`: generator wrapper abstraction.
- `fiir_crystal.evaluation`: metric value/report dataclasses and metric
  computer interfaces.
- `fiir_crystal.discovery`: discovery pipeline records and adapter interfaces
  for screening, ranking, validation task creation, and feedback.

## Minimal Loop

The intended FIIR minimum loop is:

1. represent generated structures as `CandidateRecord`;
2. attach F1/F2/F3 `FailureLabel` records;
3. build `PreferencePair` and `PreferenceDataset` objects for FSAL;
4. call an `FSALTrainer` adapter;
5. evaluate validity, stability, novelty, diversity, and failure rates;
6. pass ranked candidates into discovery validation-task metadata and feedback.

## Current Mock Closed Loop

The repository now includes a runnable lightweight FIIR-v1 demo:

```bash
python scripts/run_mock_fiir_loop.py
```

The demo uses `StructureLike`/`CrystalRecord` objects with mock metadata, runs
`FailureOracle` over lightweight F1/F2/F3 labelers, mines matched axis-aligned
preference pairs, computes an evaluation report, ranks candidates with a mock
discovery pipeline, and emits top-k feedback records. All of this is local and
replaceable; real crystal toolkits, MLIP, DFT, Materials Project, CSLLM, and
training code remain outside the current implementation.

## Development

Install in editable mode with test dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the lightweight test suite:

```bash
python -m pytest
```

All current tests use only the Python standard library plus pytest.
