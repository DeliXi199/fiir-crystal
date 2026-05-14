"""Build CrystalFormer DPO preference-pair records from FIIR audit output.

This module prepares data only. It does not train DPO models and does not run
DFT, MLFF relaxation, or external validation.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Sequence

from fiir_crystal.io import write_json, write_jsonl


SEQUENCE_FIELDS = ("g", "W", "A", "X", "L")
GEOMETRY_CHEMISTRY_ONLY = "geometry_chemistry_only"
STABILITY_AWARE_OFFLINE_VALIDATION = "stability_aware_offline_validation"


@dataclass(slots=True)
class PreferenceBuildConfig:
    """Configuration for CrystalFormer audit-to-DPO pair construction."""

    formula: str | None = None
    spacegroup: int | None = None
    min_preference_margin: float = 1e-6
    max_pairs: int | None = None
    require_dpo_eligible: bool = True
    require_raw_sequence: bool = True
    allowed_preference_types: tuple[str, ...] = (
        GEOMETRY_CHEMISTRY_ONLY,
        STABILITY_AWARE_OFFLINE_VALIDATION,
    )


@dataclass(slots=True)
class DPOPreferencePair:
    """Schema-first DPO pair for later CrystalFormer training."""

    pair_id: str
    condition: dict[str, Any]
    chosen_candidate_id: str
    rejected_candidate_id: str
    chosen_sequence: dict[str, Any]
    rejected_sequence: dict[str, Any]
    chosen_score: float
    rejected_score: float
    preference_margin: float
    preference_type: str
    preference_reason: list[str]
    chosen_failure_vector: dict[str, Any]
    rejected_failure_vector: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "condition": dict(self.condition),
            "chosen_candidate_id": self.chosen_candidate_id,
            "rejected_candidate_id": self.rejected_candidate_id,
            "chosen_sequence": dict(self.chosen_sequence),
            "rejected_sequence": dict(self.rejected_sequence),
            "chosen_score": self.chosen_score,
            "rejected_score": self.rejected_score,
            "preference_margin": self.preference_margin,
            "preference_type": self.preference_type,
            "preference_reason": list(self.preference_reason),
            "chosen_failure_vector": dict(self.chosen_failure_vector),
            "rejected_failure_vector": dict(self.rejected_failure_vector),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PreferenceBuildSummary:
    """Summary for an audit-to-DPO preference build."""

    input_candidate_count: int
    usable_candidate_count: int
    pair_count: int
    skipped_pair_count: int
    skip_reasons: dict[str, int]
    condition_count: int
    preference_type_breakdown: dict[str, int]
    formula: str | None = None
    spacegroup: int | None = None
    train_dpo: bool = False
    stability_preferences: bool = False
    candidate_skip_reasons: dict[str, int] = field(default_factory=dict)
    pair_skip_reasons: dict[str, int] = field(default_factory=dict)
    condition_breakdown: dict[str, int] = field(default_factory=dict)
    no_comparable_condition_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_candidate_count": self.input_candidate_count,
            "usable_candidate_count": self.usable_candidate_count,
            "pair_count": self.pair_count,
            "skipped_pair_count": self.skipped_pair_count,
            "skip_reasons": dict(self.skip_reasons),
            "condition_count": self.condition_count,
            "preference_type_breakdown": dict(self.preference_type_breakdown),
            "formula": self.formula,
            "spacegroup": self.spacegroup,
            "train_dpo": self.train_dpo,
            "stability_preferences": self.stability_preferences,
            "candidate_skip_reasons": dict(self.candidate_skip_reasons),
            "pair_skip_reasons": dict(self.pair_skip_reasons),
            "condition_breakdown": dict(self.condition_breakdown),
            "no_comparable_condition_count": self.no_comparable_condition_count,
        }


def read_audit_candidates(path: str | Path) -> list[dict[str, Any]]:
    """Read audit candidate JSONL rows."""

    rows: list[dict[str, Any]] = []
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            if not isinstance(data, dict):
                raise ValueError(f"{source}:{line_no}: audit candidate row must be an object")
            rows.append(data)
    return rows


def build_dpo_preferences(
    audit_candidates: Sequence[dict[str, Any]],
    config: PreferenceBuildConfig | None = None,
) -> tuple[list[DPOPreferencePair], PreferenceBuildSummary]:
    """Build same-condition DPO preference pairs from audit rows."""

    cfg = config or PreferenceBuildConfig()
    usable, candidate_skip_counter = _usable_candidates(audit_candidates, cfg)
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        groups[_condition_key(row, cfg)].append(row)

    pair_skip_counter: Counter[str] = Counter()
    pair_skip_counter.update(_cross_condition_skip_reasons(groups))
    if len(usable) < 2:
        pair_skip_counter["no_comparable_candidates"] += 1

    pairs: list[DPOPreferencePair] = []
    for group_key, rows in sorted(groups.items(), key=lambda item: str(item[0])):
        rows = sorted(rows, key=lambda row: (_sort_score(row), str(row["candidate_id"])))
        group_pair_start = len(pairs)
        for left_index, chosen in enumerate(rows):
            for rejected in rows[left_index + 1 :]:
                pair, reason = _make_pair(chosen, rejected, cfg)
                if pair is None:
                    pair_skip_counter[reason or "skipped"] += 1
                    continue
                pairs.append(pair)
                if cfg.max_pairs is not None and len(pairs) >= cfg.max_pairs:
                    summary = _summary(
                        audit_candidates,
                        usable,
                        pairs,
                        candidate_skip_counter,
                        pair_skip_counter,
                        groups,
                        cfg,
                    )
                    return pairs, summary
        if len(rows) < 2:
            pair_skip_counter["condition_group_too_small"] += 1
        elif len(pairs) == group_pair_start:
            pair_skip_counter["no_comparable_candidates"] += 1

    summary = _summary(
        audit_candidates,
        usable,
        pairs,
        candidate_skip_counter,
        pair_skip_counter,
        groups,
        cfg,
    )
    return pairs, summary


def write_preference_outputs(
    output_dir: str | Path,
    pairs: Sequence[DPOPreferencePair],
    summary: PreferenceBuildSummary,
) -> dict[str, str]:
    """Write preference pairs, summary, and report."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "preference_pairs": str(destination / "preference_pairs.jsonl"),
        "preference_summary": str(destination / "preference_summary.json"),
        "report": str(destination / "report.md"),
    }
    write_jsonl(files["preference_pairs"], pairs)
    write_json(files["preference_summary"], summary)
    Path(files["report"]).write_text(_render_report(summary), encoding="utf-8")
    return files


