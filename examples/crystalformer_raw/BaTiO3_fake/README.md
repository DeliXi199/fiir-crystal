# Fake CrystalFormer Raw Output: BaTiO3

This directory contains tiny hand-written fake outputs for local tests and
smoke examples. They are not real `deepmodeling/CrystalFormer` results and
must not be interpreted as generated or validated structures.

The CSV intentionally includes:

- complete `g` / `W` / `A` / `X` / `L` sequence fields;
- a candidate with a missing sequence field;
- structured species, fractional coordinates, and lattice data;
- a CIF-reference-only partial candidate;
- candidates with different FIIR geometry scores;
- candidates with equal scores so `no_comparable_margin` is observable.
