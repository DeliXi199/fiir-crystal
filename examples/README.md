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

`mock_validation_results.jsonl` simulates offline validation imports. These rows
are hand-written mock results and do not run MLIP, DFT, or external APIs.

Each validation row uses `candidate_id` to join back to rankings and feedback:

- `validation_source`: provenance label for the offline source.
- `status`: `completed`, `failed`, `pending`, or another local status string.
- `validated`: whether the result completed successfully.
- `is_stable`: offline stability verdict when available.
- `e_above_hull`, `band_gap`, `relaxed`: placeholder physical result fields.
- `novelty_label`: mock novelty verdict such as `novel` or `known`.
- `synthesizability_score`: mock score in `[0, 1]`.
- `error_message`: non-empty for failed validation imports.
- `metadata`: audit notes for tests and reports.
