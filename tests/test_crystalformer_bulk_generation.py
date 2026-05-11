import json
from pathlib import Path

import pytest

from scripts.run_crystalformer_bulk_generation import main


def _config(tmp_path: Path, *, fail_formula: str | None = None) -> Path:
    command = (
        "python examples/crystalformer_bulk/fake_generate.py "
        "--formula {formula} "
        "--num-samples {num_samples} "
        "--top-k {top_k} "
        "--output-dir {raw_output_dir}"
    )
    if fail_formula:
        command += f" --fail-formula {fail_formula}"
    config = {
        "crystalformer_work_dir": ".",
        "checkpoint_dir": "external/checkpoints",
        "output_root": str(tmp_path / "bulk"),
        "parser_backend": "none",
        "stability_mode": "unavailable_without_offline_validation",
        "skip_existing": True,
        "defaults": {"num_samples": 2, "top_k": 40},
        "command_template": command,
        "formulas": [
            {"formula": "BaTiO3", "num_samples": 2},
            {"formula": "SrTiO3", "num_samples": 2},
        ],
    }
    path = tmp_path / "bulk_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_bulk_generation_dry_run_only_writes_plan(tmp_path) -> None:
    config = _config(tmp_path)
    output_root = tmp_path / "dry"

    result = main(["--config", str(config), "--output-root", str(output_root)])

    assert result["summary"]["status_counts"] == {"planned": 2}
    assert result["summary"]["total_candidates"] == 0
    assert not (output_root / "crystalformer_raw" / "BaTiO3" / "samples.csv").exists()
    plan = json.loads((output_root / "bulk_plan.json").read_text(encoding="utf-8"))
    assert plan["items"][0]["command"]


def test_bulk_generation_validate_only_checks_config_without_generation(tmp_path) -> None:
    config = _config(tmp_path)
    output_root = tmp_path / "validate"

    result = main(["--config", str(config), "--output-root", str(output_root), "--validate-only"])

    summary = result["summary"]
    assert summary["validate_only"] is True
    assert summary["ready_for_generation"] is True
    assert summary["formula_count"] == 2
    assert summary["total_num_samples"] == 4
    assert (output_root / "bulk_validation_summary.json").exists()
    assert not (output_root / "crystalformer_raw" / "BaTiO3" / "samples.csv").exists()


def test_real_example_config_validate_only_is_template_safe(tmp_path) -> None:
    output_root = tmp_path / "real_validate"

    result = main(
        [
            "--config",
            "configs/crystalformer_bulk_generation.real.example.json",
            "--output-root",
            str(output_root),
            "--validate-only",
        ]
    )

    summary = result["summary"]
    assert summary["validate_only"] is True
    assert summary["formula_count"] == 1
    assert summary["total_num_samples"] == 5
    assert summary["items"][0]["formula"] == "BaTiO3"
    assert "python ./main.py" in summary["items"][0]["command"]
    assert summary["items"][0]["command"].endswith("/output.csv")
    assert Path(summary["items"][0]["raw_output_dir"]).is_absolute()
    assert str(Path("external/checkpoints/crystalformer/alex20s_csp").resolve()) in summary["items"][0]["command"]
    assert "checkpoint_dir_referenced_by_template" in summary["workspace"]
    assert "checkpoint_file_count" in summary["workspace"]


def test_real_batio3_n20_example_config_validate_only_is_template_safe(tmp_path) -> None:
    output_root = tmp_path / "real_n20_validate"

    result = main(
        [
            "--config",
            "configs/crystalformer_bulk_generation.real_batio3_n20.example.json",
            "--output-root",
            str(output_root),
            "--validate-only",
        ]
    )

    summary = result["summary"]
    assert summary["validate_only"] is True
    assert summary["formula_count"] == 1
    assert summary["total_num_samples"] == 20
    assert summary["items"][0]["formula"] == "BaTiO3"
    assert summary["items"][0]["command"].endswith("/output.csv")


