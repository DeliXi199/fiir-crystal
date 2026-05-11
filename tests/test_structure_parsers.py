from fiir_crystal.structures.parsers import (
    parse_cif_file_optional,
    parse_cif_text_optional,
    parse_struct_csv_row,
)


FAKE_CIF = """data_fake_batio3
_symmetry_space_group_name_H-M 'P 1'
_cell_length_a 4
_cell_length_b 4
_cell_length_c 4
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
"""


def test_parse_cif_text_none_returns_unparsed_fallback() -> None:
    record = parse_cif_text_optional(FAKE_CIF, parser_backend="none")

    assert record.candidate_id == "fake_batio3"
    assert record.metadata["parse_status"] == "unparsed_cif"
    assert record.metadata["parser_backend"] == "none"
    assert record.metadata["raw_sequence_status"] == "missing"


def test_parse_cif_file_none_returns_path_fallback(tmp_path) -> None:
    path = tmp_path / "candidate.cif"
    path.write_text(FAKE_CIF, encoding="utf-8")

    record = parse_cif_file_optional(path, parser_backend="none")

    assert record.candidate_id == "candidate"
    assert record.structure_ref == str(path)
    assert record.metadata["parse_status"] == "unparsed_cif"


def test_parse_cif_missing_file_becomes_parse_error(tmp_path) -> None:
    record = parse_cif_file_optional(tmp_path / "missing.cif", parser_backend="none")

    assert record.metadata["parse_status"] == "parse_error"
    assert record.metadata["parse_error_type"] == "FileNotFoundError"


def test_parse_struct_csv_row_preserves_raw_row_and_sequence() -> None:
    record = parse_struct_csv_row(
        {
            "candidate_id": "struct_001",
            "formula": "BaTiO3",
            "g": "221",
            "W": "abc",
            "A": "Ba Ti O O O",
            "X": "0 0 0; 0.5 0.5 0.5; 0.5 0.5 0; 0.5 0 0.5; 0 0.5 0.5",
            "L": "4 0 0 0 4 0 0 0 4",
        }
    )

    assert record.metadata["raw_crystalformer_row"]["g"] == "221"
    assert record.metadata["raw_sequence_status"] == "full"
    assert record.metadata["parse_status"] == "parsed_full_structure"
    assert record.species == ("Ba", "Ti", "O", "O", "O")
