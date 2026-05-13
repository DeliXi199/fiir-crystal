# F4 Reference Pool Workspace

FIIR Crystal treats F4 novelty/leakage checking as an external audit workflow.
The core package plans tasks, imports finished evidence, and reports coverage.
It does not build databases or run structure matching.

## Boundary

The FIIR core project does not:

- does not run StructureMatcher or pymatgen;
- download Materials Project, ICSD, Alexandria, GNoME, or training-set data;
- call external APIs;
- install database clients or ML/structure-matching dependencies;
- write into live CrystalFormer generation directories.

F4 evidence becomes usable only after an external worker writes local
`f4_results.jsonl` rows that conform to the import schema.

## Recommended Layout

```text
outputs/f4_novelty_audit/reference_pool_v1/
  f4_audit_plan.json
  f4_audit_tasks.jsonl
  f4_results.jsonl
  reference_pool_manifest.example.json
  reference_pool_manifest.json
  report.md
  references/
    materials_project_snapshot.structures.jsonl
    training_set_snapshot.structures.jsonl
  shards/
    f4_audit_tasks_shard_0000.jsonl
    f4_audit_tasks_shard_0001.jsonl
```

`reference_pool_manifest.example.json` is a placeholder written by the planner.
Replace it with a real `reference_pool_manifest.json` before launching external
workers.

## Plan Tasks

Create the task plan from the current 1024 candidate index:

```bash
python scripts/plan_f4_novelty_audit.py \
  --candidate-index outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl \
  --output-dir outputs/f4_novelty_audit/reference_pool_v1 \
  --reference-pool-id reference_pool_v1 \
  --shard-count 16 \
  --require-f1-pass \
  --require-f2-pass
```

The planner writes:

- `f4_audit_plan.json`
- `f4_audit_tasks.jsonl`
- `shards/f4_audit_tasks_shard_*.jsonl`
- `reference_pool_manifest.example.json`
- `skipped_candidates.jsonl`
- `report.md`

The task rows are deterministic and have schema `f4-audit-task-v1`. Each task
contains a candidate id, formula, candidate-index row number, local reference
pool manifest path, expected result path, and a candidate snapshot for external
workers. Task rows point to the expected real
`reference_pool_manifest.json`; the `.example.json` file is only a template.

## Reference Manifest

A real manifest must use this shape:

```json
{
  "schema_version": "f4-reference-pool-manifest-v1",
  "reference_pool_id": "reference_pool_v1",
  "example_manifest": false,
  "created_time_utc": "2026-05-13T00:00:00+00:00",
  "total_reference_count": 123456,
  "reference_sources": [
    {
      "name": "materials_project_snapshot",
      "path": "outputs/f4_novelty_audit/reference_pool_v1/references/materials_project_snapshot.structures.jsonl",
      "format": "structure_jsonl",
      "reference_count": 123456,
      "sha256": "record-explicitly"
    }
  ]
}
```

All paths should point to local files. The manifest is provenance, not a
download recipe.

Prepare a local CSV with CIF text/path fields as a reference source JSONL:

```bash
python scripts/prepare_f4_reference_source.py \
  --input-csv external/CrystalFormer/data/mini.csv \
  --source-name crystalformer_mini_example \
  --output-jsonl outputs/f4_novelty_audit/reference_pool_mini_smoke/references/crystalformer_mini_example.structures.jsonl
```

This helper is useful for smoke tests and for reshaping real local snapshots
after they have been obtained. Do not treat `external/CrystalFormer/data/mini.csv`
as production F4 evidence; it is a tiny example file and is not the Alex-20s
training snapshot.

Build a real manifest from local reference JSONL files:

```bash
python scripts/build_f4_reference_pool_manifest.py \
  --reference-source materials_project_snapshot=outputs/f4_novelty_audit/reference_pool_v1/references/materials_project_snapshot.structures.jsonl \
  --reference-source training_set_snapshot=outputs/f4_novelty_audit/reference_pool_v1/references/training_set_snapshot.structures.jsonl \
  --reference-pool-id reference_pool_v1 \
  --output-json outputs/f4_novelty_audit/reference_pool_v1/reference_pool_manifest.json
```

The builder reads existing local files, counts rows, checks duplicate
`reference_id` values, computes per-file `sha256`, and writes
`reference_pool_manifest.json` plus `reference_pool_manifest_report.md`. It does
not download reference data or run any matching.

## Readiness Check

Before launching external workers:

```bash
python scripts/check_f4_novelty_audit_ready.py \
  --plan-json outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json \
  --output-json outputs/f4_novelty_audit/reference_pool_v1/readiness_summary.json
```

The check verifies:

- plan JSON exists and is readable;
- task JSONL exists and row count matches the plan;
- task ids and candidate ids are unique;
- shard files exist and collectively cover all tasks;
- a non-example reference manifest exists;
- reference source files exist and have positive reference counts.

For post-run checks, require result rows too:

```bash
python scripts/check_f4_novelty_audit_ready.py \
  --plan-json outputs/f4_novelty_audit/reference_pool_v1/f4_audit_plan.json \
  --require-results
```

## Worker Output

External workers should write:

```text
outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl
```

Each row must follow `f4-audit-v1`:

```json
{
  "schema_version": "f4-audit-v1",
  "reference_pool_id": "reference_pool_v1",
  "audit_run_id": "reference_pool_v1_20260513",
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

`f4_novelty_leakage` is a leakage or near-duplicate risk score in `[0, 1]`.
Lower is better.

## Import Finished Results

Once `f4_results.jsonl` exists:

```bash
python scripts/import_f4_novelty_audit.py \
  --candidate-index outputs/mlip_validation_three_mlip_1024_20260513_batch/candidate_index.jsonl \
  --f4-results-jsonl outputs/f4_novelty_audit/reference_pool_v1/f4_results.jsonl \
  --output-dir outputs/f4_novelty_import_1024_20260513 \
  --fail-on-orphans
```

The import stage writes `candidates_with_f4.jsonl`,
`f4_import_summary.json`, and `f4_import_report.md`. It still does not run any
matching or external service.
