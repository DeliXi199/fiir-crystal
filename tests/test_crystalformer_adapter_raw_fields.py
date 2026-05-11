import csv

from fiir_crystal.generation.crystalformer_adapter import CrystalFormerAdapter


def test_adapter_preserves_raw_crystalformer_sequence_fields(tmp_path) -> None:
    path = tmp_path / "samples.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "candidate_id",
                "g",
                "W",
                "A",
                "X",
                "L",
                "formula",
                "logprob",
                "temperature",
                "K",
            ],
        )
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
                "temperature": "0.8",
                "K": "40",
            }
        )

    records = CrystalFormerAdapter(
        {
            "source_format": "crystalformer_raw_csv",
            "formula": "BaTiO3",
            "spacegroup": None,
            "source_checkpoint": "external/checkpoints/crystalformer",
        }
    ).load_outputs(path)
    metadata = records[0].metadata

    assert metadata["raw_crystalformer_row"]["g"] == "221"
    assert metadata["raw_sequence_fields"]["g"] == "221"
    assert metadata["raw_sequence_fields"]["W"] == "['a', 'b', 'c', 'c', 'c']"
    assert metadata["raw_g"] == "221"
    assert metadata["raw_W"] == "['a', 'b', 'c', 'c', 'c']"
    assert metadata["raw_A"] == "['Ba', 'Ti', 'O', 'O', 'O']"
    assert metadata["raw_X"].startswith("[[0, 0, 0]")
    assert metadata["raw_L"] == "[[4, 0, 0], [0, 4, 0], [0, 0, 4]]"
    assert metadata["raw_sequence_status"] == "full"
    assert metadata["missing_sequence_fields"] == []
    assert metadata["sampling_metadata"]["logprob"] == "-2.3"
    assert metadata["sampling_metadata"]["K"] == "40"
    assert metadata["source_model"] == "deepmodeling/CrystalFormer"
    assert metadata["source_checkpoint"] == "external/checkpoints/crystalformer"
    assert metadata["formula_condition"] == "BaTiO3"
    assert metadata["temperature"] == "0.8"
    assert metadata["top_k"] == "40"
    assert metadata["K"] == "40"
    assert metadata["original_row_index"] == 1
    assert metadata["source_format"] == "crystalformer_raw_csv"


def test_adapter_marks_missing_raw_sequence_fields(tmp_path) -> None:
    path = tmp_path / "output_BaTiO3_struct.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_id", "formula", "cif_path"])
        writer.writeheader()
        writer.writerow({"candidate_id": "struct_001", "formula": "BaTiO3", "cif_path": "struct_001.cif"})

    records = CrystalFormerAdapter({"source_format": "crystalformer_struct_csv"}).load_outputs(path)
    metadata = records[0].metadata

    assert metadata["raw_sequence_status"] == "missing"
    assert metadata["missing_sequence_fields"] == ["g", "W", "A", "X", "L"]
    assert metadata["raw_sequence_fields"] == {"g": None, "W": None, "A": None, "X": None, "L": None}