def test_real_perovskite_3x20_example_config_validate_only_is_template_safe(tmp_path) -> None:
    output_root = tmp_path / "real_perovskite_validate"

    result = main(
        [
            "--config",
            "configs/crystalformer_bulk_generation.real_perovskite_3x20.example.json",
            "--output-root",
            str(output_root),
            "--validate-only",
        ]
    )

    summary = result["summary"]
    assert summary["validate_only"] is True
    assert summary["formula_count"] == 3
    assert summary["total_num_samples"] == 60
    assert [item["formula"] for item in summary["items"]] == ["BaTiO3", "SrTiO3", "CaTiO3"]


def test_real_perovskite_10x20_example_config_validate_only_is_template_safe(tmp_path) -> None:
    output_root = tmp_path / "real_perovskite_10x20_validate"

    result = main(
        [
            "--config",
            "configs/crystalformer_bulk_generation.real_perovskite_10x20.example.json",
            "--output-root",
            str(output_root),
            "--validate-only",
        ]
    )

    summary = result["summary"]
    assert summary["validate_only"] is True
    assert summary["formula_count"] == 10
    assert summary["total_num_samples"] == 200
    assert [item["num_samples"] for item in summary["items"]] == [20] * 10
    assert summary["items"][0]["formula"] == "BaTiO3"
    assert summary["items"][-1]["formula"] == "PbTiO3"


def test_validate_only_reports_missing_referenced_checkpoint_as_blocking(tmp_path) -> None:
    work_dir = tmp_path / "CrystalFormer"
    work_dir.mkdir()
    config = {
        "crystalformer_work_dir": str(work_dir),
        "checkpoint_dir": str(tmp_path / "missing_checkpoint"),
        "command_template": (
            "python ./main.py --restore_path {checkpoint_dir} "
            "--formula {formula} --save_path {raw_output_dir}"
        ),
        "formulas": [{"formula": "BaTiO3", "num_samples": 1}],
    }
    path = tmp_path / "real_missing_checkpoint.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    result = main(["--config", str(path), "--output-root", str(tmp_path / "validate"), "--validate-only"])

    assert result["summary"]["ready_for_generation"] is False
    assert any(reason.startswith("checkpoint_dir_missing:") for reason in result["summary"]["blocking_reasons"])


def test_validate_only_reports_empty_referenced_checkpoint_dir_as_blocking(tmp_path) -> None:
    work_dir = tmp_path / "CrystalFormer"
    checkpoint_dir = tmp_path / "empty_checkpoint"
    work_dir.mkdir()
    checkpoint_dir.mkdir()
    config = {
        "crystalformer_work_dir": str(work_dir),
        "checkpoint_dir": str(checkpoint_dir),
        "command_template": (
            "python ./main.py --restore_path {checkpoint_dir} "
            "--formula {formula} --save_path {raw_output_dir}/output.csv"
        ),
        "formulas": [{"formula": "BaTiO3", "num_samples": 1}],
    }
    path = tmp_path / "real_empty_checkpoint.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    result = main(["--config", str(path), "--output-root", str(tmp_path / "validate"), "--validate-only"])

    assert result["summary"]["ready_for_generation"] is False
    assert any(reason.startswith("checkpoint_file_missing:") for reason in result["summary"]["blocking_reasons"])


def test_command_template_missing_required_fields_errors(tmp_path) -> None:
    config = {
        "crystalformer_work_dir": ".",
        "command_template": "python ./main.py --formula {formula}",
        "formulas": [{"formula": "BaTiO3", "num_samples": 1}],
    }
    path = tmp_path / "bad_template.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(SystemExit, match="raw_output_dir"):
        main(["--config", str(path), "--output-root", str(tmp_path / "validate"), "--validate-only"])


def test_validate_only_cannot_be_combined_with_run_generation(tmp_path) -> None:
    config = _config(tmp_path)

    with pytest.raises(SystemExit, match="validate-only"):
        main(["--config", str(config), "--validate-only", "--run-generation"])


