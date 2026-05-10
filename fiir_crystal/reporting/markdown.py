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
        "## Discovery Ranking Summary",
        f"- ranked_count: {summary.get('ranked_count', len(ranked_candidates))}",
        f"- ranking_utility_stats: {evaluation.get('ranking_utility_stats', {})}",
        "",
        "## Top-K Candidates",
    ]
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
