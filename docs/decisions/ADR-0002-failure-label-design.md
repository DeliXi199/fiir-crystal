# ADR-0002: Failure Label Design

## Status

Accepted.

## Decision

Failure labels use a structured F1/F2/F3 vector with confidence, calibration
tier, validity, hard-failure reasons, and metadata.

## Rationale

The project needs axis-specific supervision. Keeping geometry, chemistry, and
stability separate makes pair mining and evaluation auditable. The lightweight
tiers distinguish invalid, mock-only, rule-based, future ensemble, and future
DFT-calibrated labels without claiming unavailable validation.

## Consequences

- Tier 0-2 are implemented now.
- Tier 3-4 are placeholders until offline ensemble/DFT data is imported.
- Real chemistry and stability checks can replace the current lightweight
  adapters without changing downstream schemas.
