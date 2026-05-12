import json
from pathlib import Path

from scripts.build_mace_validation_batch import main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_build_mace_batch_selects_per_formula_with_audit_filters(tmp_path: Path) -> None:
    root = tmp_path / "run" / "smoke" / "crystalformer_audit" / "BaTiO3"
    candidates = [
        {"candidate_id": f"cf_{index}", "composition": "BaTiO3", "metadata": {}, "condition": {"formula": "BaTiO3"}}
        for index in range(4)
    ]
    audit = [
        {
            "candidate_id": "cf_0",
            "composition": "BaTiO3",
            "condition": {"formula": "BaTiO3"},
            "dpo_eligible": True,
            "f1_label": "pass",
            "f2_label": "pass",
            "ranking_score": 0.1,
            "fiir_score": 0.9,
        },
        {
            "candidate_id": "cf_1",
            "composition": "BaTiO3",
            "condition": {"formula": "BaTiO3"},
            "dpo_eligible": True,
            "f1_label": "pass",
            "f2_label": "pass",
            "ranking_score": 0.9,
            "fiir_score": 0.1,
        },
        {
            "candidate_id": "cf_2",
            "composition": "BaTiO3",
            "condition": {"formula": "BaTiO3"},
            "dpo_eligible": False,
            "f1_label": "pass",
            "f2_label": "pass",
            "ranking_score": 1.0,
            "fiir_score": 0.0,
        },
        {
            "candidate_id": "cf_3",
            "composition": "BaTiO3",
            "condition": {"formula": "BaTiO3"},
            "dpo_eligible": True,
            "f1_label": "fail",
            "f2_label": "pass",
            "ranking_score": 0.8,
            "fiir_score": 0.2,
        },
    ]
    _write_jsonl(root / "candidates.jsonl", candidates)
    _write_jsonl(root / "audit_candidates.jsonl", audit)
    output_dir = tmp_path / "batch"

    result = main(
        [
            "--candidate-jsonl",
            str(root / "candidates.jsonl"),
            "--output-dir",
            str(output_dir),
            "--per-formula-limit",
            "2",
            "--require-audit",
            "--require-dpo-eligible",
            "--require-f1-pass",
            "--require-f2-pass",
        ]
    )

    selected = [
        json.loads(line)
        for line in (output_dir / "selected_candidates.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    index_rows = [
        json.loads(line)
        for line in (output_dir / "candidate_index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert result["summary"]["selected_candidate_count"] == 2
    assert [row["candidate_id"] for row in selected] == ["cf_1", "cf_0"]
    assert [row["candidate_id"] for row in index_rows] == ["cf_1", "cf_0"]
    assert result["summary"]["skipped_reason_counts"] == {"f1_not_pass": 1, "not_dpo_eligible": 1}


def test_build_mace_batch_excludes_already_validated_ids(tmp_path: Path) -> None:
    root = tmp_path / "run" / "smoke" / "crystalformer_audit" / "SrTiO3"
    _write_jsonl(
        root / "candidates.jsonl",
        [
            {"candidate_id": "cf_0", "composition": "SrTiO3", "metadata": {}, "condition": {"formula": "SrTiO3"}},
            {"candidate_id": "cf_1", "composition": "SrTiO3", "metadata": {}, "condition": {"formula": "SrTiO3"}},
        ],
    )
    _write_jsonl(
        root / "audit_candidates.jsonl",
        [
            {"candidate_id": "cf_0", "composition": "SrTiO3", "condition": {"formula": "SrTiO3"}},
            {"candidate_id": "cf_1", "composition": "SrTiO3", "condition": {"formula": "SrTiO3"}},
        ],
    )
    validated = tmp_path / "validated.jsonl"
    _write_jsonl(validated, [{"candidate_id": "cf_0", "formula": "SrTiO3"}])

    result = main(
        [
            "--candidate-jsonl",
            str(root / "candidates.jsonl"),
            "--exclude-validation-jsonl",
            str(validated),
            "--output-dir",
            str(tmp_path / "batch"),
        ]
    )

    assert result["summary"]["selected_candidate_count"] == 1
    assert result["summary"]["skipped_reason_counts"] == {"already_validated": 1}


def test_build_mace_batch_records_per_formula_overflow(tmp_path: Path) -> None:
    root = tmp_path / "run" / "smoke" / "crystalformer_audit" / "BaZrO3"
    candidates = [
        {"candidate_id": f"cf_{index}", "composition": "BaZrO3", "metadata": {}, "condition": {"formula": "BaZrO3"}}
        for index in range(3)
    ]
    audit = [
        {
            "candidate_id": f"cf_{index}",
            "composition": "BaZrO3",
            "condition": {"formula": "BaZrO3"},
            "ranking_score": 1.0 - index * 0.1,
        }
        for index in range(3)
    ]
    _write_jsonl(root / "candidates.jsonl", candidates)
    _write_jsonl(root / "audit_candidates.jsonl", audit)

    result = main(
        [
            "--candidate-jsonl",
            str(root / "candidates.jsonl"),
            "--output-dir",
            str(tmp_path / "batch"),
            "--per-formula-limit",
            "1",
            "--require-audit",
        ]
    )

    assert result["summary"]["selected_candidate_count"] == 1
    assert result["summary"]["skipped_reason_counts"] == {"per_formula_limit_overflow": 2}
