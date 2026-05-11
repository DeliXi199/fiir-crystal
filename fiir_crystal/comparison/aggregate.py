"""Aggregate existing FIIR experiment output directories."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.io import read_json, write_json
from fiir_crystal.reporting import render_aggregate_report as render_aggregate_markdown_report
from fiir_crystal.reporting import render_markdown_table


def load_experiment_summary(output_dir: str | Path) -> dict[str, Any]:
    """Load required summary artifacts from one experiment output directory."""

    root = Path(output_dir)
    summary_path = root / "experiment_summary.json"
    evaluation_path = root / "evaluation_report.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"required experiment output missing: {summary_path}")
    if not evaluation_path.exists():
        raise FileNotFoundError(f"required experiment output missing: {evaluation_path}")
    summary = read_json(summary_path)
    evaluation = read_json(evaluation_path)
    return {
        "run_name": root.name,
        "output_dir": str(root),
        "pair_mode": summary.get("pair_mode"),
        "candidate_count": evaluation.get("candidate_count", summary.get("candidate_count", 0)),
        "pair_count": evaluation.get("pair_count", summary.get("pair_count", 0)),
        "valid_rate": evaluation.get("valid_rate"),
        "failure_rate": evaluation.get("failure_rate"),
        "top_k_valid_rate": evaluation.get("top_k_valid_rate"),
        "top_k_average_failure": evaluation.get("top_k_average_failure"),
        "average_pair_margin": evaluation.get("average_pair_margin"),
        "average_pair_confidence": evaluation.get("average_pair_confidence"),
        "feedback_count": summary.get("feedback_count", 0),
        "ranking_mode": summary.get("ranking_mode"),
        "validation_count": evaluation.get("validation_count", 0),
        "validated_stable_rate": evaluation.get("validated_stable_rate"),
        "top_k_validated_stable_rate": evaluation.get("top_k_validated_stable_rate"),
        "validation_failure_count": evaluation.get("validation_failure_count", 0),
    }


def aggregate_experiments(output_dirs: Sequence[str | Path]) -> dict[str, Any]:
    """Aggregate rows from multiple experiment output directories."""

    rows = [load_experiment_summary(output_dir) for output_dir in output_dirs]
    return {
        "run_count": len(rows),
        "runs": rows,
    }


def render_aggregate_table(rows: Sequence[dict[str, Any]]) -> str:
    """Render aggregate rows as Markdown."""

    return render_markdown_table(
        [
            "run_name",
            "pair_mode",
            "candidates",
            "pairs",
            "valid_rate",
            "failure_rate",
            "top_k_valid_rate",
            "top_k_failure",
            "avg_margin",
            "avg_confidence",
            "feedback",
            "ranking_mode",
        ],
        [
            [
                row.get("run_name"),
                row.get("pair_mode"),
                row.get("candidate_count"),
                row.get("pair_count"),
                row.get("valid_rate"),
                row.get("failure_rate"),
                row.get("top_k_valid_rate"),
                row.get("top_k_average_failure"),
                row.get("average_pair_margin"),
                row.get("average_pair_confidence"),
                row.get("feedback_count"),
                row.get("ranking_mode"),
            ]
            for row in rows
        ],
    )


def render_aggregate_report(summary: dict[str, Any]) -> str:
    """Render a Markdown aggregate report."""

    return render_aggregate_markdown_report(summary, render_aggregate_table(summary.get("runs", [])))


def write_aggregate_outputs(output_dirs: Sequence[str | Path], output_dir: str | Path) -> dict[str, Any]:
    """Aggregate experiment directories and write JSON/Markdown outputs."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary = aggregate_experiments(output_dirs)
    summary["output_dir"] = str(root)
    table = render_aggregate_table(summary["runs"])
    summary["generated_files"] = [
        str(root / "aggregate_summary.json"),
        str(root / "aggregate_table.md"),
        str(root / "report.md"),
    ]
    write_json(root / "aggregate_summary.json", summary)
    (root / "aggregate_table.md").write_text(table + "\n", encoding="utf-8")
    (root / "report.md").write_text(render_aggregate_report(summary), encoding="utf-8")
    return summary
