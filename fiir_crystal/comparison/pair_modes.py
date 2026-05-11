"""Compare multiple preference-pair construction modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.config import ExperimentConfig, load_experiment_config, merge_config_overrides
from fiir_crystal.experiment import run_fiir_experiment
from fiir_crystal.io import write_json
from fiir_crystal.reporting import render_markdown_table, render_pair_mode_comparison_report


DEFAULT_PAIR_MODES = [
    "axis_aligned",
    "weighted_sum",
    "random_negative",
    "binary_success_failure",
]


def compare_pair_modes(
    config: ExperimentConfig | str | Path,
    modes: Sequence[str] | None = None,
    output_dir: str | Path = "outputs/pair_mode_comparison",
    input_path: str | Path | None = None,
    top_k: int | None = None,
    seed: int | None = None,
    validation_results: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Run the same mock experiment across pair construction modes."""

    base_config = _load_config(config)
    selected_modes = list(modes or DEFAULT_PAIR_MODES)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for mode in selected_modes:
        mode_config = merge_config_overrides(
            base_config,
            {
                "input_path": str(input_path or base_config.input_path),
                "output_dir": str(root / mode),
                "pair_mode": mode,
                "top_k": int(top_k if top_k is not None else base_config.top_k),
                "random_seed": int(seed if seed is not None else base_config.random_seed),
            },
        )
        result = run_fiir_experiment(mode_config, validation_results=validation_results)
        rows.append(_row_from_result(mode, result))

    table = render_comparison_table(rows, include_validation=validation_results is not None)
    summary = {
        "output_dir": str(root),
        "input_path": str(input_path or base_config.input_path),
        "top_k": int(top_k if top_k is not None else base_config.top_k),
        "seed": int(seed if seed is not None else base_config.random_seed),
        "validation_metrics_available": validation_results is not None,
        "modes": rows,
        "generated_files": [
            str(root / "comparison_summary.json"),
            str(root / "comparison_table.md"),
            str(root / "report.md"),
        ],
    }
    write_json(root / "comparison_summary.json", summary)
    (root / "comparison_table.md").write_text(table + "\n", encoding="utf-8")
    (root / "report.md").write_text(render_pair_mode_comparison_report(summary, table), encoding="utf-8")
    return {
        "summary": summary,
        "rows": rows,
        "table": table,
        "output_dir": root,
    }


def render_comparison_table(rows: Sequence[dict[str, Any]], include_validation: bool = False) -> str:
    """Render a Markdown table for pair mode comparison."""

    headers = [
        "mode",
        "candidates",
        "valid_rate",
        "failure_rate",
        "pairs",
        "avg_margin",
        "avg_confidence",
        "valid_pair_ratio",
        "top_k_failure",
        "top_k_valid",
        "utility_mean",
    ]
    table_rows: list[list[Any]] = [
        [
            row.get("mode"),
            row.get("candidate_count"),
            row.get("valid_rate"),
            row.get("failure_rate"),
            row.get("pair_count"),
            row.get("average_pair_margin"),
            row.get("average_pair_confidence"),
            row.get("valid_pair_ratio"),
            row.get("top_k_average_failure"),
            row.get("top_k_valid_rate"),
            row.get("ranking_utility_stats", {}).get("mean"),
        ]
        for row in rows
    ]
    if include_validation:
        headers.extend(
            [
                "validated_stable_rate",
                "top_k_validated_stable_rate",
                "validation_coverage",
                "validation_failure_count",
            ]
        )
        for row, table_row in zip(rows, table_rows):
            table_row.extend(
                [
                    row.get("validated_stable_rate"),
                    row.get("top_k_validated_stable_rate"),
                    row.get("top_k_validation_coverage"),
                    row.get("validation_failure_count"),
                ]
            )
    return render_markdown_table(headers, table_rows)


def _row_from_result(mode: str, result: dict[str, Any]) -> dict[str, Any]:
    evaluation = result["evaluation_report"].as_dict()
    summary = dict(result["summary"])
    return {
        "mode": mode,
        "output_dir": str(result["output_dir"]),
        "candidate_count": evaluation.get("candidate_count", summary.get("candidate_count", 0)),
        "valid_rate": evaluation.get("valid_rate"),
        "failure_rate": evaluation.get("failure_rate"),
        "pair_count": evaluation.get("pair_count", summary.get("pair_count", 0)),
        "pairs_by_axis": evaluation.get("pairs_by_axis", {}),
        "pairs_by_mode": evaluation.get("pairs_by_mode", {}),
        "average_pair_margin": evaluation.get("average_pair_margin"),
        "average_pair_confidence": evaluation.get("average_pair_confidence"),
        "valid_pair_ratio": evaluation.get("valid_pair_ratio"),
        "top_k_average_failure": evaluation.get("top_k_average_failure"),
        "top_k_valid_rate": evaluation.get("top_k_valid_rate"),
        "ranking_utility_stats": evaluation.get("ranking_utility_stats", {}),
        "validation_count": evaluation.get("validation_count", 0),
        "validated_stable_rate": evaluation.get("validated_stable_rate"),
        "top_k_validated_stable_rate": evaluation.get("top_k_validated_stable_rate"),
        "top_k_validation_coverage": evaluation.get("top_k_validation_coverage"),
        "validation_failure_count": evaluation.get("validation_failure_count", 0),
    }


def _load_config(config: ExperimentConfig | str | Path) -> ExperimentConfig:
    if isinstance(config, ExperimentConfig):
        return config
    return load_experiment_config(config)
