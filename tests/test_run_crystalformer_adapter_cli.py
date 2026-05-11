import json

from scripts.run_crystalformer_adapter import main


def test_run_crystalformer_adapter_cli_with_fake_jsonl(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "candidates.jsonl").write_text(
        json.dumps(
            {
                "candidate_id": "cli_001",
                "species": ["Ba", "Ti", "O", "O", "O"],
                "frac_coords": [[0, 0, 0], [0.5, 0.5, 0.5], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]],
                "lattice_matrix": [[4, 0, 0], [0, 4, 0], [0, 0, 4]],
                "pbc": [True, True, True],
                "composition": "BaTiO3",
                "num_sites": 5,
                "space_group": 221,
                "wyckoff_letters": None,
                "prototype": "perovskite",
                "structure_ref": None,
                "source": "deepmodeling/CrystalFormer",
                "metadata": {"source_format": "normalized_jsonl"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "generation:",
                "  backend: crystalformer",
                "  run_generation: false",
                "  crystalformer_work_dir: null",
                "  crystalformer_command: null",
                f"  output_dir: {raw_dir}",
                "  normalized_output: unused/candidates.jsonl",
                "  source_format: auto",
                "screening:",
                "  use_existing_failure_oracle: true",
                "  stability_mode: unavailable_without_offline_validation",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "adapter_run"

    summary = main(["--config", str(config), "--output-dir", str(output_dir), "--formula", "BaTiO3"])

    assert summary["candidate_count"] == 1
    assert (output_dir / "candidates.jsonl").exists()
    assert (output_dir / "adapter_summary.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "fiir_run" / "report.md").exists()
    assert "F3 stability is unavailable" in (output_dir / "report.md").read_text(encoding="utf-8")


def test_run_crystalformer_adapter_dry_run(tmp_path, capsys) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "generation:",
                "  backend: crystalformer",
                "  run_generation: true",
                "  crystalformer_work_dir: null",
                "  crystalformer_command: python fake.py",
                "  output_dir: raw",
                "  normalized_output: out/candidates.jsonl",
                "  source_format: auto",
            ]
        ),
        encoding="utf-8",
    )

    summary = main(["--config", str(config), "--output-dir", str(tmp_path / "out"), "--dry-run"])

    captured = capsys.readouterr()
    assert "CrystalFormer adapter dry run" in captured.out
    assert summary["dry_run"] is True
    assert not (tmp_path / "out" / "candidates.jsonl").exists()
