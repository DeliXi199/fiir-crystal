"""CLI for normalizing deepmodeling/CrystalFormer outputs into FIIR Crystal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.config import load_experiment_config
from fiir_crystal.experiment import run_fiir_experiment
from fiir_crystal.generation.crystalformer_adapter import CrystalFormerAdapter
from fiir_crystal.io import write_json
from fiir_crystal.structures import CrystalStructureRecord, write_jsonl


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize deepmodeling/CrystalFormer outputs and run lightweight FIIR reporting."
    )
    parser.add_argument("--config", default="configs/crystalformer_adapter.yaml")
    parser.add_argument("--output-dir", help="Directory for normalized candidates, summary, and report.")
    parser.add_argument("--run-generation", action="store_true", help="Run the configured CrystalFormer command first.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without reading or running outputs.")
    parser.add_argument("--formula")
    parser.add_argument("--spacegroup", type=int)
    parser.add_argument("--num-samples", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any] | None:
    args = parse_args(argv)
    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"config file does not exist: {args.config}")

    config = _load_mapping(config_path)
    generation = dict(config.get("generation", {}))
    screening = dict(config.get("screening", {}))
    _apply_overrides(generation, args)
    output_root, normalized_output = _resolve_output_paths(generation, args.output_dir)

    if args.dry_run:
        summary = _summary(
            generation=generation,
            output_root=output_root,
            normalized_output=normalized_output,
            records=[],
            subprocess_info=None,
            fiir_summary=None,
            dry_run=True,
        )
        print(_dry_run_text(summary))
        return summary

    adapter = CrystalFormerAdapter(generation)
    records = adapter.generate(generation)
    _stamp_screening_metadata(records, screening)

    write_jsonl(normalized_output, records)

    fiir_output_dir = output_root / "fiir_run"
    fiir_config = load_experiment_config(
        None,
        overrides={
            "input_path": str(normalized_output),
            "output_dir": str(fiir_output_dir),
            "top_k": min(5, max(1, len(records))),
        },
    )
    fiir_result = run_fiir_experiment(fiir_config)
    summary = _summary(
        generation=generation,
        output_root=output_root,
        normalized_output=normalized_output,
        records=records,
        subprocess_info=adapter.last_subprocess,
        fiir_summary=fiir_result["summary"],
        dry_run=False,
    )
    summary["generated_files"] = [
        str(normalized_output),
        str(output_root / "adapter_summary.json"),
        str(output_root / "report.md"),
        str(fiir_output_dir / "report.md"),
    ]
    write_json(output_root / "adapter_summary.json", summary)
    (output_root / "report.md").write_text(_render_report(summary), encoding="utf-8")

    print("CrystalFormer adapter complete")
    print(f"  normalized_output: {normalized_output}")
    print(f"  candidates: {summary['candidate_count']}")
    print(f"  fiir_output_dir: {fiir_output_dir}")
    print(f"  report: {output_root / 'report.md'}")
    return summary


def _apply_overrides(generation: dict[str, Any], args: argparse.Namespace) -> None:
    if args.run_generation:
        generation["run_generation"] = True
    if args.formula:
        generation["formula"] = args.formula
    if args.spacegroup is not None:
        generation["spacegroup"] = args.spacegroup
    if args.num_samples is not None:
        generation["num_samples"] = args.num_samples


def _resolve_output_paths(
    generation: dict[str, Any],
    output_dir_override: str | None,
) -> tuple[Path, Path]:
    if output_dir_override:
        output_root = Path(output_dir_override)
        normalized_output = output_root / "candidates.jsonl"
    else:
        normalized_output = Path(generation.get("normalized_output", "outputs/crystalformer_run/candidates.jsonl"))
        output_root = normalized_output.parent
    output_root.mkdir(parents=True, exist_ok=True)
    generation["normalized_output"] = str(normalized_output)
    return output_root, normalized_output


def _stamp_screening_metadata(records: list[CrystalStructureRecord], screening: dict[str, Any]) -> None:
    stability_mode = screening.get("stability_mode")
    if not stability_mode:
        return
    for record in records:
        record.metadata.setdefault("stability_mode", stability_mode)


def _summary(
    generation: dict[str, Any],
    output_root: Path,
    normalized_output: Path,
    records: list[CrystalStructureRecord],
    subprocess_info: dict[str, Any] | None,
    fiir_summary: dict[str, Any] | None,
    dry_run: bool,
) -> dict[str, Any]:
    formats: dict[str, int] = {}
    for record in records:
        source_format = str(record.metadata.get("source_format", "unknown"))
        formats[source_format] = formats.get(source_format, 0) + 1
    return {
        "adapter": "crystalformer",
        "crystalformer_project": "deepmodeling/CrystalFormer",
        "dry_run": dry_run,
        "run_generation": bool(generation.get("run_generation", False)),
        "crystalformer_work_dir": generation.get("crystalformer_work_dir"),
        "crystalformer_command": generation.get("crystalformer_command"),
        "raw_output_dir": generation.get("output_dir"),
        "normalized_output": str(normalized_output),
        "output_dir": str(output_root),
        "source_format": generation.get("source_format", "auto"),
        "candidate_count": len(records),
        "partial_record_count": sum(bool(record.metadata.get("partial_record")) for record in records),
        "source_formats": formats,
        "subprocess": subprocess_info,
        "fiir_summary": fiir_summary,
        "stability_note": (
            "CrystalFormer candidates are generated structures only. F3 stability is "
            "unavailable_without_offline_validation unless offline validation, MLIP relaxation, "
            "or DFT results are imported."
        ),
    }


def _render_report(summary: dict[str, Any]) -> str:
    fiir = summary.get("fiir_summary") or {}
    lines = [
        "# CrystalFormer Adapter Report",
        "",
        "## Boundary",
        "- External generator: `deepmodeling/CrystalFormer`",
        "- FIIR Crystal did not train CrystalFormer, download checkpoints, run DFT, run MLIP, or call external APIs.",
        "- Generated structures are candidates, not relaxed stable materials.",
        "- F3 stability is unavailable without imported offline validation.",
        "",
        "## Adapter Summary",
        f"- normalized_output: `{summary.get('normalized_output')}`",
        f"- candidate_count: {summary.get('candidate_count', 0)}",
        f"- partial_record_count: {summary.get('partial_record_count', 0)}",
        f"- source_formats: {summary.get('source_formats', {})}",
        f"- run_generation: {summary.get('run_generation', False)}",
        "",
        "## FIIR Flow Summary",
        f"- fiir_output_dir: `{fiir.get('output_dir', 'unavailable')}`",
        f"- failure_vector_count: {fiir.get('failure_vector_count', 'unavailable')}",
        f"- pair_count: {fiir.get('pair_count', 'unavailable')}",
        f"- ranked_count: {fiir.get('ranked_count', 'unavailable')}",
        f"- feedback_count: {fiir.get('feedback_count', 'unavailable')}",
        "",
        "## Stability Caveat",
        f"- {summary.get('stability_note')}",
        "",
    ]
    return "\n".join(lines)


def _dry_run_text(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "CrystalFormer adapter dry run",
            f"  raw_output_dir: {summary.get('raw_output_dir')}",
            f"  normalized_output: {summary.get('normalized_output')}",
            f"  run_generation: {summary.get('run_generation')}",
            f"  crystalformer_command: {summary.get('crystalformer_command')}",
        ]
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = _parse_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return data


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if ":" not in line:
            raise ValueError(f"Unsupported config line: {raw_line}")
        key, raw_value = line.strip().split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value_text = raw_value.strip()
        if not value_text:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value_text)
    return root


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if any(char in value for char in [".", "e", "E"]):
            return float(value)
        return int(value)
    except ValueError:
        return value


if __name__ == "__main__":
    main()
