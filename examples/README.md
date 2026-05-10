# Mock Candidate Examples

`mock_candidates.jsonl` is a small local-only dataset for exercising the
lightweight FIIR pipeline. It is not a real materials dataset.

Each JSONL row describes a `StructureLike` record:

- `candidate_id`: unique candidate identifier.
- `composition`: formula-like string used by the lightweight chemistry checker.
- `num_atoms`: atom count used by geometry checks and pair matching.
- `space_group`: optional integer space group placeholder.
- `prototype`: structural family placeholder such as `perovskite` or `spinel`.
- `lattice_lengths`: mock lattice lengths.
- `lattice_angles`: mock lattice angles.
- `frac_coords`: mock fractional coordinates.
- `mock_geometry_score`: optional geometry failure prior.
- `mock_chemistry_score`: optional chemistry failure prior.
- `mock_stability_score`: optional stability failure prior.
- `metadata.composition_family`: optional family used by pair matching.
- `metadata.mock_novelty` / `metadata.mock_diversity`: discovery ranking placeholders.

The file intentionally includes good candidates, geometry failures, chemistry
failures, stability failures, hard constraint failures, different prototypes,
different atom counts, and different space groups.
