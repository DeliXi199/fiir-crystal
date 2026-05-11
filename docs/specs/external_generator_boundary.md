# External Generator Boundary

External generators must enter FIIR Crystal through an adapter that produces
`CrystalStructureRecord` objects. The core package must remain stdlib-only and
must not depend on JAX, torch, pymatgen, ASE, CrystalFormer, or generator-specific
runtime packages.

Boundary rules:

- no automatic network calls;
- no automatic git clone, pip install, checkpoint download, or dataset download;
- no DFT, MLIP, Materials Project, or other external API execution;
- no generator training inside FIIR Crystal;
- external model outputs are candidates, not validated stable materials;
- tests use fake outputs and do not require the real external model.

Adapters may provide a subprocess mode, but only with an explicit command from
the user. The default behavior should read existing local outputs.
