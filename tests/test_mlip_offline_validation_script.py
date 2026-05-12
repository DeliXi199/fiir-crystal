import json
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

from scripts import run_mlip_offline_validation as mlip_runner


def _candidate() -> dict:
    return {
        "candidate_id": "cf_001",
        "composition": "BaTiO3",
        "species": ["Ba", "Ti", "O", "O", "O"],
        "frac_coords": [[0, 0, 0], [0.5, 0.5, 0.5], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]],
        "lattice_matrix": [[4, 0, 0], [0, 4, 0], [0, 0, 4]],
        "condition": {"formula": "BaTiO3", "mode": "csp", "generation": {"top_k": "40"}},
    }


def test_chgnet_dry_run_writes_no_fabricated_f3(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    output_dir = tmp_path / "chgnet"
    candidates.write_text(json.dumps(_candidate(), sort_keys=True) + "\n", encoding="utf-8")

    result = mlip_runner.main(
        [
            "--mlip-kind",
            "chgnet",
            "--candidates-jsonl",
            str(candidates),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )

    rows = [json.loads(line) for line in (output_dir / "chgnet_validation_results.jsonl").read_text().splitlines()]
    assert result["summary"]["runs_mlip"] is False
    assert result["summary"]["workflow"] == "chgnet_offline_validation"
    assert rows[0]["validator"] == "chgnet_0_3_0"
    assert rows[0]["validation_status"] == "planned_not_executed"
    assert rows[0]["energy_above_hull"] is None
    assert rows[0]["is_stable"] is None
    assert rows[0]["metadata"]["mlip_kind"] == "chgnet"
    assert rows[0]["metadata"]["energy_above_hull_status"] == "unavailable_without_local_hull_reference"


def test_matgl_dry_run_uses_explicit_boundary_without_loading_optional_packages(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    output_dir = tmp_path / "matgl"
    candidates.write_text(json.dumps(_candidate(), sort_keys=True) + "\n", encoding="utf-8")

    result = mlip_runner.main(
        [
            "--mlip-kind",
            "matgl",
            "--candidates-jsonl",
            str(candidates),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )

    rows = [json.loads(line) for line in (output_dir / "matgl_validation_results.jsonl").read_text().splitlines()]
    assert result["summary"]["runs_mlip"] is False
    assert result["summary"]["workflow"] == "matgl_offline_validation"
    assert rows[0]["validator"] == "matgl_m3gnet"
    assert rows[0]["metadata"]["downloads"] is False


def test_matgl_real_run_requires_local_model_path(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(json.dumps(_candidate(), sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="requires --model-path"):
        mlip_runner.main(
            [
                "--mlip-kind",
                "matgl",
                "--candidates-jsonl",
                str(candidates),
                "--output-dir",
                str(tmp_path / "matgl"),
                "--limit",
                "1",
            ]
        )


def test_matgl_runtime_moves_loaded_potential_to_requested_device(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_path = tmp_path / "matgl_model"
    model_path.mkdir()
    output_dir = tmp_path / "matgl_output"
    load_calls = []

    class FakePotential:
        def __init__(self) -> None:
            self.to_calls = []

        def to(self, device: str) -> "FakePotential":
            self.to_calls.append(device)
            return self

    class FakePESCalculator:
        def __init__(self, potential: FakePotential) -> None:
            self.potential = potential

    potential = FakePotential()
    matgl_module = types.ModuleType("matgl")
    matgl_module.__version__ = "test"

    def load_model(path: str, device: str | None = None) -> FakePotential:
        load_calls.append({"path": path, "device": device})
        return potential

    matgl_module.load_model = load_model  # type: ignore[attr-defined]
    torch_module = types.ModuleType("torch")
    torch_module.__version__ = "test"
    ext_module = types.ModuleType("matgl.ext")
    ase_module = types.ModuleType("matgl.ext.ase")
    ase_module.PESCalculator = FakePESCalculator  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "matgl", matgl_module)
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "matgl.ext", ext_module)
    monkeypatch.setitem(sys.modules, "matgl.ext.ase", ase_module)

    runtime = mlip_runner._load_matgl_runtime(
        Namespace(model_path=str(model_path), output_dir=str(output_dir), device="cuda")
    )

    assert load_calls == [{"path": str(model_path), "device": "cuda"}]
    assert potential.to_calls == ["cuda"]
    assert runtime["actual_device"] == "cuda"
    assert runtime["calc"].potential is potential
