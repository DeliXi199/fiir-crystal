#!/usr/bin/env python
"""Build F3-isolated DPO preferences from three-MLIP relaxation evidence.

The regular preference builder ranks candidates by the aggregate FIIR score.
This script is intentionally narrower: it emits same-formula good-vs-near-miss
MLIP relaxation pairs where F1 and F2 are controlled to the same passing values.
"""

from __future__ import annotations

import argparse
import glob
import math
import platform
import socket
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)
if PROJECT_ROOT_TEXT in sys.path:
    sys.path.remove(PROJECT_ROOT_TEXT)
sys.path.insert(0, PROJECT_ROOT_TEXT)

from fiir_crystal.dpo import (
    DPOPreferencePair,
    STABILITY_AWARE_OFFLINE_VALIDATION,
    validate_preference_pairs_for_training,
)
from fiir_crystal.dpo.preference_builder import SEQUENCE_FIELDS
from fiir_crystal.io import read_jsonl, write_json, write_jsonl


DEFAULT_OUTPUT_DIR = Path("outputs/dpo_preferences/f3_isolated_mlip_consensus")
MLIP_MODELS = ("MACE", "CHGNet", "MatGL")
MODEL_KEY_ALIASES = {
    "MACE": ("MACE", "mace"),
    "CHGNet": ("CHGNet", "chgnet"),
    "MatGL": ("MatGL", "matgl"),
}
GOOD_FORCE_MAX = 0.05
NEAR_MISS_FORCE_MAX = 0.10
RANK_NEIGHBOR_COUNT = 5
F3_PAIR_RULE_ID = "same_formula_rank_neighbor_f3_pairing_v1"


