# ADR-0001: Project Scope

## Status

Accepted.

## Decision

FIIR Crystal starts with a lightweight, local-only closed loop before any real
MLIP, DFT, remote database, or training integration.

## Rationale

The first risk is data-flow complexity, not model quality. A small reproducible
mock loop lets us validate failure vectors, pair construction, evaluation,
ranking, feedback, serialization, and reporting without expensive external
systems.

## Consequences

- Current outputs are engineering artifacts, not scientific claims.
- Heavy components remain behind adapter boundaries.
- Tests can run quickly on a login node with no external services.
