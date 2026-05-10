# ADR-0003: Axis-Aligned Pair Mining

## Status

Accepted.

## Decision

The primary pair mode is matched axis-aligned pair mining. Baselines
`weighted_sum`, `random_negative`, and `binary_success_failure` are also kept.

## Rationale

Axis-aligned pairs preserve which failure dimension changed while controlling
simple structure metadata such as prototype, atom count, space group, and
composition family. Baselines are required to test whether axis alignment is
actually useful compared with scalar or weaker pair construction.

## Consequences

- All modes output the same `PreferencePair` schema.
- No mode performs training.
- Random baselines accept a seed for reproducibility.
