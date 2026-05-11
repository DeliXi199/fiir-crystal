"""CLI for local CrystalFormer workspace readiness checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.generation.crystalformer_workspace import (
    CrystalFormerWorkspaceCheckConfig,
    check_crystalformer_workspace,
    write_workspace_check_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the external CrystalFormer workspace without network, installs, or generation."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--crystalformer-dir", default="external/CrystalFormer")
    parser.add_argument("--checkpoint-dir", default="external/checkpoints")
    parser.add_argument("--output-dir", default="outputs/workspace_check")
    parser.add_argument("--no-create-output-dirs", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    config = CrystalFormerWorkspaceCheckConfig(
        repo_root=Path(args.repo_root),
        crystalformer_dir=Path(args.crystalformer_dir),
        checkpoint_dir=Path(args.checkpoint_dir),
        create_output_dirs=not args.no_create_output_dirs,
    )
    summary = check_crystalformer_workspace(config)
    files = write_workspace_check_outputs(args.output_dir, summary)

    print("CrystalFormer workspace check complete")
    print(f"  crystalformer_state: {summary['crystalformer']['clone_state']}")
    print(f"  crystalformer_dir: {summary['crystalformer']['relative_path']}")
    print(f"  checkpoints_exist: {summary['checkpoints']['exists']}")
    print(f"  json: {files['json']}")
    print(f"  markdown: {files['markdown']}")
    return {"summary": summary, "files": files}


if __name__ == "__main__":
    main()
