import csv
import subprocess

import pytest

from fiir_crystal.generation.crystalformer_adapter import CrystalFormerAdapter
from fiir_crystal.structures import CrystalStructureRecord, write_jsonl


def _record(candidate_id: str = "jsonl_001") -> CrystalStructureRecord:
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


def test_load_normalized_jsonl(tmp_path) -> None:
    path = tmp_path / "candidates.jsonl"
    write_jsonl(path, [_record()])

    records = CrystalFormerAdapter({"source_format": "normalized_jsonl"}).load_outputs(path)

    assert records[0].candidate_id == "jsonl_001"
    assert records[0].composition == "BaTiO3"


def test_load_fake_raw_sampling_csv(tmp_path) -> None:
    path = tmp_path / "samples.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_id", "g", "W", "A", "X", "L", "formula", "logprob"])
        writer.writeheader()
        writer.writerow(
            {
                "candidate_id": "raw_001",
                "g": "221",
                "W": "['a', 'b', 'c', 'c', 'c']",
                "A": "['Ba', 'Ti', 'O', 'O', 'O']",
                "X": "[[0, 0, 0], [0.5, 0.5, 0.5], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]]",
                "L": "[[4, 0, 0], [0, 4, 0], [0, 0, 4]]",
                "formula": "BaTiO3",
                "logprob": "-2.3",
            }
        )

    records = CrystalFormerAdapter({"source_format": "crystalformer_raw_csv"}).load_outputs(path)

    assert records[0].candidate_id == "raw_001"
    assert records[0].space_group == 221
    assert records[0].species == ("Ba", "Ti", "O", "O", "O")
    assert records[0].metadata["logprob"] == "-2.3"
    assert "mock_stability_score" not in records[0].metadata


def test_load_struct_csv_with_cif_path(tmp_path) -> None:
    cif_path = tmp_path / "raw_001.cif"
    cif_path.write_text("data_raw_001\n", encoding="utf-8")
    csv_path = tmp_path / "struct.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_id", "formula", "cif_path"])
        writer.writeheader()
        writer.writerow({"candidate_id": "struct_001", "formula": "BaTiO3", "cif_path": cif_path.name})

    records = CrystalFormerAdapter({"source_format": "crystalformer_struct_csv"}).load_outputs(csv_path)

    assert records[0].candidate_id == "struct_001"
    assert records[0].structure_ref == str(cif_path)
    assert records[0].metadata["source_format"] == "crystalformer_struct_csv"


def test_load_cif_directory_fallback(tmp_path) -> None:
    (tmp_path / "candidate_a.cif").write_text("data_candidate_a\n", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not a cif\n", encoding="utf-8")

    records = CrystalFormerAdapter({"source_format": "cif_directory"}).load_outputs(tmp_path)

    assert [record.candidate_id for record in records] == ["candidate_a"]
    assert records[0].structure_ref == str(tmp_path / "candidate_a.cif")
    assert records[0].metadata["source_format"] == "cif_directory"


def test_load_manifest_records(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"records": ['
        '{"candidate_id": "manifest_001", "species": ["Ba"], "frac_coords": [[0, 0, 0]], '
        '"lattice_matrix": [[4, 0, 0], [0, 4, 0], [0, 0, 4]], "pbc": [true, true, true], '
        '"composition": "Ba", "num_sites": 1, "space_group": null, "wyckoff_letters": null, '
        '"prototype": null, "structure_ref": null, "source": "deepmodeling/CrystalFormer", "metadata": {}}'
        ']}',
        encoding="utf-8",
    )

    records = CrystalFormerAdapter({"source_format": "manifest"}).load_outputs(manifest)

    assert records[0].candidate_id == "manifest_001"
    assert records[0].metadata["manifest_path"] == str(manifest)


def test_missing_output_dir_has_clear_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="CrystalFormer output path does not exist"):
        CrystalFormerAdapter().load_outputs(tmp_path / "missing")


def test_run_generation_false_does_not_call_subprocess(tmp_path, monkeypatch) -> None:
    path = tmp_path / "candidates.jsonl"
    write_jsonl(path, [_record()])

    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess should not be called")

    monkeypatch.setattr(subprocess, "run", fail_run)
    records = CrystalFormerAdapter({"run_generation": False, "output_dir": str(path)}).generate()

    assert records[0].candidate_id == "jsonl_001"


def test_run_generation_true_calls_mocked_subprocess(tmp_path, monkeypatch) -> None:
    path = tmp_path / "candidates.jsonl"
    write_jsonl(path, [_record("generated_001")])
    calls = []

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = CrystalFormerAdapter(
        {
            "run_generation": True,
            "crystalformer_command": "python fake_crystalformer.py",
            "output_dir": str(path),
        }
    )

    records = adapter.generate()

    assert calls
    assert records[0].candidate_id == "generated_001"
    assert adapter.last_subprocess["stdout"] == "ok"
