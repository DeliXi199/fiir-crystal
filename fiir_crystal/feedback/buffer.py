"""Feedback buffer and mock active discovery loop utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.config import ExperimentConfig, load_experiment_config, merge_config_overrides
from fiir_crystal.experiment import run_fiir_experiment
from fiir_crystal.failure import FailureVector, StructureLike
from fiir_crystal.io import read_mock_candidates_jsonl, write_json, write_jsonl
from fiir_crystal.reporting import render_active_loop_report
from fiir_crystal.validation import ValidationResult


@dataclass(slots=True)
class FeedbackEvent:
    """Single event that can steer a future mock active loop round."""

    candidate_id: str
    round_id: str
    source: str
    decision: str
    validation_result: ValidationResult | None = None
    failure_vector: FailureVector | None = None
    suggested_action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "round_id": self.round_id,
            "source": self.source,
            "decision": self.decision,
            "validation_result": self.validation_result.to_dict() if self.validation_result else None,
            "failure_vector": self.failure_vector.to_dict() if self.failure_vector else None,
            "suggested_action": self.suggested_action,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackEvent":
        return cls(
            candidate_id=str(data["candidate_id"]),
            round_id=str(data.get("round_id", "")),
            source=str(data.get("source", "")),
            decision=str(data.get("decision", "")),
            validation_result=(
                None if data.get("validation_result") is None else ValidationResult.from_dict(data["validation_result"])
            ),
            failure_vector=(
                None if data.get("failure_vector") is None else FailureVector.from_dict(data["failure_vector"])
            ),
            suggested_action=str(data.get("suggested_action", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class FeedbackBuffer:
    """Append-only local feedback buffer."""

    events: list[FeedbackEvent] = field(default_factory=list)

    def add(self, event: FeedbackEvent) -> None:
        self.events.append(event)

    def extend(self, events: Sequence[FeedbackEvent]) -> None:
        self.events.extend(events)

    @classmethod
    def from_feedback_records(cls, records: Sequence[Any], round_id: str) -> "FeedbackBuffer":
        buffer = cls()
        for record in records:
            buffer.add(
                FeedbackEvent(
                    candidate_id=str(record.candidate_id),
                    round_id=round_id,
                    source="discovery_feedback",
                    decision=str(record.decision or "selected"),
                    failure_vector=record.failure_vector,
                    suggested_action="review_selected_candidate",
                    metadata={
                        "selected_rank": record.selected_rank,
                        "reason": record.reason,
                        "utility_score": record.metadata.get("utility"),
                    },
                )
            )
        return buffer

    @classmethod
    def from_validation_results(
        cls,
        results: Sequence[ValidationResult],
        round_id: str,
        failure_vectors: dict[str, FailureVector] | None = None,
    ) -> "FeedbackBuffer":
        buffer = cls()
        for result in results:
            decision, action = _validation_decision(result)
            buffer.add(
                FeedbackEvent(
                    candidate_id=result.candidate_id,
                    round_id=round_id,
                    source="offline_validation",
                    decision=decision,
                    validation_result=result,
                    failure_vector=(failure_vectors or {}).get(result.candidate_id),
                    suggested_action=action,
                    metadata={
                        "validation_source": result.validation_source,
                        "status": result.status,
                        "is_stable": result.is_stable,
                        "novelty_label": result.novelty_label,
                    },
                )
            )
        return buffer

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_count": len(self.events),
            "positive_evidence_count": self.positive_evidence_count,
            "negative_evidence_count": self.negative_evidence_count,
            "sampling_hints": self.sampling_hints(),
            "events": [event.to_dict() for event in self.events],
        }

    @property
    def positive_evidence_count(self) -> int:
        return sum(event.decision == "positive_evidence" for event in self.events)

    @property
    def negative_evidence_count(self) -> int:
        return sum(event.decision == "negative_evidence" for event in self.events)

    def positive_candidate_ids(self) -> set[str]:
        return {event.candidate_id for event in self.events if event.decision == "positive_evidence"}

    def negative_candidate_ids(self) -> set[str]:
        return {event.candidate_id for event in self.events if event.decision == "negative_evidence"}

    def sampling_hints(self) -> dict[str, Any]:
        return {
            "prefer_candidate_ids": sorted(self.positive_candidate_ids()),
            "avoid_candidate_ids": sorted(self.negative_candidate_ids()),
            "notes": "Mock hints only; no generator training is performed.",
        }


@dataclass(slots=True)
class ActiveLoopState:
    """Serializable state for a mock active discovery loop."""

    current_round: int
    total_rounds: int
    feedback_event_count: int
    positive_evidence_count: int
    negative_evidence_count: int
    sampling_hints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "feedback_event_count": self.feedback_event_count,
            "positive_evidence_count": self.positive_evidence_count,
            "negative_evidence_count": self.negative_evidence_count,
            "sampling_hints": dict(self.sampling_hints),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActiveLoopState":
        return cls(
            current_round=int(data.get("current_round", 0)),
            total_rounds=int(data.get("total_rounds", 0)),
            feedback_event_count=int(data.get("feedback_event_count", 0)),
            positive_evidence_count=int(data.get("positive_evidence_count", 0)),
            negative_evidence_count=int(data.get("negative_evidence_count", 0)),
            sampling_hints=dict(data.get("sampling_hints", {})),
            metadata=dict(data.get("metadata", {})),
        )


def run_mock_active_loop(
    config: ExperimentConfig | str | Path,
    validation_results: Sequence[ValidationResult] | None = None,
    output_dir: str | Path = "outputs/mock_active_loop",
    input_path: str | Path | None = None,
    rounds: int = 3,
) -> dict[str, Any]:
    """Run a deterministic mock active discovery loop."""

    base_config = _load_config(config)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    source_input = str(input_path or base_config.input_path)
    base_structures = read_mock_candidates_jsonl(source_input)
    feedback_buffer = FeedbackBuffer()
    round_rows: list[dict[str, Any]] = []

    for index in range(1, rounds + 1):
        round_id = f"round_{index:03d}"
        round_dir = root / round_id
        round_dir.mkdir(parents=True, exist_ok=True)
        round_input = source_input
        if index > 1:
            adjusted = _prepare_round_structures(base_structures, feedback_buffer, index)
            round_input = str(round_dir / "round_input_candidates.jsonl")
            write_jsonl(round_input, adjusted)
        round_config = merge_config_overrides(
            base_config,
            {
                "input_path": round_input,
                "output_dir": str(round_dir),
            },
        )
        result = run_fiir_experiment(round_config, validation_results=validation_results)
        vectors_by_id = {vector.candidate_id: vector for vector in result["failure_vectors"]}
        feedback_buffer.extend(
            FeedbackBuffer.from_feedback_records(result["discovery_run"].feedback_records, round_id).events
        )
        if index == 1 and validation_results is not None:
            feedback_buffer.extend(
                FeedbackBuffer.from_validation_results(validation_results, round_id, vectors_by_id).events
            )
        evaluation = result["evaluation_report"].as_dict()
        round_rows.append(
            {
                "round_id": round_id,
                "output_dir": str(round_dir),
                "pair_mode": result["summary"].get("pair_mode"),
                "pair_count": evaluation.get("pair_count"),
                "feedback_count": result["summary"].get("feedback_count"),
                "top_k_valid_rate": evaluation.get("top_k_valid_rate"),
                "validated_stable_rate": evaluation.get("validated_stable_rate"),
                "top_k_validated_stable_rate": evaluation.get("top_k_validated_stable_rate"),
            }
        )

    state = ActiveLoopState(
        current_round=rounds,
        total_rounds=rounds,
        feedback_event_count=len(feedback_buffer.events),
        positive_evidence_count=feedback_buffer.positive_evidence_count,
        negative_evidence_count=feedback_buffer.negative_evidence_count,
        sampling_hints=feedback_buffer.sampling_hints(),
        metadata={
            "input_path": source_input,
            "validation_count": len(validation_results) if validation_results is not None else 0,
        },
    )
    summary = {
        "output_dir": str(root),
        "round_count": rounds,
        "rounds": round_rows,
        "feedback_event_count": len(feedback_buffer.events),
        "positive_evidence_count": feedback_buffer.positive_evidence_count,
        "negative_evidence_count": feedback_buffer.negative_evidence_count,
        "sampling_hints": feedback_buffer.sampling_hints(),
        "generated_files": [
            str(root / "active_loop_summary.json"),
            str(root / "active_loop_state.json"),
            str(root / "active_loop_report.md"),
            str(root / "feedback_buffer.jsonl"),
        ],
    }
    write_jsonl(root / "feedback_buffer.jsonl", feedback_buffer.events)
    write_json(root / "active_loop_state.json", state)
    write_json(root / "active_loop_summary.json", summary)
    (root / "active_loop_report.md").write_text(render_active_loop_report(summary), encoding="utf-8")
    return {
        "summary": summary,
        "state": state,
        "feedback_buffer": feedback_buffer,
        "output_dir": root,
    }


def _validation_decision(result: ValidationResult) -> tuple[str, str]:
    if result.succeeded and result.is_stable is True:
        return "positive_evidence", "sample_similar_mock_family"
    if result.status.lower() in {"failed", "error"}:
        return "negative_evidence", "treat_failed_validation_as_future_negative"
    if result.succeeded and result.is_stable is False:
        return "negative_evidence", "avoid_similar_high_failure_candidates"
    return "pending_evidence", "defer_until_validation_completes"


def _prepare_round_structures(
    structures: Sequence[StructureLike],
    feedback_buffer: FeedbackBuffer,
    round_index: int,
) -> list[StructureLike]:
    positive = feedback_buffer.positive_candidate_ids()
    negative = feedback_buffer.negative_candidate_ids()
    adjusted: list[StructureLike] = []
    for structure in structures:
        item = StructureLike.from_dict(structure.to_dict())
        metadata = dict(item.metadata)
        novelty = float(metadata.get("mock_novelty", 0.5))
        diversity = float(metadata.get("mock_diversity", 0.5))
        if item.candidate_id in positive:
            metadata["mock_novelty"] = min(1.0, novelty + 0.02 * round_index)
            metadata["mock_diversity"] = min(1.0, diversity + 0.01 * round_index)
            metadata["feedback_hint"] = "positive_evidence"
        elif item.candidate_id in negative:
            metadata["mock_novelty"] = max(0.0, novelty - 0.03 * round_index)
            metadata["feedback_hint"] = "negative_evidence"
        else:
            metadata["feedback_hint"] = "neutral"
        item.metadata = metadata
        adjusted.append(item)
    adjusted.sort(key=lambda item: (item.metadata.get("feedback_hint") != "positive_evidence", item.candidate_id))
    return adjusted


def _load_config(config: ExperimentConfig | str | Path) -> ExperimentConfig:
    if isinstance(config, ExperimentConfig):
        return config
    return load_experiment_config(config)
