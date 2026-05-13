import csv
from pathlib import Path

import pytest

from fiir_crystal.io import read_json, read_jsonl, write_jsonl
from scripts.build_f4_reference_pool_manifest import main as build_manifest_main
from scripts.check_f4_novelty_audit_ready import main as check_ready_main
from scripts.plan_f4_novelty_audit import main as plan_f4_main
from scripts.prepare_f4_reference_source import main as prepare_reference_main


def _candidate(candidate_id: str, formula: str = "BaTiO3") -> dict:
    return {
        "candidate_id": candidate_id,
        "composition": formula,
        "condition": {"mode": "csp", "formula": formula, "spacegroup": None},
        "f1_label": "pass",
        "f2_label": "pass",
    }


def test_prepare_f4_reference_source_from_inline_cif_csv(tmp_path: Path) -> None:
    source_csv = tmp_path / "mini.csv"
    output_jsonl = tmp_path / "references" / "mini.structures.jsonl"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["material_id", "pretty_formula", "cif", "e_above_hull"])
        writer.writeheader()
        writer.writerow(
            {
                "material_id": "mp-1",
                "pretty_formula": "BaTiO3",
                "cif": "data_mp_1\n_cell_length_a 4.0\n",
                "e_above_hull": "0.0",
            }
        )

    result = prepare_reference_main(
        [
            "--input-csv",
            str(source_csv),
            "--output-jsonl",
            str(output_jsonl),
            "--source-name",
            "crystalformer_mini_example",
        ]
    )

    assert result["summary"]["converted_row_count"] == 1
    rows = read_jsonl(output_jsonl)
    assert rows[0]["reference_id"] == "mp-1"
    assert rows[0]["formula"] == "BaTiO3"
    assert rows[0]["source_database"] == "crystalformer_mini_example"
    assert rows[0]["structure_format"] == "cif_inline"
    assert rows[0]["structure_ref"].startswith("data_mp_1")
    assert rows[0]["metadata"]["raw_row"]["e_above_hull"] == "0.0"
    assert read_json(output_jsonl.with_suffix(".report.json"))["local_only"] is True


def test_prepare_f4_reference_source_from_inline_structure_csv_can_omit_raw_row(tmp_path: Path) -> None:
    source_csv = tmp_path / "alex20_like.csv"
    output_jsonl = tmp_path / "references" / "alex20_like.structures.jsonl"
    structure = '{"@module": "pymatgen.core.structure", "@class": "Structure"}'
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["mat_id", "formula", "structure", "e_above_hull"])
        writer.writeheader()
        writer.writerow(
            {
                "mat_id": "agm000001",
                "formula": "BaTiO3",
                "structure": structure,
                "e_above_hull": "0.0",
            }
        )

    prepare_reference_main(
        [
            "--input-csv",
            str(source_csv),
            "--output-jsonl",
            str(output_jsonl),
            "--source-name",
            "alex20_train_snapshot",
            "--omit-raw-row",
        ]
    )

    rows = read_jsonl(output_jsonl)
    assert rows[0]["reference_id"] == "agm000001"
    assert rows[0]["structure_format"] == "structure_inline"
    assert rows[0]["structure_ref"] == structure
    assert "raw_row" not in rows[0]["metadata"]
    assert read_json(output_jsonl.with_suffix(".report.json"))["omits_raw_row"] is True


def test_prepare_f4_reference_source_enables_smoke_readiness(tmp_path: Path) -> None:
    candidate_index = tmp_path / "candidate_index.jsonl"
    source_csv = tmp_path / "mini.csv"
    output_dir = tmp_path / "f4_smoke"
    references_jsonl = output_dir / "references" / "mini.structures.jsonl"
    write_jsonl(candidate_index, [_candidate("c1"), _candidate("c2", "SrTiO3")])
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["material_id", "pretty_formula", "cif"])
        writer.writeheader()
        writer.writerow({"material_id": "mp-1", "pretty_formula": "BaTiO3", "cif": "data_mp_1\n"})

    plan_f4_main(
        [
            "--candidate-index",
            str(candidate_index),
            "--output-dir",
            str(output_dir),
            "--reference-pool-id",
            "reference_pool_mini_smoke",
            "--shard-count",
            "2",
        ]
    )
    prepare_reference_main(
        [
            "--input-csv",
            str(source_csv),
            "--output-jsonl",
            str(references_jsonl),
            "--source-name",
            "crystalformer_mini_example",
        ]
    )
    build_manifest_main(
        [
            "--reference-source",
            f"crystalformer_mini_example={references_jsonl}",
            "--reference-pool-id",
            "reference_pool_mini_smoke",
            "--output-json",
            str(output_dir / "reference_pool_manifest.json"),
        ]
    )

    readiness = check_ready_main(["--plan-json", str(output_dir / "f4_audit_plan.json")])
    assert readiness["ready"] is True
    assert readiness["reference_pool"]["total_reference_count"] == 1


def test_prepare_f4_reference_source_rejects_rows_without_structure(tmp_path: Path) -> None:
    source_csv = tmp_path / "missing_cif.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["material_id", "pretty_formula"])
        writer.writeheader()
        writer.writerow({"material_id": "mp-1", "pretty_formula": "BaTiO3"})

    with pytest.raises(SystemExit, match="has no CIF/structure text/path"):
        prepare_reference_main(
            [
                "--input-csv",
                str(source_csv),
                "--output-jsonl",
                str(tmp_path / "refs.jsonl"),
            ]
        )
