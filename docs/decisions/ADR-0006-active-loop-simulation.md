# ADR-0006: Active Loop Simulation

## Status

Accepted.

## Decision

The mock active loop simulates `generate -> label -> pair -> rank -> validate ->
feedback -> next round` by reusing local candidates and feedback-derived
metadata hints. It does not train or call a real generator.

## Rationale

This validates round-level artifacts, feedback buffers, and selection logic
without introducing deep learning training or heavy materials dependencies.

## Consequences

- Each round remains a normal FIIR experiment output directory.
- Positive, negative, and pending evidence can be inspected in JSONL.
- Future generator or predictor updates can replace the mock sampling hints
  without changing the reporting and feedback contracts.
