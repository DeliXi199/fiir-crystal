from pathlib import Path


def test_dpo_schema_doc_defines_pair_boundary() -> None:
    text = Path("docs/specs/crystalformer_dpo_data_schema.md").read_text(encoding="utf-8")

    for token in [
        '"pair_id"',
        '"condition"',
        '"chosen_candidate_id"',
        '"rejected_candidate_id"',
        '"chosen_sequence"',
        '"rejected_sequence"',
        '"g"',
        '"W"',
        '"A"',
        '"X"',
        '"L"',
        '"preference_type": "geometry_chemistry_only"',
        "Do not pair candidates across formulas",
        "Stability preferences require imported offline validation",
        "DPO training is explicitly out of scope",
        "no_comparable_margin",
    ]:
        assert token in text


def test_dpo_preference_builder_config_is_boundary_only() -> None:
    text = Path("configs/dpo_preference_builder.yaml").read_text(encoding="utf-8")

    assert "outputs/dpo_preferences/BaTiO3" in text
    assert "same_formula_required: true" in text
    assert "require_raw_sequence: true" in text
    assert "build_pairs_in_this_stage: true" in text
    assert "train_dpo_in_this_stage: false" in text
    assert "min_preference_margin: 0.000001" in text
