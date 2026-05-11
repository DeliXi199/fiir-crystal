# CrystalFormer To FIIR Loop

The first CrystalFormer integration follows this local-only loop:

1. Read a CrystalFormer output file or directory.
2. Normalize each candidate to `CrystalStructureRecord` while preserving raw
   `g` / `W` / `A` / `X` / `L` fields where available.
3. Write `candidates.jsonl`.
4. Run a smoke audit that records parse status, F1 geometry, F2 chemistry, F3
   unavailable/unknown status, and DPO eligibility.
5. Convert records to lightweight `StructureLike` objects when using the
   existing FIIR experiment runner.
6. Run existing FIIR failure attribution, preference-pair mining, ranking, and
   report generation.

F1 geometry uses the degraded `StructureLike` representation. If fractional
coordinates and a lattice matrix are available, FIIR computes lightweight
geometry checks. CIF-only candidates are kept as references and may be marked
invalid or partial until a parser or richer offline import is available.

F2 chemistry uses `composition` or a formula derived from species when present.

F3 stability is unavailable without offline validation, MLIP relaxation, or DFT
result import. CrystalFormer scores, log probabilities, and temperatures remain
provenance metadata. They must not be reported as thermodynamic stability or as
proof that a material is stable.

The smoke audit is not DPO training. It only prepares the engineering closure:
CrystalFormer output -> FIIR audit -> DPO eligibility flags. Preference-pair
construction and DPO training are separate later stages.
