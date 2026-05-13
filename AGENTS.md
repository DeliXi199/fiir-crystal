Project rules for FIIR Crystal
==============================

This file is the project-level operating guide for Codex and other coding
agents working in this repository.

Startup checklist
-----------------

- At the start of each new conversation about this project, read this file
  first.
- Then read `docs/status/current_project_state.md` for the latest saved project
  state, important run results, and recommended next actions.
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
- When a submitted SLURM job needs to run for more than a brief startup window,
  do not sit idle watching the queue. Monitor only the early startup window,
  then work on safe, lightweight local tasks such as documentation, manifests,
  schema checks, tests, or runbook preparation, and return later to inspect
  `squeue`/`sacct` and produced artifacts.
- For larger GPU jobs, first use the normal resource-aware GPU selection and
  pin the best currently free eligible long-running GPU node. Queue flexibly
  across eligible GPU partitions/nodes only when no long-running GPU node has
  enough free resources, so SLURM can start the job on whichever eligible
  resource becomes available first. Keep short bounded GPU sanity jobs eligible
  for `test` only when the explicit time limit is 30 minutes or less.
- GPU jobs must request actual GPUs, not merely land on a GPU node and use CPU
  cores. For flexible larger jobs, set the requested GPU count explicitly
  through the existing wrapper/planner knobs such as `FIIR_GPU_MIN_GPUS` or
  `--min-gpus`.
- For larger CrystalFormer generation, MLIP validation, DPO smoke/evaluation,
  and similar GPU compute jobs, request the full GPU count of the target node
  class whenever the candidate partitions are homogeneous enough to do so. On
  the current long-running CUDA GPU partitions this usually means
  `FIIR_GPU_MIN_GPUS=8`.
- Local shell work is appropriate for lightweight inspection and development:
  `rg`, reading files, small stdlib scripts, formatting, dry-runs, schema
  checks, and focused unit tests that do not invoke external model
  environments.
- For SLURM work, prefer existing wrappers and planners under `scripts/slurm/`
  before inventing new submission commands. Use startup monitoring only for the
  early window, then leave long jobs to SLURM and inspect artifacts afterward.
- Resource-use principle: every SLURM job must request and actually use the
  full compute-resource shape of its target node or homogeneous partition set.
  This applies to all submitted jobs, including smoke, debug, validation,
  generation, training, and evaluation jobs. Configure both the SLURM request
  and task-level concurrency so allocated CPUs, GPUs, and nodes are used rather
  than left idle. If a workflow cannot use the full node shape, do not submit it
  to SLURM in that form; reshape the task, choose a matching partition, or keep
  it local only if it is lightweight and allowed by the login-node policy.

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

Project memory discipline
-------------------------

- Important run results, conclusions, artifact paths, and next-step decisions
  must be saved in `docs/status/current_project_state.md`.
- Significant executed workflows should be appended to `docs/status/run_log.md`
  with date, command intent, output paths, key counts, and caveats.
- Keep status documents lightweight and durable. Reference generated files under
  `outputs/`, but do not commit heavy generated artifacts.
- If an experiment result changes the research direction or active next step,
  update the status documents in the same turn as the code or workflow change.
- At the end of each task, inspect whether the completed work should be uploaded
  to GitHub. If the change is a durable code, configuration, rule, or status
  update and the worktree can be scoped cleanly without large ignored artifacts
  or unrelated user changes, commit and push through the configured remote. If
  upload is not safe, record why in the final response or status notes instead
  of silently skipping it.
