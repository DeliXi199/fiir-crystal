from fiir_crystal.evaluation.error_audit import audit_candidates, summarize_audit, write_audit_outputs
from fiir_crystal.structures import CrystalStructureRecord


def _record(candidate_id: str, metadata: dict | None = None) -> CrystalStructureRecord:
    return CrystalStructureRecord(
        candidate_id=candidate_id,
        species=("Ba", "Ti", "O", "O", "O"),
        frac_coords=((0, 0, 0), (0.5, 0.5, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)),
        lattice_matrix=((4.0, 0, 0), (0, 4.0, 0), (0, 0, 4.0)),
        pbc=(True, True, True),
        composition="BaTiO3",
        num_sites=5,
        space_group=221,
        wyckoff_letters=("a", "b", "c", "c", "c"),
        prototype="perovskite",
        structure_ref=None,
        source="deepmodeling/CrystalFormer",
        metadata=metadata or {},
    )


def _raw_metadata() -> dict:
    return {
        "source_format": "crystalformer_raw_csv",
        "raw_crystalformer_row": {"g": "221", "W": "abc", "A": "Ba Ti O O O", "X": "coords", "L": "lattice"},
        "raw_sequence_fields": {"g": "221", "W": "abc", "A": "Ba Ti O O O", "X": "coords", "L": "lattice"},
        "formula_condition": "BaTiO3",
        "stability_mode": "unavailable_without_offline_validation",
    }


def test_audit_marks_f3_unknown_and_dpo_eligible_with_raw_sequence() -> None:
    results = audit_candidates([_record("raw_001", _raw_metadata())], formula="BaTiO3")
    summary = summarize_audit(results, candidates=[_record("raw_001", _raw_metadata())], formula="BaTiO3")

    assert results[0].f3_label == "unknown"
    assert results[0].failure_vector["f3_stability"] is None
    assert results[0].dpo_eligible is True
    assert results[0].preference_type == "geometry_chemistry_only"
    assert summary.f3_unknown_count == 1
    assert summary.f3_available_count == 0
    assert summary.parsed_full_structure_count == 1


def test_missing_raw_sequence_is_not_dpo_eligible() -> None:
    metadata = {"source_format": "normalized_jsonl", "formula_condition": "BaTiO3"}

    result = audit_candidates([_record("missing_raw", metadata)], formula="BaTiO3")[0]

    assert result.dpo_eligible is False
    assert "missing_raw_sequence" in result.dpo_ineligible_reasons


def test_parse_error_does_not_stop_audit_and_is_summarized() -> None:
    metadata = _raw_metadata()
    metadata["parse_status"] = "parse_error"
    metadata["parse_error_message"] = "fake parser failure"

    results = audit_candidates([_record("parse_bad", metadata)], formula="BaTiO3")
    summary = summarize_audit(results, candidates=[_record("parse_bad", metadata)], formula="BaTiO3")

    assert results[0].parse_status == "parse_error"
    assert results[0].dpo_eligible is False
    assert "parse_error" in results[0].dpo_ineligible_reasons
    assert summary.parse_error_count == 1
    assert summary.top_parse_errors[0]["reason"] == "fake parser failure"


def test_write_audit_outputs_generates_expected_files(tmp_path) -> None:
    records = [_record("raw_001", _raw_metadata())]
    results = audit_candidates(records, formula="BaTiO3")
    summary = summarize_audit(results, candidates=records, formula="BaTiO3")

    files = write_audit_outputs(tmp_path, records, results, summary)

    for path in files.values():
        assert tmp_path.joinpath(path.split(str(tmp_path) + "/")[-1]).exists()
    assert (tmp_path / "audit_summary.json").exists()
    assert (tmp_path / "report.md").exists()
    assert "not stability validation" in (tmp_path / "report.md").read_text(encoding="utf-8")
