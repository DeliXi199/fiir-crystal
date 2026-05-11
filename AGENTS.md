Project rules for FIIR Crystal:

- Core runtime code must stay standard-library only.
- Do not automatically access the network.
- Do not download datasets, model weights, checkpoints, or external repositories.
- Do not run DFT, MLIP, Materials Project, or other external API workflows.
- External models must enter through adapter boundaries.
- Tests must not require real external model environments.
- Keep the mock loop runnable.
- Split large features into modules instead of one giant script.
