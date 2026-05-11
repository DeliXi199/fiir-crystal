# CrystalFormer Adapter

FIIR Crystal treats `deepmodeling/CrystalFormer` as an external generator. The
adapter reads files that already exist on disk, normalizes them to
`CrystalStructureRecord`, and hands those records to the lightweight FIIR
failure attribution, ranking, and reporting flow.

Supported load-only inputs:

- normalized JSONL, where each row is a `CrystalStructureRecord` dictionary;
- raw CrystalFormer sampling CSV with `g` / `W` / `A` / `X` / `L`-style fields
  when enough structure fields are present;
- `awl2struct` struct CSV with a CIF string or CIF path, stored as
  `structure_ref`;
- a directory of `.cif` files, represented as structure-reference stubs;
- `manifest.json` pointing at any of the above.

Subprocess mode is optional. When `run_generation: true`, the adapter calls the
user-provided `crystalformer_command` with `subprocess.run`. FIIR Crystal does
not infer a CrystalFormer path, install dependencies, download checkpoints,
download datasets, or train the model.

The adapter preserves CrystalFormer-native sequence information for later DPO
preference construction. `CrystalStructureRecord.metadata` includes:

- `raw_crystalformer_row`
- `raw_sequence_fields`
- `raw_g`, `raw_W`, `raw_A`, `raw_X`, `raw_L`
- `raw_sequence_status`
- `missing_sequence_fields`
- `sampling_metadata`
- `source_model`
- `source_checkpoint`
- `formula_condition`
- `spacegroup_condition`
- `temperature`
- `top_k` / `K`
- `original_row_index`
- `source_format`

When only a struct CSV or CIF reference is available, the adapter records a
clear `raw_sequence_status` such as `partial` or `missing` rather than silently
pretending the native sequence is present.

Sampling metadata such as `score`, `logprob`, `temperature`, and rank are stored
under `metadata`. They are not treated as stability evidence.