@dataclass(frozen=True, slots=True)
class F3Candidate:
    """Candidate with controlled F1/F2 and imported three-MLIP force evidence."""

    candidate_id: str
    raw_candidate_id: str
    formula: str
    audit_row: dict[str, Any]
    consensus_row: dict[str, Any]
    f1_geometry: float
    f2_chemistry: float
    model_forces: dict[str, float]
    model_converged: dict[str, bool | None]
    model_stresses: dict[str, float | None]
    model_energies: dict[str, float | None]
    mean_force_max: float
    sample_label: str | None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build F3-only good-vs-near-miss DPO pairs from three-MLIP relaxation evidence."
    )
    parser.add_argument("--consensus-jsonl", required=True)
    parser.add_argument("--audit-candidates-jsonl", action="append", default=[])
    parser.add_argument("--audit-glob", action="append", default=[])
    parser.add_argument("--candidate-id-prefix", default="")
    parser.add_argument("--sample-label")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--good-force-max", type=float, default=GOOD_FORCE_MAX)
    parser.add_argument("--near-miss-force-max", type=float, default=NEAR_MISS_FORCE_MAX)
    parser.add_argument("--rank-neighbor-count", type=int, default=RANK_NEIGHBOR_COUNT)
    parser.add_argument("--max-pairs-per-formula", type=int)
    parser.add_argument("--require-f1-f2-pass", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fail-on-zero-pairs", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = parse_args(argv)
    if args.max_pairs_per_formula is not None and args.max_pairs_per_formula < 1:
        raise SystemExit("--max-pairs-per-formula must be positive")
    if args.good_force_max <= 0:
        raise SystemExit("--good-force-max must be positive")
    if args.near_miss_force_max <= args.good_force_max:
        raise SystemExit("--near-miss-force-max must be larger than --good-force-max")
    if args.rank_neighbor_count < 1:
        raise SystemExit("--rank-neighbor-count must be positive")

    audit_paths = _paths(args.audit_candidates_jsonl, args.audit_glob)
    if not audit_paths:
        raise SystemExit("no audit candidate JSONL files were provided or matched")

    output_dir = Path(args.output_dir)
    dpo_dir = output_dir / "dpo_preferences"
    output_dir.mkdir(parents=True, exist_ok=True)

    audit_rows = _read_audit_rows(audit_paths)
    consensus_rows = read_jsonl(args.consensus_jsonl)
    candidates, candidate_skips = _matched_candidates(
        audit_rows,
        consensus_rows,
        candidate_id_prefix=args.candidate_id_prefix,
        sample_label=args.sample_label,
        require_f1_f2_pass=args.require_f1_f2_pass,
    )
    pairs, pair_skips, formula_stats = _build_pairs(
        candidates,
        good_force_max=args.good_force_max,
        near_miss_force_max=args.near_miss_force_max,
        rank_neighbor_count=args.rank_neighbor_count,
        max_pairs_per_formula=args.max_pairs_per_formula,
    )

    pair_rows = [pair.to_dict() for pair in pairs]
    validation_summary = validate_preference_pairs_for_training(pair_rows)
    summary = _summary(
        args=args,
        audit_paths=audit_paths,
        consensus_rows=consensus_rows,
        candidates=candidates,
        pairs=pairs,
        candidate_skips=candidate_skips,
        pair_skips=pair_skips,
        formula_stats=formula_stats,
        validation_summary=validation_summary.to_dict(),
    )

    files = {
        "audit_candidates": output_dir / "audit_candidates.jsonl",
        "matched_candidates": output_dir / "matched_f3_candidates.jsonl",
        "preference_pairs": dpo_dir / "preference_pairs.jsonl",
        "preference_summary": dpo_dir / "preference_summary.json",
        "report": dpo_dir / "report.md",
    }
    write_jsonl(files["audit_candidates"], [_audit_candidate_record(candidate) for candidate in candidates])
    write_jsonl(files["matched_candidates"], [_candidate_record(candidate) for candidate in candidates])
    write_jsonl(files["preference_pairs"], pairs)
    write_json(files["preference_summary"], summary)
    files["report"].write_text(_render_report(summary), encoding="utf-8")

    print("F3-isolated DPO preference build complete")
    print(f"  consensus_rows: {len(consensus_rows)}")
    print(f"  matched_f3_candidates: {len(candidates)}")
    print(f"  preference_pairs: {len(pairs)}")
    print(f"  valid_training_pairs: {validation_summary.valid_pair_count}")
    print(f"  preference_pairs_jsonl: {files['preference_pairs']}")

    if args.fail_on_zero_pairs and not pairs:
        raise SystemExit("no F3-isolated DPO preference pairs were built")

    return {
        "summary": summary,
        "files": {key: str(value) for key, value in files.items()},
    }


def _paths(explicit: Iterable[str], patterns: Iterable[str]) -> list[Path]:
    paths = [Path(path) for path in explicit]
    for pattern in patterns:
        paths.extend(Path(path) for path in glob.glob(pattern))
    return sorted({path.resolve() for path in paths if path.exists() and path.is_file()})


def _read_audit_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for row in read_jsonl(path):
            copied = dict(row)
            copied.setdefault("audit_source_jsonl", str(path))
            rows.append(copied)
    return rows


def _matched_candidates(
    audit_rows: list[dict[str, Any]],
    consensus_rows: list[dict[str, Any]],
    *,
    candidate_id_prefix: str,
    sample_label: str | None,
    require_f1_f2_pass: bool,
) -> tuple[list[F3Candidate], Counter[str]]:
    audit_by_id = {str(row.get("candidate_id")): row for row in audit_rows if row.get("candidate_id")}
    skipped: Counter[str] = Counter()
    candidates: list[F3Candidate] = []
    seen: set[str] = set()
    for consensus in consensus_rows:
        consensus_id = str(consensus.get("candidate_id") or "")
        if not consensus_id:
            skipped["missing_consensus_candidate_id"] += 1
            continue
        raw_id = _strip_prefix(consensus_id, candidate_id_prefix)
        audit = audit_by_id.get(raw_id)
        if audit is None:
            skipped["missing_audit_candidate"] += 1
            continue
        if consensus_id in seen:
            skipped["duplicate_consensus_candidate_id"] += 1
            continue
        seen.add(consensus_id)

        if consensus.get("validation_status") != "completed":
            skipped["consensus_not_completed"] += 1
            continue
        model_forces = _model_float_map(consensus, "force_max")
        if set(model_forces) != set(MLIP_MODELS):
            skipped["missing_three_mlip_force_evidence"] += 1
            continue
        model_converged = _model_bool_map(consensus, "relaxation_converged")
        model_stresses = _model_float_map(consensus, "stress_max", require_all=False)
        model_energies = _model_float_map(consensus, "energy_eV_per_atom", require_all=False)
        if not _has_full_sequence(audit):
            skipped["missing_raw_sequence"] += 1
            continue
        f1 = _optional_float(_failure_vector(audit).get("f1_geometry"))
        f2 = _optional_float(_failure_vector(audit).get("f2_chemistry"))
        if f1 is None or f2 is None:
            skipped["missing_f1_or_f2"] += 1
            continue
        if require_f1_f2_pass and (f1 != 0.0 or f2 != 0.0):
            skipped["f1_f2_not_passing"] += 1
            continue
        if not bool(audit.get("dpo_eligible", True)):
            skipped["not_dpo_eligible"] += 1
            continue
        if str(audit.get("parse_status")) == "parse_error":
            skipped["parse_error"] += 1
            continue
        formula = str(consensus.get("formula") or audit.get("composition") or "")
        if not formula:
            skipped["missing_formula"] += 1
            continue
        candidates.append(
            F3Candidate(
                candidate_id=consensus_id,
                raw_candidate_id=raw_id,
                formula=formula,
                audit_row=audit,
                consensus_row=consensus,
                f1_geometry=f1,
                f2_chemistry=f2,
                model_forces=model_forces,
                model_converged=model_converged,
                model_stresses=model_stresses,
                model_energies=model_energies,
                mean_force_max=sum(model_forces.values()) / len(model_forces),
                sample_label=sample_label,
            )
        )
    candidates.sort(key=lambda candidate: (candidate.formula, candidate.candidate_id))
    return candidates, skipped


def _build_pairs(
    candidates: list[F3Candidate],
    *,
    good_force_max: float,
    near_miss_force_max: float,
    rank_neighbor_count: int,
    max_pairs_per_formula: int | None,
) -> tuple[list[DPOPreferencePair], Counter[str], dict[str, dict[str, int]]]:
    by_formula: dict[str, list[F3Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_formula[candidate.formula].append(candidate)

    skipped: Counter[str] = Counter()
    pairs: list[DPOPreferencePair] = []
    formula_stats: dict[str, dict[str, int]] = {}
    for formula in sorted(by_formula):
        good = sorted(
            (
                candidate
                for candidate in by_formula[formula]
                if _is_good_candidate(candidate, good_force_max=good_force_max)
            ),
            key=_force_rank,
        )
        near_miss = sorted(
            (
                candidate
                for candidate in by_formula[formula]
                if _is_near_miss_candidate(
                    candidate,
                    good_force_max=good_force_max,
                    near_miss_force_max=near_miss_force_max,
                )
            ),
            key=_force_rank,
        )
        formula_stats[formula] = {
            "f3_good_candidate_count": len(good),
            "f3_near_miss_candidate_count": len(near_miss),
            "possible_rank_neighbor_pair_count": sum(
                min(rank_neighbor_count, len(_compatible_candidates(candidate, near_miss))) for candidate in good
            ),
            "emitted_pair_count": 0,
        }
        if not good or not near_miss:
            skipped["formula_missing_good_or_near_miss"] += 1
            continue

        formula_pairs: list[tuple[F3Candidate, F3Candidate]] = []
        for good_index, chosen in enumerate(good):
            compatible_near = _compatible_candidates(chosen, near_miss)
            if not compatible_near:
                continue
            neighbors = _rank_neighbors(
                good_index,
                len(good),
                compatible_near,
                rank_neighbor_count=rank_neighbor_count,
            )
            formula_pairs.extend((chosen, rejected) for rejected in neighbors)
        if not formula_pairs:
            skipped["formula_no_f1_f2_matched_pairs"] += 1
            continue
        if max_pairs_per_formula is not None:
            formula_pairs = formula_pairs[:max_pairs_per_formula]

        for chosen, rejected in formula_pairs:
            pairs.append(_make_pair(chosen, rejected, good_force_max, near_miss_force_max, rank_neighbor_count))
        formula_stats[formula]["emitted_pair_count"] = len(formula_pairs)

    return pairs, skipped, formula_stats


def _make_pair(
    chosen: F3Candidate,
    rejected: F3Candidate,
    good_force_max: float,
    near_miss_force_max: float,
    rank_neighbor_count: int,
) -> DPOPreferencePair:
    chosen_failure = _f3_failure_vector(chosen)
    rejected_failure = _f3_failure_vector(rejected)
    return DPOPreferencePair(
        pair_id=f"{chosen.formula}:{chosen.candidate_id}>{rejected.candidate_id}",
        condition=_condition(chosen),
        chosen_candidate_id=chosen.candidate_id,
        rejected_candidate_id=rejected.candidate_id,
        chosen_sequence=_sequence(chosen.audit_row),
        rejected_sequence=_sequence(rejected.audit_row),
        chosen_score=0.0,
        rejected_score=1.0,
        preference_margin=1.0,
        preference_type=STABILITY_AWARE_OFFLINE_VALIDATION,
        preference_reason=[
            F3_PAIR_RULE_ID,
            "good_vs_near_miss_mlip_force",
            "f1_f2_controlled",
        ],
        chosen_failure_vector=chosen_failure,
        rejected_failure_vector=rejected_failure,
        metadata={
            "source": "scripts/build_f3_isolated_dpo_preferences.py",
            "dpo_training": False,
            "stability_preference": True,
            "f3_only_preference": True,
            "f3_pair_rule": F3_PAIR_RULE_ID,
            "pair_score_semantics": "binary_preference_marker_not_normalized_f3_score",
            "good_force_max": good_force_max,
            "near_miss_force_max": near_miss_force_max,
            "rank_neighbor_count": rank_neighbor_count,
            "f1_f2_control": {
                "chosen_f1_geometry": chosen.f1_geometry,
                "chosen_f2_chemistry": chosen.f2_chemistry,
                "rejected_f1_geometry": rejected.f1_geometry,
                "rejected_f2_chemistry": rejected.f2_chemistry,
            },
            "sample_label": chosen.sample_label,
            "chosen_raw_candidate_id": chosen.raw_candidate_id,
            "rejected_raw_candidate_id": rejected.raw_candidate_id,
            "chosen_mlip_force_evidence": _mlip_evidence(chosen),
            "rejected_mlip_force_evidence": _mlip_evidence(rejected),
            "chosen_mean_force_max": chosen.mean_force_max,
            "rejected_mean_force_max": rejected.mean_force_max,
            "chosen_vote_pattern": chosen.consensus_row.get("metadata", {}).get("vote_pattern"),
            "rejected_vote_pattern": rejected.consensus_row.get("metadata", {}).get("vote_pattern"),
            "chosen_force_max": chosen.mean_force_max,
            "rejected_force_max": rejected.mean_force_max,
            "chosen_stress_max": chosen.consensus_row.get("stress_max"),
            "rejected_stress_max": rejected.consensus_row.get("stress_max"),
            "chosen_relaxation_converged": chosen.consensus_row.get("relaxation_converged"),
            "rejected_relaxation_converged": rejected.consensus_row.get("relaxation_converged"),
            "caveat": "F3 pairs are same-formula MLIP relaxation force preferences, not DFT hull labels.",
        },
    )


def _condition(candidate: F3Candidate) -> dict[str, Any]:
    source = candidate.audit_row.get("condition")
    condition = dict(source) if isinstance(source, dict) else {}
    generation = condition.get("generation")
    if not isinstance(generation, dict):
        generation = {}
    generation = {
        **generation,
        "f3_pair_objective": F3_PAIR_RULE_ID,
    }
    if candidate.sample_label:
        generation["sample_label"] = candidate.sample_label
    return {
        "mode": condition.get("mode", "csp"),
        "formula": candidate.formula,
        "spacegroup": None,
        "generation": dict(sorted(generation.items())),
    }


def _candidate_record(candidate: F3Candidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "raw_candidate_id": candidate.raw_candidate_id,
        "formula": candidate.formula,
        "sample_label": candidate.sample_label,
        "f1_geometry": candidate.f1_geometry,
        "f2_chemistry": candidate.f2_chemistry,
        "mean_force_max": candidate.mean_force_max,
        "model_forces": dict(candidate.model_forces),
        "model_converged": dict(candidate.model_converged),
        "model_stresses": dict(candidate.model_stresses),
        "model_energies": dict(candidate.model_energies),
        "vote_pattern": candidate.consensus_row.get("metadata", {}).get("vote_pattern"),
        "audit_source_jsonl": candidate.audit_row.get("audit_source_jsonl"),
    }


def _audit_candidate_record(candidate: F3Candidate) -> dict[str, Any]:
    row = dict(candidate.audit_row)
    row["candidate_id"] = candidate.candidate_id
    row["raw_candidate_id"] = candidate.raw_candidate_id
    row["composition"] = candidate.formula
    row["condition"] = _condition(candidate)
    row["dpo_eligible"] = bool(row.get("dpo_eligible", True))
    row["f3_label"] = "mlip_force_pair_evidence"
    row["f3_source"] = "three_mlip_relaxation_force_pairing"
    row["f3_validation_available"] = True
    row["failure_vector"] = _f3_failure_vector(candidate)
    row["mean_force_max"] = candidate.mean_force_max
    row["model_forces"] = dict(candidate.model_forces)
    row["model_converged"] = dict(candidate.model_converged)
    row["model_stresses"] = dict(candidate.model_stresses)
    row["model_energies"] = dict(candidate.model_energies)
    return row


def _summary(
    *,
    args: argparse.Namespace,
    audit_paths: list[Path],
    consensus_rows: list[dict[str, Any]],
    candidates: list[F3Candidate],
    pairs: list[DPOPreferencePair],
    candidate_skips: Counter[str],
    pair_skips: Counter[str],
    formula_stats: dict[str, dict[str, int]],
    validation_summary: dict[str, Any],
) -> dict[str, Any]:
    formula_count = len({candidate.formula for candidate in candidates})
    good_count = sum(
        1 for candidate in candidates if _is_good_candidate(candidate, good_force_max=args.good_force_max)
    )
    near_miss_count = sum(
        1
        for candidate in candidates
        if _is_near_miss_candidate(
            candidate,
            good_force_max=args.good_force_max,
            near_miss_force_max=args.near_miss_force_max,
        )
    )
    return {
        "workflow": "f3_isolated_mlip_force_rank_neighbor_dpo_preferences",
        "local_only": True,
        "runs_generation": False,
        "runs_training": False,
        "runs_dft": False,
        "runs_mlip": False,
        "calls_external_apis": False,
        "downloads": False,
        "consensus_jsonl": str(args.consensus_jsonl),
        "audit_candidate_input_paths": [str(path) for path in audit_paths],
        "candidate_id_prefix": args.candidate_id_prefix,
        "sample_label": args.sample_label,
        "require_f1_f2_pass": args.require_f1_f2_pass,
        "f3_pair_rule": F3_PAIR_RULE_ID,
        "good_force_max": args.good_force_max,
        "near_miss_force_max": args.near_miss_force_max,
        "rank_neighbor_count": args.rank_neighbor_count,
        "max_pairs_per_formula": args.max_pairs_per_formula,
        "consensus_input_count": len(consensus_rows),
        "matched_f3_candidate_count": len(candidates),
        "f3_good_candidate_count": good_count,
        "f3_near_miss_candidate_count": near_miss_count,
        "formula_count": formula_count,
        "pair_count": len(pairs),
        "preference_type_breakdown": dict(Counter(pair.preference_type for pair in pairs)),
        "preference_reason": [F3_PAIR_RULE_ID, "good_vs_near_miss_mlip_force", "f1_f2_controlled"],
        "candidate_skip_reasons": dict(sorted(candidate_skips.items())),
        "pair_skip_reasons": dict(sorted(pair_skips.items())),
        "formula_stats": dict(sorted(formula_stats.items())),
        "training_pair_validation": validation_summary,
        "created_time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
        },
        "caveat": "F3 pairs are same-formula MLIP relaxation force preferences, not DFT hull labels.",
    }


def _render_report(summary: dict[str, Any]) -> str:
    validation = summary["training_pair_validation"]
    return "\n".join(
        [
            "# F3-Isolated DPO Preference Build",
            "",
            "## Boundary",
            "- Reads local audit candidates and local three-MLIP consensus labels only.",
            "- Does not run generation, MLIP, DFT, training, downloads, or external APIs.",
            "- Emits only same-formula good-vs-near-miss MLIP force pairs with F1/F2 controlled.",
            "",
            "## Inputs",
            f"- consensus_jsonl: `{summary['consensus_jsonl']}`",
            f"- audit_candidate_input_count: {len(summary['audit_candidate_input_paths'])}",
            f"- sample_label: {summary['sample_label']}",
            "",
            "## Summary",
            f"- consensus_input_count: {summary['consensus_input_count']}",
            f"- matched_f3_candidate_count: {summary['matched_f3_candidate_count']}",
            f"- f3_good_candidate_count: {summary['f3_good_candidate_count']}",
            f"- f3_near_miss_candidate_count: {summary['f3_near_miss_candidate_count']}",
            f"- formula_count: {summary['formula_count']}",
            f"- pair_count: {summary['pair_count']}",
            f"- f3_pair_rule: {summary['f3_pair_rule']}",
            f"- good_force_max: {summary['good_force_max']}",
            f"- near_miss_force_max: {summary['near_miss_force_max']}",
            f"- rank_neighbor_count: {summary['rank_neighbor_count']}",
            f"- preference_type_breakdown: {summary['preference_type_breakdown']}",
            f"- candidate_skip_reasons: {summary['candidate_skip_reasons']}",
            f"- pair_skip_reasons: {summary['pair_skip_reasons']}",
            "",
            "## Training Schema Check",
            f"- valid_pair_count: {validation['valid_pair_count']}",
            f"- invalid_pair_count: {validation['invalid_pair_count']}",
            f"- invalid_reasons: {validation['invalid_reasons']}",
            "",
            "## Caveat",
            f"- {summary['caveat']}",
            "",
        ]
    )


def _strip_prefix(candidate_id: str, prefix: str) -> str:
    if prefix and candidate_id.startswith(prefix):
        return candidate_id[len(prefix) :]
    return candidate_id


def _sequence(row: dict[str, Any]) -> dict[str, Any]:
    fields = row.get("raw_sequence_fields")
    if not isinstance(fields, dict):
        fields = {}
    return {field: fields.get(field) for field in SEQUENCE_FIELDS}


def _has_full_sequence(row: dict[str, Any]) -> bool:
    sequence = _sequence(row)
    return all(sequence.get(field) not in (None, "", []) for field in SEQUENCE_FIELDS)


def _failure_vector(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("failure_vector")
    return dict(value) if isinstance(value, dict) else {}


def _f3_failure_vector(candidate: F3Candidate) -> dict[str, Any]:
    failure = _failure_vector(candidate.audit_row)
    failure["candidate_id"] = candidate.candidate_id
    failure["sample_id"] = candidate.candidate_id
    failure["f1_geometry"] = candidate.f1_geometry
    failure["f2_chemistry"] = candidate.f2_chemistry
    failure["f3_stability"] = None
    failure["calibration_tier"] = 2
    failure["confidence"] = 0.5
    metadata = dict(failure.get("metadata", {})) if isinstance(failure.get("metadata"), dict) else {}
    metadata["f3_status"] = "mlip_force_pair_evidence"
    metadata["stability"] = {
        "source": candidate.consensus_row.get("validation_source"),
        "validation_status": candidate.consensus_row.get("validation_status"),
        "pair_rule": F3_PAIR_RULE_ID,
        "vote_pattern": candidate.consensus_row.get("metadata", {}).get("vote_pattern"),
        "validator": candidate.consensus_row.get("validator"),
        "mean_force_max": candidate.mean_force_max,
        "model_forces": dict(candidate.model_forces),
        "model_converged": dict(candidate.model_converged),
        "model_stresses": dict(candidate.model_stresses),
        "model_energies": dict(candidate.model_energies),
        "unit": "eV/Angstrom",
    }
    failure["metadata"] = metadata
    return failure


def _f1_f2_key(candidate: F3Candidate) -> tuple[float, float]:
    return (candidate.f1_geometry, candidate.f2_chemistry)


def _force_rank(candidate: F3Candidate) -> tuple[float, str]:
    return (candidate.mean_force_max, candidate.candidate_id)


def _is_good_candidate(candidate: F3Candidate, *, good_force_max: float) -> bool:
    return all(candidate.model_forces[model] <= good_force_max for model in MLIP_MODELS) and all(
        candidate.model_converged.get(model) is True for model in MLIP_MODELS
    )


def _is_near_miss_candidate(
    candidate: F3Candidate,
    *,
    good_force_max: float,
    near_miss_force_max: float,
) -> bool:
    forces = [candidate.model_forces[model] for model in MLIP_MODELS]
    return all(force <= near_miss_force_max for force in forces) and any(force > good_force_max for force in forces)


def _compatible_candidates(candidate: F3Candidate, others: list[F3Candidate]) -> list[F3Candidate]:
    return [other for other in others if _f1_f2_key(candidate) == _f1_f2_key(other)]


def _rank_neighbors(
    good_index: int,
    good_count: int,
    near_miss: list[F3Candidate],
    *,
    rank_neighbor_count: int,
) -> list[F3Candidate]:
    target = _rank_position(good_index, good_count)
    ranked = sorted(
        enumerate(near_miss),
        key=lambda item: (
            abs(_rank_position(item[0], len(near_miss)) - target),
            item[1].mean_force_max,
            item[1].candidate_id,
        ),
    )
    return [candidate for _, candidate in ranked[:rank_neighbor_count]]


def _rank_position(index: int, count: int) -> float:
    if count <= 1:
        return 0.0
    return index / (count - 1)


def _mlip_evidence(candidate: F3Candidate) -> dict[str, Any]:
    return {
        "unit": "eV/Angstrom",
        "mean_force_max": candidate.mean_force_max,
        "model_forces": dict(candidate.model_forces),
        "model_converged": dict(candidate.model_converged),
        "model_stresses": dict(candidate.model_stresses),
        "model_energies": dict(candidate.model_energies),
    }


def _model_float_map(
    row: dict[str, Any],
    suffix: str,
    *,
    require_all: bool = True,
) -> dict[str, float | None]:
    metadata = row.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    values: dict[str, float | None] = {}
    for model in MLIP_MODELS:
        value = None
        for alias in MODEL_KEY_ALIASES[model]:
            value = _optional_float(metadata.get(f"{alias}_{suffix}"))
            if value is not None:
                break
        if value is None and require_all:
            return {}
        values[model] = value
    return values


def _model_bool_map(row: dict[str, Any], suffix: str) -> dict[str, bool | None]:
    metadata = row.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    values: dict[str, bool | None] = {}
    for model in MLIP_MODELS:
        value = None
        for alias in MODEL_KEY_ALIASES[model]:
            value = _optional_bool(metadata.get(f"{alias}_{suffix}"))
            if value is not None:
                break
        values[model] = value
    return values


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "null", "None", "none"):
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        return None
    return parsed


if __name__ == "__main__":
    main()
