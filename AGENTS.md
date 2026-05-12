Project rules for FIIR Crystal
==============================

This file is the project-level operating guide for Codex and other coding
agents working in this repository.

Startup checklist
-----------------

- At the start of each new conversation about this project, read this file
  first.
- Then read `docs/guidance/01_fiir_project_manual.md`.
- For architecture work, important code edits, experiment planning, or
  recommendations about next steps, also read the relevant paper guidance:
  `docs/guidance/02_paper1_crystalfail_bench.md`,
  `docs/guidance/03_paper2_fsal.md`, and/or
  `docs/guidance/04_paper3_discovery_pipeline.md`.
- For cross-paper or roadmap decisions, read all guidance documents in numeric
  order.
- Treat the guidance documents as the project roadmap. Do not skip
  `docs/specs/` and implement directly from long guidance prose when a spec is
  expected.

Current project stage
---------------------

- This repository is no longer just an empty phase-one skeleton. It already has
  a local-first FIIR scaffold, mock loop, CrystalFormer adapter, bulk
  orchestration, offline validation import boundary, comparison reports, active
  loop simulation, and DPO handoff boundary.
- The immediate research/engineering priority is to turn existing generation
  outputs into useful validation evidence: offline MLIP/MACE relaxation,
  normalization/import, F3 evidence, and stability-aware preference artifacts.
- Do not treat real DPO training, DFT, MLIP execution, or external model
  installation as in-core `fiir_crystal` functionality. Those remain external
  workflows with explicit boundaries and provenance.

Execution policy
----------------

- Treat this machine as a login node.
- Do not run compute-heavy jobs directly in the local shell.
- Submit computation, training, CrystalFormer generation, MLIP/MACE validation,
  DFT, bulk generation, long evaluations, or other long-running workflows
  through SLURM (`sbatch` or the project submit wrappers) so work runs on
  allocated compute nodes.
- Local shell work is appropriate for lightweight inspection and development:
  `rg`, reading files, small stdlib scripts, formatting, dry-runs, schema
  checks, and focused unit tests that do not invoke external model
  environments.
- For SLURM work, prefer existing wrappers and planners under `scripts/slurm/`
  before inventing new submission commands. Use startup monitoring only for the
  early window, then leave long jobs to SLURM and inspect artifacts afterward.

External resources and dependencies
-----------------------------------

- Core runtime code must stay standard-library only.
- Do not automatically access the network.
- Do not download datasets, model weights, checkpoints, or external
  repositories unless the user explicitly asks for that specific action.
- Do not run DFT, MLIP, Materials Project, CSLLM, ICSD, GNoME, or other
  external API workflows from the core package.
- External models must enter through adapter boundaries.
- Do not add `torch`, `jax`, `pymatgen`, `ase`, `mace`, `chgnet`, `matgl`, or
  similar heavy scientific/model packages as core runtime dependencies.
- Tests must not require real external model environments. Keep mock and
  load-only paths runnable without those environments.

Code and artifact discipline
----------------------------

- Keep the mock loop runnable.
- Split large features into modules instead of one giant script.
- Prefer existing project interfaces in `fiir_crystal.failure`,
  `fiir_crystal.fsal`, `fiir_crystal.generation`, `fiir_crystal.validation`,
  `fiir_crystal.discovery`, and related modules.
- Write generated experiment artifacts under `outputs/`.
- Write SLURM stdout/stderr under `logs/slurm/`.
- Do not commit large generated outputs, checkpoints, raw model artifacts, or
  local environment files.
- Preserve provenance for any external command boundary: command, cwd,
  environment assumptions, stdout/stderr locations, return code, and input/output
  artifact paths.
