# ADR-0005: Offline Validation Results

## Status

Accepted.

## Decision

FIIR Crystal imports validation results from local JSONL files instead of
running MLIP, DFT, Materials Project, CSLLM, or external services.

## Rationale

The first engineering phase needs reproducible data flow before expensive
physics or model adapters are introduced. JSONL keeps offline results auditable,
testable, and easy to join by `candidate_id`.

## Consequences

- Validation-aware metrics can be tested without external dependencies.
- Failed or pending validation rows are recorded without crashing the pipeline.
- Real validation executors remain future adapters outside the lightweight core.
