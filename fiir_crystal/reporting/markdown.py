"""Simple Markdown report generator for lightweight FIIR experiments."""

from __future__ import annotations

from typing import Any, Sequence


def render_experiment_report(
    summary: dict[str, Any],
    config: dict[str, Any],
    evaluation_report: Any | None,
    ranked_candidates: Sequence[Any],
    feedback_records: Sequence[Any],
) -> str:
    """Render a Markdown report without external templating dependencies."""

    evaluation = evaluation_report.as_dict() if hasattr(evaluation_report, "as_dict") else (evaluation_report or {})
    lines = [
        "# FIIR Crystal Mock Experiment Report",
        "",
        "## Experiment Config Summary",
        f"- input_path: `{config.get('input_path', 'unavailable')}`",
        f"- output_dir: `{config.get('output_dir', 'unavailable')}`",
        f"- pair_mode: `{config.get('pair_mode', 'unavailable')}`",
        f"- ranking_mode: `{config.get('ranking', {}).get('mode', 'unavailable')}`",
        f"- top_k: `{config.get('top_k', 'unavailable')}`",
        "",
        "## Candidate Summary",
        f"- candidate_count: {summary.get('candidate_count', 0)}",
        f"- valid_rate: {evaluation.get('valid_rate', 'unavailable')}",
        f"- hard_failure_count: {evaluation.get('hard_failure_count', 'unavailable')}",
        "",
        "## Failure Summary",
        f"- average_f1: {evaluation.get('average_f1', 'unavailable')}",
        f"- average_f2: {evaluation.get('average_f2', 'unavailable')}",
        f"- average_f3: {evaluation.get('average_f3', 'unavailable')}",
        f"- average_f4: {evaluation.get('average_f4', 'unavailable')}",
        f"- average_f5: {evaluation.get('average_f5', 'unavailable')}",
        f"- failure_rate: {evaluation.get('failure_rate', 'unavailable')}",
        f"- calibration_tier_distribution: {evaluation.get('calibration_tier_distribution', {})}",
        "",
        "## Preference Pair Summary",
        f"- pair_count: {evaluation.get('pair_count', 0)}",
        f"- pairs_by_axis: {evaluation.get('pairs_by_axis', {})}",
        f"- pairs_by_mode: {evaluation.get('pairs_by_mode', {})}",
        f"- average_pair_margin: {evaluation.get('average_pair_margin', 'unavailable')}",
        f"- average_pair_confidence: {evaluation.get('average_pair_confidence', 'unavailable')}",
        "",
        "## Validation Statistics",
    ]
    if evaluation.get("validation_metrics_available"):
        lines.extend(
            [
                f"- validation_count: {evaluation.get('validation_count', 0)}",
                f"- validation_success_rate: {evaluation.get('validation_success_rate', 'unavailable')}",
                f"- validated_stable_rate: {evaluation.get('validated_stable_rate', 'unavailable')}",
                f"- top_k_validated_stable_rate: {evaluation.get('top_k_validated_stable_rate', 'unavailable')}",
                f"- top_k_validation_coverage: {evaluation.get('top_k_validation_coverage', 'unavailable')}",
                f"- validation_failure_count: {evaluation.get('validation_failure_count', 0)}",
            ]
        )
    else:
        lines.append("- Validation metrics unavailable; no offline validation JSONL was provided.")
    lines.extend(
        [
            "",
            "## Discovery Ranking Summary",
            f"- ranked_count: {summary.get('ranked_count', len(ranked_candidates))}",
            f"- ranking_utility_stats: {evaluation.get('ranking_utility_stats', {})}",
            "",
            "## Top-K Candidates",
        ]
    )
    if ranked_candidates:
        for candidate in ranked_candidates[: int(config.get("top_k", len(ranked_candidates)))]:
            lines.append(
                f"- rank {candidate.rank}: `{candidate.candidate_id}` "
                f"utility={candidate.acquisition.utility:.4f}"
            )
    else:
        lines.append("- No ranked candidates were produced.")
    lines.extend(["", "## Feedback Summary"])
    if feedback_records:
        for record in feedback_records:
            lines.append(
                f"- `{record.candidate_id}` rank={record.selected_rank} "
                f"decision={record.decision} reason={record.reason}"
            )
    else:
        lines.append("- No feedback records were produced.")
    lines.extend(
        [
            "",
            "## Limitations",
            "- This run uses mock structures and lightweight rules only.",
            "- No MLIP, DFT, Materials Project, CSLLM, or external database is called.",
            "- No deep learning training is performed.",
            "",
            "## Next Steps",
            "- Add optional adapters for real local structure objects.",
            "- Keep external validation offline and imported through JSONL.",
            "- Compare axis-aligned pairs against baseline pair construction modes.",
            "",
        ]
    )
    return "\n".join(lines)


