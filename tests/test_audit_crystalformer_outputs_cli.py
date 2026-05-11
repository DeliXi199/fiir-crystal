import csv
import json

from scripts.audit_crystalformer_outputs import main


def test_audit_crystalformer_outputs_cli_with_fake_raw_csv(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    csv_path = raw_dir / "samples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_id", "g", "W", "A", "X", "L", "formula"])
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
            }
        )
    output_dir = tmp_path / "audit"

    result = main(
        [
            "--input-dir",
            str(raw_dir),
            "--formula",
            "BaTiO3",
            "--output-dir",
            str(output_dir),
            "--parser-backend",
            "none",
            "--stability-mode",
            "unavailable_without_offline_validation",
        ]
    )

    assert result["summary"]["total_candidates"] == 1
    assert (output_dir / "candidates.jsonl").exists()
    assert (output_dir / "audit_candidates.jsonl").exists()
    assert (output_dir / "audit_summary.json").exists()
    assert (output_dir / "failure_vectors.jsonl").exists()
    assert (output_dir / "error_audit_table.md").exists()
    assert (output_dir / "report.md").exists()
    summary = json.loads((output_dir / "audit_summary.json").read_text(encoding="utf-8"))
    assert summary["f3_unknown_count"] == 1
    audit_row = json.loads((output_dir / "audit_candidates.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert audit_row["dpo_eligible"] is True
    assert audit_row["dpo_ineligible_reasons"] == []


def test_audit_cli_with_fake_output_struct_csv_generates_summary(tmp_path) -> None:
    raw_dir = tmp_path / "raw_struct"
    raw_dir.mkdir()
    (raw_dir / "struct_001.cif").write_text("data_struct_001\n", encoding="utf-8")
    csv_path = raw_dir / "output_BaTiO3_struct.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_id", "formula", "cif_path"])
        writer.writeheader()
        writer.writerow({"candidate_id": "struct_001", "formula": "BaTiO3", "cif_path": "struct_001.cif"})
    output_dir = tmp_path / "audit_struct"

    result = main(
        [
            "--input-dir",
            str(raw_dir),
            "--formula",
            "BaTiO3",
            "--output-dir",
            str(output_dir),
            "--parser-backend",
            "none",
        ]
    )

    assert result["summary"]["total_candidates"] == 1
    assert result["summary"]["unparsed_cif_count"] == 1
    assert result["summary"]["f3_unknown_count"] == 1
    assert (output_dir / "report.md").exists()


def test_audit_cli_dry_run_does_not_write_outputs(tmp_path, capsys) -> None:
    output_dir = tmp_path / "dry"

    summary = main(
        [
            "--input-dir",
            str(tmp_path / "raw"),
            "--formula",
            "BaTiO3",
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert "CrystalFormer smoke audit dry run" in captured.out
    assert summary["dry_run"] is True
    assert not output_dir.exists()
