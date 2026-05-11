# ADR-0007: Comparison Reporting

## Status

Accepted.

## Decision

Pair mode comparison and experiment aggregation write both machine-readable JSON
and human-readable Markdown tables/reports.

## Rationale

The project needs quick comparisons across `axis_aligned`, `weighted_sum`,
`random_negative`, and `binary_success_failure` baselines. JSON supports tests
and downstream notebooks; Markdown tables are convenient for lab notes and paper
experiment logs.

## Consequences

- Every compared mode is still a complete standalone experiment run.
- Aggregate reports fail clearly when required output files are missing.
- Validation-aware columns are included only when offline validation results are
  provided.