def test_bulk_generation_run_generation_executes_fake_and_smoke(tmp_path) -> None:
    config = _config(tmp_path)
    output_root = tmp_path / "run"

    result = main(
        [
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--run-generation",
            "--no-skip-existing",
        ]
    )

    summary = result["summary"]
    assert summary["status_counts"] == {"succeeded": 2}
    assert summary["total_candidates"] == 4
    assert summary["total_dpo_eligible"] == 4
    assert summary["timing"]["total_wall_seconds"] >= 0
    assert summary["timing"]["generation_seconds_total"] >= 0
    assert summary["timing"]["smoke_seconds_total"] >= 0
    assert summary["items"][0]["generation_duration_seconds"] >= 0
    assert summary["items"][0]["smoke_duration_seconds"] >= 0
    assert summary["items"][0]["total_duration_seconds"] >= 0
    assert (output_root / "crystalformer_raw" / "BaTiO3" / "samples.csv").exists()
    provenance = json.loads(
        (output_root / "formula_runs" / "BaTiO3" / "generation_provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["executed"] is True
    assert provenance["returncode"] == 0
    assert provenance["duration_seconds"] >= 0
    assert provenance["started_at_utc"]
    assert provenance["ended_at_utc"]
    assert "wrote fake CrystalFormer raw output" in provenance["stdout"]


def test_bulk_generation_auto_parallelism_uses_total_cpu_budget(tmp_path) -> None:
    config = _config(tmp_path)
    output_root = tmp_path / "parallel"

    result = main(
        [
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--run-generation",
            "--no-skip-existing",
            "--total-cpu-cores",
            "4",
        ]
    )

    summary = result["summary"]
    assert summary["status_counts"] == {"succeeded": 2}
    assert summary["parallelism"]["max_concurrent_generations"] == 2
    assert summary["parallelism"]["thread_allocations"] == [2, 2]
    assert summary["parallelism"]["parallel_core_budget"] == 4
    for formula in ("BaTiO3", "SrTiO3"):
        provenance = json.loads(
            (output_root / "formula_runs" / formula / "generation_provenance.json").read_text(
                encoding="utf-8"
            )
        )
        assert provenance["generation_cpu_threads"] == 2
        assert provenance["env_overrides"]["OMP_NUM_THREADS"] == "2"
        assert "intra_op_parallelism_threads=2" in provenance["env_overrides"]["XLA_FLAGS"]


def test_bulk_generation_only_formula(tmp_path) -> None:
    config = _config(tmp_path)
    output_root = tmp_path / "only"

    result = main(
        [
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--only-formula",
            "BaTiO3",
            "--run-generation",
            "--no-skip-existing",
        ]
    )

    assert result["summary"]["formula_count"] == 1
    assert result["summary"]["status_counts"] == {"succeeded": 1}
    assert (output_root / "crystalformer_raw" / "BaTiO3" / "samples.csv").exists()
    assert not (output_root / "crystalformer_raw" / "SrTiO3" / "samples.csv").exists()


def test_bulk_generation_stops_on_failure_by_default(tmp_path) -> None:
    config = _config(tmp_path, fail_formula="BaTiO3")
    output_root = tmp_path / "fail_stop"

    result = main(
        [
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--run-generation",
            "--no-skip-existing",
        ]
    )

    assert result["summary"]["completed_formula_count"] == 1
    assert result["summary"]["status_counts"] == {"failed": 1}
    assert "generation_failed_returncode" in result["rows"][0]["error"]
    assert not (output_root / "crystalformer_raw" / "SrTiO3" / "samples.csv").exists()


def test_bulk_generation_continue_on_error_runs_later_formula(tmp_path) -> None:
    config = _config(tmp_path, fail_formula="BaTiO3")
    output_root = tmp_path / "fail_continue"

    result = main(
        [
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--run-generation",
            "--no-skip-existing",
            "--continue-on-error",
        ]
    )

    assert result["summary"]["completed_formula_count"] == 2
    assert result["summary"]["status_counts"] == {"failed": 1, "succeeded": 1}
    assert (output_root / "crystalformer_raw" / "SrTiO3" / "samples.csv").exists()
