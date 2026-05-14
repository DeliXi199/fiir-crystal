import json

from fiir_crystal.dpo import PreferenceBuildConfig, build_dpo_preferences


def _audit_row(
    candidate_id: str,
    score: float,
    *,
    raw: bool = True,
    formula: str = "BaTiO3",
    spacegroup=None,
    generation=None,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "source_format": "crystalformer_raw_csv",
        "parse_status": "parsed_full_structure",
        "raw_sequence_status": "full" if raw else "missing",
        "f1_label": "pass" if score < 0.1 else "fail",
        "f2_label": "pass",
        "f3_label": "unknown",
        "failure_vector": {
            "candidate_id": candidate_id,
            "f1_geometry": score,
            "f2_chemistry": 0.0,
            "f3_stability": None,
        },
        "evidence": {},
        "fiir_score": score,
        "ranking_score": 1.0 - score,
        "dpo_eligible": raw,
        "dpo_ineligible_reasons": [] if raw else ["missing_raw_sequence"],
        "preference_type": "geometry_chemistry_only" if raw else None,
        "condition": {
            "mode": "csp",
            "formula": formula,
            "spacegroup": spacegroup,
            "generation": generation or {},
        },
        "raw_sequence_fields": (
            {"g": "221", "W": "W" + candidate_id, "A": "A" + candidate_id, "X": "X" + candidate_id, "L": "L" + candidate_id}
            if raw
            else {"g": None, "W": None, "A": None, "X": None, "L": None}
        ),
    }


def test_build_dpo_preferences_emits_schema_pair_for_margin() -> None:
    rows = [_audit_row("good", 0.0), _audit_row("bad", 0.4)]

    pairs, summary = build_dpo_preferences(rows, PreferenceBuildConfig(formula="BaTiO3"))

    assert summary.pair_count == 1
    pair = pairs[0].to_dict()
    assert pair["chosen_candidate_id"] == "good"
    assert pair["rejected_candidate_id"] == "bad"
    assert pair["chosen_sequence"]["g"] == "221"
    assert pair["rejected_sequence"]["A"] == "Abad"
    assert pair["preference_margin"] == 0.4
    assert pair["preference_type"] == "geometry_chemistry_only"
    assert "f3_unavailable_geometry_chemistry_only" in pair["preference_reason"]
    assert pair["metadata"]["dpo_training"] is False
    assert summary.stability_preferences is False


def test_build_dpo_preferences_filters_missing_raw_sequence() -> None:
    rows = [_audit_row("good", 0.0), _audit_row("bad", 0.4, raw=False)]

    pairs, summary = build_dpo_preferences(rows, PreferenceBuildConfig(formula="BaTiO3"))

    assert pairs == []
    assert summary.usable_candidate_count == 1
    assert summary.skip_reasons["not_dpo_eligible"] == 1


def test_build_dpo_preferences_does_not_cross_formula() -> None:
    rows = [_audit_row("batio3", 0.0, formula="BaTiO3"), _audit_row("srtio3", 0.4, formula="SrTiO3")]

    pairs, summary = build_dpo_preferences(rows, PreferenceBuildConfig())

    assert pairs == []
    assert summary.condition_count == 2
    assert summary.skip_reasons["condition_group_too_small"] == 2
    assert summary.skip_reasons["different_formula_condition"] == 1


def test_build_dpo_preferences_does_not_cross_spacegroup_condition() -> None:
    rows = [
        _audit_row("sg_221", 0.0, spacegroup=221),
        _audit_row("sg_62", 0.4, spacegroup=62),
    ]

    pairs, summary = build_dpo_preferences(rows, PreferenceBuildConfig(formula="BaTiO3"))

    assert pairs == []
    assert summary.condition_count == 2
    assert summary.skip_reasons["different_spacegroup_condition"] == 1


def test_build_dpo_preferences_does_not_cross_generation_condition() -> None:
    rows = [
        _audit_row("temp_1", 0.0, generation={"temperature": "1.0", "top_k": "40"}),
        _audit_row("temp_2", 0.4, generation={"temperature": "2.0", "top_k": "40"}),
    ]

    pairs, summary = build_dpo_preferences(rows, PreferenceBuildConfig(formula="BaTiO3"))

    assert pairs == []
    assert summary.condition_count == 2
    assert summary.skip_reasons["different_generation_condition"] == 1


def test_build_dpo_preferences_records_no_comparable_margin() -> None:
    rows = [_audit_row("a", 0.0), _audit_row("b", 0.0)]

    pairs, summary = build_dpo_preferences(rows, PreferenceBuildConfig(formula="BaTiO3"))

    assert pairs == []
    assert summary.pair_count == 0
    assert summary.skip_reasons["no_comparable_margin"] == 1


def test_build_dpo_preferences_converts_ranking_score_to_failure_score() -> None:
    good = _audit_row("good", 0.0)
    bad = _audit_row("bad", 0.4)
    del good["fiir_score"]
    del bad["fiir_score"]

    pairs, summary = build_dpo_preferences([good, bad], PreferenceBuildConfig(formula="BaTiO3"))

    assert summary.pair_count == 1
    pair = pairs[0].to_dict()
    assert pair["chosen_candidate_id"] == "good"
    assert pair["rejected_candidate_id"] == "bad"
    assert pair["chosen_score"] == 0.0
    assert pair["rejected_score"] == 0.4


def test_pair_is_json_serializable() -> None:
    pairs, _ = build_dpo_preferences([_audit_row("good", 0.0), _audit_row("bad", 0.2)])

    payload = json.dumps(pairs[0].to_dict(), sort_keys=True)

    assert '"chosen_sequence"' in payload
    assert '"rejected_sequence"' in payload
