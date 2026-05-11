from fiir_crystal.failure import StructureLike
from fiir_crystal.structures import CrystalStructureRecord, read_jsonl, write_jsonl


def _record() -> CrystalStructureRecord:
    return CrystalStructureRecord(
        candidate_id="cf_001",
        species=("Ba", "Ti", "O", "O", "O"),
        frac_coords=(
            (0.0, 0.0, 0.0),
            (0.5, 0.5, 0.5),
            (0.5, 0.5, 0.0),
            (0.5, 0.0, 0.5),
            (0.0, 0.5, 0.5),
        ),
        lattice_matrix=((4.0, 0.0, 0.0), (0.0, 4.0, 0.0), (0.0, 0.0, 4.0)),
        pbc=(True, True, True),
        composition="BaTiO3",
        num_sites=5,
        space_group=221,
        wyckoff_letters=("a", "b", "c", "c", "c"),
        prototype="perovskite",
        structure_ref=None,
        source="deepmodeling/CrystalFormer",
        metadata={"score": "-1.2"},
    )


def test_crystal_structure_record_round_trip_and_validate() -> None:
    record = _record()

    loaded = CrystalStructureRecord.from_dict(record.to_dict())

    assert loaded.validate_basic() == []
    assert loaded.candidate_id == "cf_001"
    assert loaded.species == ("Ba", "Ti", "O", "O", "O")
    assert loaded.metadata["score"] == "-1.2"


def test_structure_record_jsonl_round_trip(tmp_path) -> None:
    path = tmp_path / "candidates.jsonl"

    write_jsonl(path, [_record()])
    loaded = read_jsonl(path)

    assert loaded[0].composition == "BaTiO3"
    assert loaded[0].space_group == 221


def test_structure_record_to_structure_like() -> None:
    structure = _record().to_structure_like()

    assert isinstance(structure, StructureLike)
    assert structure.candidate_id == "cf_001"
    assert structure.composition == "BaTiO3"
    assert structure.num_atoms == 5
    assert structure.lattice_lengths == (4.0, 4.0, 4.0)
    assert structure.lattice_angles == (90.0, 90.0, 90.0)
    assert structure.metadata["stability_mode"] == "unavailable_without_offline_validation"


def test_partial_stub_reports_basic_validation_warnings() -> None:
    record = CrystalStructureRecord(
        candidate_id="stub",
        species=(),
        frac_coords=(),
        lattice_matrix=(),
        pbc=(True, True, True),
        composition=None,
        num_sites=0,
        space_group=None,
        wyckoff_letters=None,
        prototype=None,
        structure_ref="stub.cif",
        source="deepmodeling/CrystalFormer",
    )

    assert record.validate_basic() == []
    assert record.to_structure_like().structure_ref == "stub.cif"
