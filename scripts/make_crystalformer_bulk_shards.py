"""Create CrystalFormer bulk generation shard configs from a formula bank."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_COMMAND_TEMPLATE = (
    "python ./main.py --optimizer none --restore_path {checkpoint_dir} "
    "--K {top_k} --num_samples {num_samples} --formula {formula} "
    "--save_path {raw_output_dir}/output.csv"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate CrystalFormer bulk config shards from a formula bank."
    )
    parser.add_argument("--formula-bank", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--formulas-per-shard", type=int, default=32)
    parser.add_argument("--num-samples", type=int, default=1600)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--output-root-prefix", required=True)
    parser.add_argument("--crystalformer-work-dir", default="external/CrystalFormer")
    parser.add_argument("--checkpoint-dir", default="external/checkpoints/crystalformer/alex20s_csp")
    parser.add_argument("--parser-backend", default="none")
    parser.add_argument("--stability-mode", default="unavailable_without_offline_validation")
    parser.add_argument("--source-format", default="auto")
    parser.add_argument("--command-template", default=DEFAULT_COMMAND_TEMPLATE)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    formulas = load_formula_bank(Path(args.formula_bank))
    if args.formulas_per_shard <= 0:
        raise SystemExit("--formulas-per-shard must be positive")
    if args.num_samples <= 0:
        raise SystemExit("--num-samples must be positive")
    if args.top_k <= 0:
        raise SystemExit("--top-k must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    shards = _split_formulas(formulas, args.formulas_per_shard)
    shard_files = []
    for index, shard_formulas in enumerate(shards, start=1):
        shard_name = f"shard_{index:03d}"
        config = _shard_config(args, shard_name, shard_formulas)
        path = output_dir / f"{shard_name}.json"
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        shard_files.append(str(path))

    summary = {
        "formula_bank": str(Path(args.formula_bank)),
        "formula_count": len(formulas),
        "shard_count": len(shards),
        "formulas_per_shard": args.formulas_per_shard,
        "num_samples": args.num_samples,
        "total_num_samples": len(formulas) * args.num_samples,
        "shard_files": shard_files,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("CrystalFormer bulk shard configs written")
    print(f"  formula_count: {summary['formula_count']}")
    print(f"  shard_count: {summary['shard_count']}")
    print(f"  total_num_samples: {summary['total_num_samples']}")
    print(f"  output_dir: {output_dir}")
    return summary


def load_formula_bank(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("formulas"), list):
        rows = data["formulas"]
    else:
        raise ValueError("formula bank must be a list or an object with a formulas list")

    formulas: list[str] = []
    seen = set()
    for row in rows:
        formula = _formula_from_row(row)
        if not formula:
            raise ValueError("formula entries must not be empty")
        if formula in seen:
            raise ValueError(f"duplicate formula in bank: {formula}")
        seen.add(formula)
        formulas.append(formula)
    if not formulas:
        raise ValueError("formula bank must not be empty")
    return formulas


def _formula_from_row(row: Any) -> str:
    if isinstance(row, str):
        return row.strip()
    if isinstance(row, dict):
        return str(row.get("formula", "")).strip()
    raise ValueError(f"unsupported formula bank entry: {row!r}")


def _split_formulas(formulas: list[str], formulas_per_shard: int) -> list[list[str]]:
    shard_count = math.ceil(len(formulas) / formulas_per_shard)
    return [
        formulas[index * formulas_per_shard : (index + 1) * formulas_per_shard]
        for index in range(shard_count)
    ]


def _shard_config(args: argparse.Namespace, shard_name: str, formulas: list[str]) -> dict[str, Any]:
    return {
        "crystalformer_work_dir": args.crystalformer_work_dir,
        "checkpoint_dir": args.checkpoint_dir,
        "output_root": f"{args.output_root_prefix}_{shard_name}",
        "parser_backend": args.parser_backend,
        "stability_mode": args.stability_mode,
        "source_format": args.source_format,
        "skip_existing": bool(args.skip_existing),
        "defaults": {
            "num_samples": args.num_samples,
            "top_k": args.top_k,
        },
        "command_template": args.command_template,
        "formulas": [{"formula": formula} for formula in formulas],
    }


if __name__ == "__main__":
    main()