def _usable_candidates(
    rows: Sequence[dict[str, Any]],
    cfg: PreferenceBuildConfig,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    usable: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for row in rows:
        reason = _candidate_skip_reason(row, cfg)
        if reason is None:
            usable.append(row)
        else:
            skipped[reason] += 1
            for extra_reason in _candidate_extra_reasons(row):
                if extra_reason != reason:
                    skipped[extra_reason] += 1
    return usable, skipped


def _candidate_skip_reason(row: dict[str, Any], cfg: PreferenceBuildConfig) -> str | None:
    if cfg.require_dpo_eligible and not bool(row.get("dpo_eligible")):
        return "not_dpo_eligible"
    if not row.get("candidate_id"):
        return "missing_candidate_id"
    if row.get("parse_status") == "parse_error":
        return "parse_error"
    if _score(row) is None:
        return "missing_fiir_score"
    condition = _condition(row, cfg)
    if cfg.formula is not None and condition.get("formula") != cfg.formula:
        return "formula_mismatch"
    if cfg.spacegroup is not None and condition.get("spacegroup") != cfg.spacegroup:
        return "spacegroup_mismatch"
    if cfg.require_raw_sequence and not _has_full_sequence(row):
        return _raw_sequence_skip_reason(row)
    preference_type = _preference_type(row)
    if preference_type not in cfg.allowed_preference_types:
        return "preference_type_not_allowed"
    return None


def _make_pair(
    chosen: dict[str, Any],
    rejected: dict[str, Any],
    cfg: PreferenceBuildConfig,
) -> tuple[DPOPreferencePair | None, str | None]:
    if _condition_key(chosen, cfg) != _condition_key(rejected, cfg):
        return None, "condition_mismatch"

    chosen_score = _score(chosen)
    rejected_score = _score(rejected)
    if chosen_score is None or rejected_score is None:
        return None, "missing_fiir_score"
    if chosen_score > rejected_score:
        chosen, rejected = rejected, chosen
        chosen_score, rejected_score = rejected_score, chosen_score

    margin = round(rejected_score - chosen_score, 12)
    if margin < cfg.min_preference_margin:
        return None, "no_comparable_margin"
    if _has_f3_validation(chosen) != _has_f3_validation(rejected):
        return None, "mixed_f3_validation_availability"

    preference_type = _pair_preference_type(chosen, rejected)
    if preference_type not in cfg.allowed_preference_types:
        return None, "preference_type_not_allowed"

    condition = _condition(chosen, cfg)
    return DPOPreferencePair(
        pair_id=f"{condition.get('formula') or 'unknown'}:{chosen['candidate_id']}>{rejected['candidate_id']}",
        condition=condition,
        chosen_candidate_id=str(chosen["candidate_id"]),
        rejected_candidate_id=str(rejected["candidate_id"]),
        chosen_sequence=_sequence(chosen),
        rejected_sequence=_sequence(rejected),
        chosen_score=float(chosen_score),
        rejected_score=float(rejected_score),
        preference_margin=margin,
        preference_type=preference_type,
        preference_reason=_preference_reason(chosen, rejected),
        chosen_failure_vector=dict(chosen.get("failure_vector", {})),
        rejected_failure_vector=dict(rejected.get("failure_vector", {})),
        metadata={
            "source": "fiir_crystal.dpo.preference_builder",
            "dpo_training": False,
            "stability_preference": preference_type == STABILITY_AWARE_OFFLINE_VALIDATION,
            "chosen_parse_status": chosen.get("parse_status"),
            "rejected_parse_status": rejected.get("parse_status"),
            "chosen_raw_sequence_status": chosen.get("raw_sequence_status"),
            "rejected_raw_sequence_status": rejected.get("raw_sequence_status"),
            "chosen_missing_sequence_fields": _missing_sequence_fields(chosen),
            "rejected_missing_sequence_fields": _missing_sequence_fields(rejected),
        },
    ), None


def _summary(
    input_rows: Sequence[dict[str, Any]],
    usable_rows: Sequence[dict[str, Any]],
    pairs: Sequence[DPOPreferencePair],
    candidate_skipped: Counter[str],
    pair_skipped: Counter[str],
    groups: dict[tuple[Any, ...], list[dict[str, Any]]],
    cfg: PreferenceBuildConfig,
) -> PreferenceBuildSummary:
    preference_types = Counter(pair.preference_type for pair in pairs)
    skipped = candidate_skipped + pair_skipped
    return PreferenceBuildSummary(
        input_candidate_count=len(input_rows),
        usable_candidate_count=len(usable_rows),
        pair_count=len(pairs),
        skipped_pair_count=sum(skipped.values()),
        skip_reasons=dict(sorted(skipped.items())),
        condition_count=len(groups),
        preference_type_breakdown=dict(sorted(preference_types.items())),
        formula=cfg.formula,
        spacegroup=cfg.spacegroup,
        train_dpo=False,
        stability_preferences=any(
            pair.preference_type == STABILITY_AWARE_OFFLINE_VALIDATION for pair in pairs
        ),
        candidate_skip_reasons=dict(sorted(candidate_skipped.items())),
        pair_skip_reasons=dict(sorted(pair_skipped.items())),
        condition_breakdown=_condition_breakdown(groups),
        no_comparable_condition_count=sum(
            1
            for rows in groups.values()
            if len(rows) < 2
            or not any(
                _score_gap(left, right) >= cfg.min_preference_margin
                for left, right in combinations(rows, 2)
            )
        ),
    )


def _condition(row: dict[str, Any], cfg: PreferenceBuildConfig) -> dict[str, Any]:
    condition = dict(row.get("condition", {}))
    formula = condition.get("formula") or row.get("composition") or cfg.formula
    spacegroup = condition.get("spacegroup")
    if spacegroup in (None, "", "null", "None", "none"):
        spacegroup = cfg.spacegroup
    return {
        "mode": condition.get("mode", "csp"),
        "formula": formula,
        "spacegroup": _optional_int(spacegroup),
        "generation": _generation_condition(condition),
    }


def _condition_key(row: dict[str, Any], cfg: PreferenceBuildConfig) -> tuple[Any, ...]:
    condition = _condition(row, cfg)
    return (
        condition.get("mode"),
        condition.get("formula"),
        condition.get("spacegroup"),
        _freeze_generation_condition(condition.get("generation")),
    )


def _score(row: dict[str, Any]) -> float | None:
    value = row.get("fiir_score")
    if value is not None:
        return float(value)
    ranking_score = row.get("ranking_score")
    if ranking_score is None:
        return None
    # `ranking_score` is a success-like score (`1 - fiir_score`), so convert
    # it back to the lower-is-better failure score used for pair ordering.
    return 1.0 - float(ranking_score)


def _sort_score(row: dict[str, Any]) -> float:
    score = _score(row)
    return float("inf") if score is None else score


def _score_gap(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_score = _score(left)
    right_score = _score(right)
    if left_score is None or right_score is None:
        return 0.0
    return abs(float(left_score) - float(right_score))


def _sequence(row: dict[str, Any]) -> dict[str, Any]:
    fields = row.get("raw_sequence_fields")
    if not isinstance(fields, dict):
        fields = {}
    return {field: fields.get(field) for field in SEQUENCE_FIELDS}


def _has_full_sequence(row: dict[str, Any]) -> bool:
    sequence = _sequence(row)
    return all(sequence.get(field) not in (None, "", []) for field in SEQUENCE_FIELDS)


def _raw_sequence_skip_reason(row: dict[str, Any]) -> str:
    sequence = _sequence(row)
    present = [
        field
        for field in SEQUENCE_FIELDS
        if sequence.get(field) not in (None, "", [])
    ]
    return "missing_raw_sequence" if not present else "partial_raw_sequence"


def _missing_sequence_fields(row: dict[str, Any]) -> list[str]:
    sequence = _sequence(row)
    return [
        field
        for field in SEQUENCE_FIELDS
        if sequence.get(field) in (None, "", [])
    ]


def _candidate_extra_reasons(row: dict[str, Any]) -> list[str]:
    reasons = row.get("dpo_ineligible_reasons")
    if not isinstance(reasons, list):
        return []
    return [str(reason) for reason in reasons if reason]


def _preference_type(row: dict[str, Any]) -> str:
    if row.get("preference_type"):
        return str(row["preference_type"])
    if _has_f3_validation(row):
        return STABILITY_AWARE_OFFLINE_VALIDATION
    if _f3_unavailable(row):
        return GEOMETRY_CHEMISTRY_ONLY
    return "stability_available"


def _pair_preference_type(chosen: dict[str, Any], rejected: dict[str, Any]) -> str:
    if _has_f3_validation(chosen) and _has_f3_validation(rejected):
        return STABILITY_AWARE_OFFLINE_VALIDATION
    if _f3_unavailable(chosen) or _f3_unavailable(rejected):
        return GEOMETRY_CHEMISTRY_ONLY
    return "stability_available"


def _preference_reason(chosen: dict[str, Any], rejected: dict[str, Any]) -> list[str]:
    reasons = ["lower_fiir_score"]
    if _f3_unavailable(chosen) or _f3_unavailable(rejected):
        reasons.append("f3_unavailable_geometry_chemistry_only")
    if _has_f3_validation(chosen) and _has_f3_validation(rejected):
        reasons.append("offline_validation_stability_signal")
    return reasons


def _has_f3_validation(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("f3_validation_available"))
        and row.get("validation_status") == "validated_success"
        and isinstance(row.get("offline_validation"), dict)
    )


def _f3_unavailable(row: dict[str, Any]) -> bool:
    if row.get("f3_label") in {"unknown", "unavailable"}:
        return True
    evidence = row.get("evidence")
    if isinstance(evidence, dict) and evidence.get("f3_status") in {
        "unknown",
        "unavailable",
        "unknown_unavailable",
    }:
        return True
    failure_vector = row.get("failure_vector")
    return isinstance(failure_vector, dict) and failure_vector.get("f3_stability") is None


def _generation_condition(condition: dict[str, Any]) -> dict[str, Any]:
    generation = condition.get("generation")
    if not isinstance(generation, dict):
        generation = {}
    return {
        str(key): generation[key]
        for key in sorted(generation)
        if generation[key] not in (None, "")
    }


def _freeze_generation_condition(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        return ()
    return tuple(
        (str(key), json.dumps(value[key], sort_keys=True))
        for key in sorted(value)
        if value[key] not in (None, "")
    )


def _cross_condition_skip_reasons(
    groups: dict[tuple[Any, ...], list[dict[str, Any]]],
) -> Counter[str]:
    skipped: Counter[str] = Counter()
    for left_key, right_key in combinations(groups, 2):
        count = len(groups[left_key]) * len(groups[right_key])
        if left_key[1] != right_key[1]:
            skipped["different_formula_condition"] += count
        elif left_key[2] != right_key[2]:
            skipped["different_spacegroup_condition"] += count
        elif left_key[3] != right_key[3]:
            skipped["different_generation_condition"] += count
        else:
            skipped["condition_mismatch"] += count
    return skipped


def _condition_breakdown(groups: dict[tuple[Any, ...], list[dict[str, Any]]]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for key, rows in groups.items():
        label = "|".join(str(part) for part in key)
        breakdown[label] = len(rows)
    return dict(sorted(breakdown.items()))


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
        return None
    return int(float(str(value)))


def _render_report(summary: PreferenceBuildSummary) -> str:
    data = summary.to_dict()
    lines = [
        "# CrystalFormer DPO Preference Build Report",
        "",
        "## Scope",
        "- This prepares preference-pair data only.",
        "- This does not train DPO and does not modify CrystalFormer.",
        "- No DFT, MLFF relaxation, Materials Project calls, or external validation are run.",
        "- Without F3 validation, emitted pairs are limited to geometry/chemistry preferences.",
        "",
        "## Summary",
        f"- input_candidate_count: {data['input_candidate_count']}",
        f"- usable_candidate_count: {data['usable_candidate_count']}",
        f"- pair_count: {data['pair_count']}",
        f"- skipped_pair_count: {data['skipped_pair_count']}",
        f"- skip_reasons: {data['skip_reasons']}",
        f"- candidate_skip_reasons: {data['candidate_skip_reasons']}",
        f"- pair_skip_reasons: {data['pair_skip_reasons']}",
        f"- condition_count: {data['condition_count']}",
        f"- no_comparable_condition_count: {data['no_comparable_condition_count']}",
        f"- preference_type_breakdown: {data['preference_type_breakdown']}",
        "",
    ]
    if summary.pair_count == 0:
        lines.extend(
            [
                "## Pairing Note",
                "- No preference pairs were emitted. This is expected when all eligible candidates have equal FIIR scores or no comparable margin.",
                "",
            ]
        )
    return "\n".join(lines)
