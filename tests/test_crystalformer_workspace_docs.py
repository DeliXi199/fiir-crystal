from pathlib import Path


def test_workspace_setup_doc_contains_required_modes_and_paths() -> None:
    text = Path("docs/setup/crystalformer_workspace.md").read_text(encoding="utf-8")

    assert "deepmodeling/CrystalFormer" in text
    assert "external/CrystalFormer/" in text
    assert "external/checkpoints/" in text
    assert "outputs/crystalformer_raw/" in text
    assert "outputs/crystalformer_run/" in text
    assert "outputs/crystalformer_audit/" in text
    assert "outputs/dpo_preferences/" in text
    assert "git clone https://github.com/deepmodeling/CrystalFormer external/CrystalFormer" in text
    assert "git submodule add <your-fork-or-upstream-url> external/CrystalFormer" in text
    assert 'pip install -U "jax[cpu]"' in text
    assert "scripts/audit_crystalformer_outputs.py" in text
    assert "no candidate is reported as stable" in text


def test_gitignore_keeps_heavy_crystalformer_artifacts_out() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    for pattern in [
        "external/CrystalFormer/.venv/",
        "external/CrystalFormer/outputs/",
        "external/CrystalFormer/checkpoints/",
        "external/CrystalFormer/wandb/",
        "external/CrystalFormer/runs/",
        "external/CrystalFormer/logs/",
        "external/checkpoints/",
        "outputs/crystalformer_raw/",
        "outputs/crystalformer_run/",
        "outputs/crystalformer_audit/",
        "outputs/dpo_preferences/",
    ]:
        assert pattern in text

    assert "external/CrystalFormer/" not in [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
