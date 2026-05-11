"""Local readiness checks for the external CrystalFormer workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fiir_crystal.io import write_json


DEFAULT_OUTPUT_DIRS = (
    "outputs/crystalformer_raw",
    "outputs/crystalformer_audit",
    "outputs/dpo_preferences",
)


@dataclass(slots=True)
class CrystalFormerWorkspaceCheckConfig:
    """Configuration for a no-network CrystalFormer workspace check."""

    repo_root: Path = Path(".")
    crystalformer_dir: Path = Path("external/CrystalFormer")
    checkpoint_dir: Path = Path("external/checkpoints")
    output_dirs: tuple[Path, ...] = field(
        default_factory=lambda: tuple(Path(item) for item in DEFAULT_OUTPUT_DIRS)
    )
    create_output_dirs: bool = True


def check_crystalformer_workspace(
    config: CrystalFormerWorkspaceCheckConfig | None = None,
) -> dict[str, Any]:
    """Check local CrystalFormer workspace readiness without external side effects."""

    cfg = config or CrystalFormerWorkspaceCheckConfig()
    repo_root = cfg.repo_root.resolve()
    crystalformer_dir = _resolve(repo_root, cfg.crystalformer_dir)
    checkpoint_dir = _resolve(repo_root, cfg.checkpoint_dir)
    gitmodules_path = repo_root / ".gitmodules"

    output_summaries = []
    for output_dir in cfg.output_dirs:
        path = _resolve(repo_root, output_dir)
        existed_before = path.exists()
        created = False
        if cfg.create_output_dirs and not existed_before:
            path.mkdir(parents=True, exist_ok=True)
            created = True
        output_summaries.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "created": created,
                "relative_path": _relative(path, repo_root),
            }
        )

    clone_state = _clone_state(crystalformer_dir, gitmodules_path)
    checkpoint_exists = checkpoint_dir.exists()
    return {
        "tool": "check_crystalformer_workspace",
        "network_access": False,
        "installs_dependencies": False,
        "modifies_crystalformer": False,
        "repo_root": str(repo_root),
        "crystalformer": {
            "path": str(crystalformer_dir),
            "relative_path": _relative(crystalformer_dir, repo_root),
            "exists": crystalformer_dir.exists(),
            "clone_state": clone_state,
            "is_normal_clone": clone_state == "normal_clone",
            "is_submodule": clone_state == "submodule",
            "is_missing": clone_state == "missing",
            "git_metadata": _git_metadata_state(crystalformer_dir),
        },
        "checkpoints": {
            "path": str(checkpoint_dir),
            "relative_path": _relative(checkpoint_dir, repo_root),
            "exists": checkpoint_exists,
            "note": (
                "checkpoint directory is optional for load-only smoke tests"
                if not checkpoint_exists
                else "checkpoint directory exists; contents were not inspected"
            ),
        },
        "outputs": output_summaries,
        "recommendations": _recommendations(clone_state, checkpoint_exists),
    }


def write_workspace_check_outputs(
    output_dir: str | Path,
    summary: dict[str, Any],
) -> dict[str, str]:
    """Write JSON and Markdown workspace readiness summaries."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "json": str(destination / "workspace_check.json"),
        "markdown": str(destination / "workspace_check.md"),
    }
    write_json(files["json"], summary)
    Path(files["markdown"]).write_text(render_workspace_check_markdown(summary), encoding="utf-8")
    return files


def render_workspace_check_markdown(summary: dict[str, Any]) -> str:
    """Render a concise Markdown summary for humans."""

    crystalformer = summary["crystalformer"]
    checkpoints = summary["checkpoints"]
    lines = [
        "# CrystalFormer Workspace Check",
        "",
        "## Boundary",
        "- This check is local-only.",
        "- It does not clone repositories, install dependencies, download checkpoints, or modify CrystalFormer.",
        "",
        "## Workspace",
        f"- path: `{crystalformer['relative_path']}`",
        f"- exists: {crystalformer['exists']}",
        f"- clone_state: {crystalformer['clone_state']}",
        f"- git_metadata: {crystalformer['git_metadata']}",
        "",
        "## Checkpoints",
        f"- path: `{checkpoints['relative_path']}`",
        f"- exists: {checkpoints['exists']}",
        f"- note: {checkpoints['note']}",
        "",
        "## Output Directories",
    ]
    for output in summary["outputs"]:
        lines.append(
            f"- `{output['relative_path']}`: exists={output['exists']}, created={output['created']}"
        )
    lines.extend(["", "## Recommendations"])
    for item in summary["recommendations"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _clone_state(crystalformer_dir: Path, gitmodules_path: Path) -> str:
    if not crystalformer_dir.exists():
        return "missing"
    git_state = _git_metadata_state(crystalformer_dir)
    if git_state == "submodule_git_file" or _gitmodules_mentions(gitmodules_path, crystalformer_dir):
        return "submodule"
    if git_state == "normal_git_dir":
        return "normal_clone"
    return "present_without_git_metadata"


def _git_metadata_state(path: Path) -> str:
    git_path = path / ".git"
    if git_path.is_file():
        return "submodule_git_file"
    if git_path.is_dir():
        return "normal_git_dir"
    return "absent"


def _gitmodules_mentions(gitmodules_path: Path, crystalformer_dir: Path) -> bool:
    if not gitmodules_path.exists():
        return False
    try:
        text = gitmodules_path.read_text(encoding="utf-8")
    except OSError:
        return False
    normalized = str(crystalformer_dir).replace("\\", "/")
    return "external/CrystalFormer" in text or normalized in text


def _recommendations(clone_state: str, checkpoint_exists: bool) -> list[str]:
    recommendations = []
    if clone_state == "missing":
        recommendations.append(
            "For real generation, create external/CrystalFormer manually as a clone, fork, or submodule."
        )
    elif clone_state == "normal_clone":
        recommendations.append(
            "Plain clone mode is suitable for load-only smoke runs."
        )
    elif clone_state == "submodule":
        recommendations.append(
            "Submodule/fork mode is suitable for later trainer-adapter work."
        )
    else:
        recommendations.append(
            "The CrystalFormer path exists but git metadata was not detected; verify it before real generation."
        )
    if not checkpoint_exists:
        recommendations.append(
            "external/checkpoints is absent; this is fine for load-only smoke tests."
        )
    recommendations.append(
        "Future DPO work should prefer a recorded fork or submodule, but this check will not create one."
    )
    return recommendations


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
