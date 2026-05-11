import subprocess
import sys

from fiir_crystal.config import load_experiment_config
from fiir_crystal.experiment import run_fiir_experiment
from fiir_crystal.failure import FailureOracle
from fiir_crystal.io import read_mock_candidates_jsonl
from fiir_crystal.structures import CrystalStructureRecord, write_jsonl


def _external_record(candidate_id: str) -> CrystalStructureRecord:
    return CrystalStructureRecord(
        candidate_id=candidate_id,
        species=("Ba", "Ti", "O", "O", "O"),
        frac_coords=((0, 0, 0), (0.5, 0.5, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)),
        lattice_matrix=((4.0, 0, 0), (0, 4.0, 0), (0, 0, 4.0)),
        pbc=(True, True, True),
        composition="BaTiO3",
        num_sites=5,
        space_group=221,
        wyckoff_letters=None,
        prototype="perovskite",
        structure_ref=None,
        source="deepmodeling/CrystalFormer",
        metadata={"source_format": "normalized_jsonl"},
    )


def test_standard_candidates_jsonl_enters_existing_fiir_pipeline(tmp_path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    write_jsonl(candidates, [_external_record("cf_a"), _external_record("cf_b")])

    config = load_experiment_config(
        None,
        overrides={"input_path": str(candidates), "output_dir": str(tmp_path / "fiir"), "top_k": 2},
    )
    result = run_fiir_experiment(config)

    assert result["summary"]["candidate_count"] == 2
    assert (tmp_path / "fiir" / "report.md").exists()
    assert result["evaluation_report"].validation_metrics_available is False


def test_external_record_to_structure_like_marks_f3_unavailable_low_confidence(tmp_path) -> None:
    path = tmp_path / "candidates.jsonl"
    write_jsonl(path, [_external_record("cf_unvalidated")])
    structure = read_mock_candidates_jsonl(path)[0]

    label = FailureOracle.default().label_structure(structure)

    assert label.f3_stability == 0.5
    assert label.is_stable is False
    assert label.calibration_tier == 1
    assert label.confidence == 0.5
    assert label.metadata["stability"]["source"] == "unavailable_without_offline_validation"
    assert "unavailable_reason" in label.metadata["stability"]


def test_existing_mock_loop_scripts_still_run(tmp_path) -> None:
    loop = subprocess.run(
        [sys.executable, "scripts/run_mock_fiir_loop.py", "--quiet"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert loop.returncode == 0, loop.stderr

    active = subprocess.run(
        [
            sys.executable,
            "scripts/run_mock_active_loop.py",
            "--rounds",
            "1",
            "--output-dir",
            str(tmp_path / "active"),
            "--quiet",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert active.returncode == 0, active.stderr
