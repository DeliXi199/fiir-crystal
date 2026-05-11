import json
from pathlib import Path

from fiir_crystal.generation.crystalformer_workspace import (
    CrystalFormerWorkspaceCheckConfig,
    check_crystalformer_workspace,
    write_workspace_check_outputs,
)


def test_workspace_check_missing_state_creates_output_dirs(tmp_path) -> None:
    summary = check_crystalformer_workspace(
        CrystalFormerWorkspaceCheckConfig(repo_root=tmp_path)
    )

    assert summary["crystalformer"]["clone_state"] == "missing"
    assert summary["outputs"]
    assert all(item["exists"] for item in summary["outputs"])


def test_workspace_check_normal_clone_state(tmp_path) -> None:
    crystalformer = tmp_path / "external" / "CrystalFormer"
    (crystalformer / ".git").mkdir(parents=True)

    summary = check_crystalformer_workspace(
        CrystalFormerWorkspaceCheckConfig(repo_root=tmp_path, create_output_dirs=False)
    )

    assert summary["crystalformer"]["clone_state"] == "normal_clone"
    assert summary["crystalformer"]["is_normal_clone"] is True


def test_workspace_check_submodule_like_state_and_outputs(tmp_path) -> None:
    crystalformer = tmp_path / "external" / "CrystalFormer"
    crystalformer.mkdir(parents=True)
    (crystalformer / ".git").write_text("gitdir: ../../.git/modules/external/CrystalFormer\n", encoding="utf-8")
    output_dir = tmp_path / "workspace_check"

    summary = check_crystalformer_workspace(
        CrystalFormerWorkspaceCheckConfig(repo_root=tmp_path, create_output_dirs=False)
    )
    files = write_workspace_check_outputs(output_dir, summary)

    assert summary["crystalformer"]["clone_state"] == "submodule"
    assert Path(files["json"]).exists()
    assert Path(files["markdown"]).exists()
    saved = json.loads(Path(files["json"]).read_text(encoding="utf-8"))
    assert saved["crystalformer"]["is_submodule"] is True
