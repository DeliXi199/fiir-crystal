# ADR-0002: Failure Label Design

## Status

Superseded by FIIR-v2.2 guidance.

## Decision

Failure labels use a structured F1-F5 vector with confidence, calibration tier,
validity, hard-failure reasons, and metadata.

F1/F2/F3 remain the FSAL training axes. F4 is a novelty/leakage constraint used
for filtering, benchmark credibility, and evaluation. F5 is a synthesizability
signal used for discovery screening and post-hoc analysis. F4 and F5 are not
DPO optimization targets.

## Rationale

The project needs axis-specific supervision without collapsing failure modes
into a scalar reward. Keeping geometry, chemistry, and stability separate makes
pair mining auditable, while F4/F5 carry evaluation and discovery constraints
that should not become direct training pressure.

Calibration tier semantics follow the v2.2 guidance: Tier 1 is highest
confidence, Tier 4 is lowest confidence. Tier 0 is an implementation sentinel
for invalid/hard-failure records.

## Consequences

- The lightweight implementation computes F1/F2/F3 locally and can pass through
  optional F4/F5 metadata or offline evidence.
- Tier 4 covers mock/rules-only/unavailable validation in the current local
  implementation.
- Tier 1/2 require imported high-fidelity or multi-oracle evidence and must not
  be fabricated by local code.
- Real chemistry and stability checks can replace the current lightweight
  adapters without changing downstream schemas.
