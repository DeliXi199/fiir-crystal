"""CLI for building CrystalFormer DPO preference-pair JSONL from FIIR audit output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fiir_crystal.dpo import (
    PreferenceBuildConfig,
    build_dpo_preferences,
    read_audit_candidates,
    write_preference_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build schema-first CrystalFormer DPO preference pairs from FIIR audit records."
    )
    parser.add_argument("--config", default="configs/dpo_preference_builder.yaml")
    parser.add_argument("--audit-candidates-jsonl")
    parser.add_argument("--audit-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--formula")
    parser.add_argument("--spacegroup", type=int)
    parser.add_argument("--min-preference-margin", type=float)
    parser.add_argument("--max-pairs", type=int)
    parser.add_argument("--fail-on-zero-pairs", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any] | None:
    args = parse_args(argv)
    config = _load_config(args.config)
    audit_candidates = _audit_candidates_path(args, config)
    output_dir = _output_dir(args, config)
    build_config = _build_config(args, config)

    if args.dry_run:
        summary = {
            "dry_run": True,
            "audit_candidates_jsonl": str(audit_candidates),
            "output_dir": str(output_dir),
            "formula": build_config.formula,
            "spacegroup": build_config.spacegroup,
            "min_preference_margin": build_config.min_preference_margin,
            "max_pairs": build_config.max_pairs,
            "dpo_training": False,
        }
        print("CrystalFormer DPO preference builder dry run")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        return summary

    rows = read_audit_candidates(audit_candidates)
    pairs, summary = build_dpo_preferences(rows, build_config)
    files = write_preference_outputs(output_dir, pairs, summary)

    print("CrystalFormer DPO preference build complete")
    print(f"  input_candidates: {summary.input_candidate_count}")
    print(f"  usable_candidates: {summary.usable_candidate_count}")
    print(f"  preference_pairs: {summary.pair_count}")
    print(f"  output_dir: {output_dir}")
    print(f"  report: {files['report']}")

    if args.fail_on_zero_pairs and summary.pair_count == 0:
        raise SystemExit("no DPO preference pairs were built")
    return {"summary": summary.to_dict(), "files": files}


def _audit_candidates_path(args: argparse.Namespace, config: dict[str, Any]) -> Path:
    if args.audit_candidates_jsonl:
        return Path(args.audit_candidates_jsonl)
    if args.audit_dir:
        return Path(args.audit_dir) / "audit_candidates.jsonl"
    configured = _nested(config, "input", "audit_candidates_jsonl")
    if configured:
        return Path(str(configured))
    audit_dir = _nested(config, "input", "audit_dir") or "outputs/crystalformer_audit/BaTiO3"
    return Path(str(audit_dir)) / "audit_candidates.jsonl"


def _output_dir(args: argparse.Namespace, config: dict[str, Any]) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    configured = _nested(config, "output", "preference_dir")
    if configured:
        return Path(str(configured))
    formula = args.formula or _nested(config, "condition", "formula") or "unknown_formula"
    return Path("outputs") / "dpo_preferences" / str(formula)


def _build_config(args: argparse.Namespace, config: dict[str, Any]) -> PreferenceBuildConfig:
    return PreferenceBuildConfig(
        formula=args.formula if args.formula is not None else _nested(config, "condition", "formula"),
        spacegroup=args.spacegroup if args.spacegroup is not None else _optional_int(_nested(config, "condition", "spacegroup")),
        min_preference_margin=(
            args.min_preference_margin
            if args.min_preference_margin is not None
            else float(_nested(config, "pairing", "min_preference_margin") or 1e-6)
        ),
        max_pairs=args.max_pairs if args.max_pairs is not None else _optional_int(_nested(config, "pairing", "max_pairs")),
        require_raw_sequence=bool(_nested(config, "pairing", "require_raw_sequence", default=True)),
    )


def _load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = _parse_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {source}")
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
            continue
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


def _nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return int(float(str(value)))


if __name__ == "__main__":
    main()
