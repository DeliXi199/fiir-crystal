import json
from pathlib import Path

from scripts import check_dpo_offline_validation_ready as check


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_readiness_passes_when_all_files_exist_with_expected_rows(tmp_path: Path) -> None:
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    output = tmp_path / "summary.json"
    _write_jsonl(left, [{"candidate_id": "a"}, {"candidate_id": "b"}])
    _write_jsonl(right, [{"candidate_id": "c"}, {"candidate_id": "d"}])

    summary = check.main(
        [
            "--validation",
            f"left={left}",
            "--validation",
            f"right={right}",
            "--expected-rows",
            "2",
            "--output-json",
            str(output),
        ]
    )

    assert summary["ready"] is True
    assert output.exists()
    assert {row["row_count"] for row in summary["validations"]} == {2}


def test_readiness_fails_for_missing_or_wrong_row_count(tmp_path: Path) -> None:
    present = tmp_path / "present.jsonl"
    missing = tmp_path / "missing.jsonl"
    _write_jsonl(present, [{"candidate_id": "a"}])

    summary = check.main(
        [
            "--validation",
            f"present={present}",
            "--validation",
            f"missing={missing}",
            "--expected-rows",
            "2",
        ]
    )

    assert summary["ready"] is False
    issues = {row["label"]: row["issue"] for row in summary["validations"]}
    assert issues == {"present": "row_count_mismatch", "missing": "missing"}
