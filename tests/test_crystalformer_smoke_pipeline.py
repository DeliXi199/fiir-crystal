import json
import sys
from pathlib import Path

import pytest

from scripts.run_crystalformer_smoke_pipeline import main


FAKE_RAW_DIR = Path("examples/crystalformer_raw/BaTiO3_fake")


def test_smoke_pipeline_load_only_fake_outputs(tmp_path) -> None:
    output_root = tmp_path / "smoke"

    result = main(
        [
            "--input-dir",
            str(FAKE_RAW_DIR),
            "--formula",
            "BaTiO3",
            "--output-root",
            str(output_root),
            "--parser-backend",
            "none",
            "--stability-mode",
            "unavailable_without_offline_validation",
        ]
    )

    summary = result["summary"]
    assert summary["candidate_count"] == 5
    assert summary["f3_status_counts"] == {"unknown": 5}
    assert summary["f3_validation"] == "unavailable"
    assert summary["dpo_eligible_count"] == 3
    assert summary["preference_pair_count"] >= 1
    assert summary["preference_skip_reasons"]["no_comparable_margin"] == 1
    assert (output_root / "crystalformer_audit" / "BaTiO3" / "audit_summary.json").exists()
    assert (output_root / "dpo_preferences" / "BaTiO3" / "preference_summary.json").exists()


def test_explicit_command_without_run_generation_does_not_execute(tmp_path) -> None:
    marker = tmp_path / "marker.txt"
    fake_command = tmp_path / "fake_generate.py"
    fake_command.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "smoke"

    result = main(
        [
            "--input-dir",
            str(FAKE_RAW_DIR),
            "--formula",
            "BaTiO3",
            "--output-root",
            str(output_root),
            "--parser-backend",
            "none",
            "--crystalformer-command",
            f"{sys.executable} {fake_command}",
            "--crystalformer-work-dir",
            str(tmp_path),
        ]
    )

    assert not marker.exists()
    provenance = json.loads(Path(result["files"]["provenance"]).read_text(encoding="utf-8"))
    assert provenance["generation"]["executed"] is False
    assert provenance["generation"]["command_present"] is True


def test_run_generation_requires_command(tmp_path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--input-dir",
                str(FAKE_RAW_DIR),
                "--formula",
                "BaTiO3",
                "--output-root",
                str(tmp_path / "smoke"),
                "--run-generation",
                "--crystalformer-work-dir",
                str(tmp_path),
            ]
        )

    assert "--run-generation requires --crystalformer-command" in str(exc.value)


def test_fake_generation_command_records_provenance(tmp_path) -> None:
    marker = tmp_path / "marker.txt"
    fake_command = tmp_path / "fake_generate.py"
    fake_command.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')",
                "print('fake generation complete')",
            ]
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "smoke"

    result = main(
        [
            "--input-dir",
            str(FAKE_RAW_DIR),
            "--formula",
            "BaTiO3",
            "--output-root",
            str(output_root),
            "--parser-backend",
            "none",
            "--crystalformer-command",
            f"{sys.executable} {fake_command}",
            "--crystalformer-work-dir",
            str(tmp_path),
            "--run-generation",
        ]
    )

    assert marker.read_text(encoding="utf-8") == "ran"
    provenance = json.loads(Path(result["files"]["provenance"]).read_text(encoding="utf-8"))
    assert provenance["generation"]["executed"] is True
    assert provenance["generation"]["returncode"] == 0
    assert "fake generation complete" in provenance["generation"]["stdout"]
    assert provenance["generation"]["cwd"] == str(tmp_path)


def test_smoke_pipeline_never_marks_stable_without_f3_validation(tmp_path) -> None:
    output_root = tmp_path / "smoke"

    main(
        [
            "--input-dir",
            str(FAKE_RAW_DIR),
            "--formula",
            "BaTiO3",
            "--output-root",
            str(output_root),
            "--parser-backend",
            "none",
        ]
    )

    audit_path = output_root / "crystalformer_audit" / "BaTiO3" / "audit_candidates.jsonl"
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert rows
    assert {row["f3_label"] for row in rows} == {"unknown"}
    assert all(row["evidence"]["f3_status"] == "unknown_unavailable" for row in rows)
