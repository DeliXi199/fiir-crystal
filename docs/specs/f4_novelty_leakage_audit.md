# F4 Novelty Leakage Audit Import

This spec defines the local evidence contract for importing externally computed
F4 novelty/leakage audit results into FIIR Crystal candidate rows.

## Boundary

The FIIR core project consumes F4 audit evidence but does not compute it in this
step. The import path:

- reads local JSONL files only;
- does not run StructureMatcher, pymatgen, Materials Project, database queries,
  downloads, or external APIs;
- preserves external audit provenance so the reference pool and matching
  workflow can be reproduced outside the core package.

The external workflow is responsible for building the reference pool and
computing nearest-reference matches. FIIR Crystal is responsible for schema
validation, candidate-id joins, summary statistics, and report generation.

## Inputs

Default candidate index:

```text
outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl
```

Default external F4 results:

```text
outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl
```

Each F4 JSONL row must be an object:

```json
{
  "schema_version": "f4-audit-v1",
  "reference_pool_id": "reference_pool_v1",
  "audit_run_id": "f4_reference_pool_v1_20260513",
  "candidate_id": "crystalformer_output_AgNbO3_000001",
  "f4_novelty_leakage": 0.92,
  "nearest_reference_id": "mp-xxxx",
  "reference_source": "materials_project_snapshot",
  "match_type": "structure_matcher",
  "fingerprint_distance": 0.03,
  "confidence": 0.95,
  "metadata": {}
}
```

Required fields:

- `candidate_id`
- `f4_novelty_leakage`
- `reference_source`
- `match_type`
- `confidence`

`schema_version`, `reference_pool_id`, `audit_run_id`,
`nearest_reference_id`, `fingerprint_distance`, and `metadata` are optional but
recommended.

## Score Semantics

`f4_novelty_leakage` is a leakage or near-duplicate risk score in `[0, 1]`.
Lower is better.

- `0.00-0.20`: very low leakage risk
- `0.20-0.50`: low leakage risk
- `0.50-0.80`: medium leakage risk
- `0.80-1.00`: high leakage risk

This preserves the existing FIIR taxonomy where F4 is a constraint and
evaluation axis, not a DPO training target.

## Join Rules

Rows are joined by `candidate_id`.

- Candidate has a matching F4 row: attach `f4_novelty_audit`, set
  `f4_novelty_available=true`, copy `f4_novelty_leakage`, and add the evidence
  under both `evidence.f4_novelty_audit` and
  `failure_vector.metadata.f4_novelty_audit`.
- Candidate has no F4 row: keep the candidate and mark
  `f4_status="missing"`.
- F4 row has no candidate: keep it out of candidate outputs and count it as an
  orphan in the summary.
- Duplicate candidate ids in the candidate index are an error.
- Duplicate `candidate_id` values in F4 results are an error by default. The
  CLI can allow them with `--allow-duplicate-results`, in which case the first
  row wins and duplicates are counted.
- Malformed JSONL, missing required fields, out-of-range scores, out-of-range
  confidence, and negative fingerprint distances fail fast.

## Outputs

The import script writes:

```text
outputs/f4_novelty_import_1024_YYYYMMDD/
  candidates_with_f4.jsonl
  f4_import_summary.json
  f4_import_report.md
```

The summary includes candidate count, F4 row count, matched count, missing
count, orphan count, duplicate count, score statistics, score bins, source and
match-type breakdowns, high-leakage candidates, input hashes, and local-only
execution flags.

## CLI

```bash
python scripts/import_f4_novelty_audit.py \
  --candidate-index outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl \
  --f4-results-jsonl outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl \
  --output-dir outputs/f4_novelty_import_1024_20260513
```

Useful guards:

```bash
python scripts/import_f4_novelty_audit.py \
  --fail-on-missing \
  --fail-on-orphans
```
