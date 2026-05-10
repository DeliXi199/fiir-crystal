# ADR-0004: Experiment Runner Design

## Status

Accepted.

## Decision

The experiment runner reads JSONL candidates, writes JSONL/JSON intermediate
artifacts, and generates a Markdown report.

## Rationale

JSONL keeps records inspectable, stream-friendly, and dependency-free. JSON
summary files are easy to consume from tests and notebooks. Markdown provides a
human-readable report without adding a template system.

## Consequences

- The runner can be reproduced from a config file and local JSONL input.
- Intermediate files make debugging pair construction and ranking straightforward.
- Future offline validation results can use the same serialization style.