def render_pair_mode_comparison_report(summary: dict[str, Any], table_markdown: str) -> str:
    """Render a pair construction mode comparison report."""

    rows = summary.get("modes", [])
    lines = [
        "# FIIR Crystal Pair Mode Comparison Report",
        "",
        "## Summary",
        f"- modes: {', '.join(str(row.get('mode')) for row in rows) if rows else 'none'}",
        f"- output_dir: `{summary.get('output_dir', 'unavailable')}`",
        f"- validation_metrics_available: {summary.get('validation_metrics_available', False)}",
        "",
        "## Key Metrics",
        table_markdown if table_markdown.strip() else "_No comparison rows were produced._",
        "",
        "## Generated Files",
    ]
    for path in summary.get("generated_files", []):
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Limitations",
            "- Pair modes reuse the same mock candidates and lightweight labels.",
            "- No DPO training, MLIP, DFT, external API, or dataset download is performed.",
            "",
            "## Next Steps",
            "- Use these tables to choose baselines for larger local mock sweeps.",
            "- Import offline validation JSONL when available to compare top-k outcomes.",
            "",
        ]
    )
    return "\n".join(lines)


def render_aggregate_report(summary: dict[str, Any], table_markdown: str) -> str:
    """Render an aggregate report for multiple experiment output directories."""

    lines = [
        "# FIIR Crystal Aggregate Experiment Report",
        "",
        "## Summary",
        f"- run_count: {summary.get('run_count', 0)}",
        f"- output_dir: `{summary.get('output_dir', 'unavailable')}`",
        "",
        "## Key Metrics",
        table_markdown if table_markdown.strip() else "_No experiment summaries were available._",
        "",
        "## Generated Files",
    ]
    for path in summary.get("generated_files", []):
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Limitations",
            "- Aggregation only reads local JSON/JSONL experiment outputs.",
            "- Missing required summary files are reported as errors rather than silently ignored.",
            "",
            "## Next Steps",
            "- Add seeds and config hashes when running larger sweeps.",
            "- Use offline validation imports for post-hoc discovery comparisons.",
            "",
        ]
    )
    return "\n".join(lines)


def render_active_loop_report(summary: dict[str, Any]) -> str:
    """Render a mock active discovery loop report."""

    rows = summary.get("rounds", [])
    lines = [
        "# FIIR Crystal Mock Active Loop Report",
        "",
        "## Summary",
        f"- round_count: {summary.get('round_count', 0)}",
        f"- output_dir: `{summary.get('output_dir', 'unavailable')}`",
        f"- feedback_event_count: {summary.get('feedback_event_count', 0)}",
        f"- positive_evidence_count: {summary.get('positive_evidence_count', 0)}",
        f"- negative_evidence_count: {summary.get('negative_evidence_count', 0)}",
        "",
        "## Key Metrics",
        render_markdown_table(
            ["round", "pair_mode", "pairs", "feedback", "top_k_valid_rate", "validated_stable_rate"],
            [
                [
                    row.get("round_id"),
                    row.get("pair_mode"),
                    row.get("pair_count"),
                    row.get("feedback_count"),
                    row.get("top_k_valid_rate"),
                    row.get("validated_stable_rate"),
                ]
                for row in rows
            ],
        ),
        "",
        "## Feedback Statistics",
        f"- sampling_hints: {summary.get('sampling_hints', {})}",
        "",
        "## Generated Files",
    ]
    for path in summary.get("generated_files", []):
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Limitations",
            "- Later rounds resample and annotate existing mock candidates; no real generation model is trained.",
            "- Validation results are offline imports only.",
            "",
            "## Next Steps",
            "- Replace sampling hints with generator adapter inputs when a real local generator is available.",
            "- Add richer feedback prioritization once offline validation coverage grows.",
            "",
        ]
    )
    return "\n".join(lines)


def render_markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a small GitHub-flavored Markdown table."""

    if not rows:
        return "_No rows._"
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(_format_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator, *body])


def _format_cell(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "unavailable"
    return str(value).replace("\n", " ")
