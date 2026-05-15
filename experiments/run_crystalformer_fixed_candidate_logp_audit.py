#!/usr/bin/env python
"""Score a fixed FIIR candidate panel with one or more CrystalFormer checkpoints.

This is an external experiment helper. It imports CrystalFormer/JAX only when
executed and is meant to run on an allocated GPU node, not as core
``fiir_crystal`` runtime code.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MODEL_ARGS = {
    "Nf": 5,
    "Kx": 16,
    "Kl": 4,
    "h0_size": 256,
    "transformer_layers": 16,
    "num_heads": 8,
    "key_size": 32,
    "model_size": 256,
    "embed_size": 256,
    "dropout_rate": 0.1,
    "attn_dropout": 0.1,
    "n_max": 21,
    "atom_types": 119,
    "wyck_types": 28,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a fixed FIIR raw-sequence candidate JSONL with CrystalFormer checkpoints."
    )
    parser.add_argument("--candidate-jsonl", required=True)
    parser.add_argument(
        "--checkpoint",
        action="append",
        required=True,
        help="Checkpoint as LABEL=path/to/checkpoint_dir_or_file. Repeat for multiple checkpoints.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--crystalformer-work-dir", default="external/CrystalFormer")
    parser.add_argument("--batchsize", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    for name, default in DEFAULT_MODEL_ARGS.items():
        arg_type = float if isinstance(default, float) else int
        parser.add_argument(f"--{name}", type=arg_type, default=default)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path.cwd()
    crystalformer_work_dir = _resolve(project_root, args.crystalformer_work_dir)
    if not crystalformer_work_dir.exists():
        raise SystemExit(f"CrystalFormer work dir does not exist: {crystalformer_work_dir}")
    sys.path.insert(0, str(crystalformer_work_dir))

    import jax
    import jax.numpy as jnp

    from crystalformer.src.formula import find_composition_vector
    from crystalformer.src.loss import make_loss_fn
    from crystalformer.src.transformer import make_transformer
    from crystalformer.src.utils import GLXYZAW_from_file
    from crystalformer.src.wyckoff import mult_table
    import crystalformer.src.checkpoint as checkpoint_lib

    candidate_jsonl = _resolve(project_root, args.candidate_jsonl)
    output_dir = _resolve(project_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_rows = _read_jsonl(candidate_jsonl)
    checkpoint_specs = _parse_checkpoints(args.checkpoint, project_root)
    model_args = {name: getattr(args, name) for name in DEFAULT_MODEL_ARGS}

    print(f"candidate_jsonl: {candidate_jsonl}")
    print(f"candidate_count: {len(candidate_rows)}")
    print(f"checkpoint_count: {len(checkpoint_specs)}")
    print(f"jax_default_backend: {jax.default_backend()}")
    print(f"jax_devices: {jax.devices()}")

    data = GLXYZAW_from_file(str(candidate_jsonl), model_args["atom_types"], model_args["wyck_types"], model_args["n_max"], 1)
    data = _with_composition(jax, find_composition_vector, mult_table, data)

    key = jax.random.PRNGKey(args.seed)
    params, transformer = make_transformer(
        key,
        model_args["Nf"],
        model_args["Kx"],
        model_args["Kl"],
        model_args["n_max"],
        model_args["h0_size"],
        model_args["transformer_layers"],
        model_args["num_heads"],
        model_args["key_size"],
        model_args["model_size"],
        model_args["embed_size"],
        model_args["atom_types"],
        model_args["wyck_types"],
        model_args["dropout_rate"],
        model_args["attn_dropout"],
    )
    _, logp_fn = make_loss_fn(
        model_args["n_max"],
        model_args["atom_types"],
        model_args["wyck_types"],
        model_args["Kx"],
        model_args["Kl"],
        transformer,
    )
    logp_fn = jax.jit(logp_fn, static_argnums=8)
    parallel_logp_fn = _parallel_logp_fn(jax, logp_fn)

    output_rows: list[dict[str, Any]] = []
    for checkpoint_label, checkpoint_path in checkpoint_specs:
        ckpt_filename, epoch_finished = checkpoint_lib.find_ckpt_filename(str(checkpoint_path))
        if ckpt_filename is None:
            raise SystemExit(f"No checkpoint found for {checkpoint_label}: {checkpoint_path}")
        print(f"Scoring checkpoint {checkpoint_label}: {ckpt_filename} (epoch {epoch_finished})")
        ckpt = checkpoint_lib.load_data(ckpt_filename)
        params = ckpt["params"]
        output_rows.extend(
            _score_checkpoint(
                jax=jax,
                data=data,
                candidate_rows=candidate_rows,
                params=params,
                parallel_logp_fn=parallel_logp_fn,
                checkpoint_label=checkpoint_label,
                checkpoint_path=str(checkpoint_path),
                checkpoint_file=str(ckpt_filename),
                checkpoint_epoch=epoch_finished,
                batchsize=args.batchsize,
                seed=args.seed,
            )
        )

    rows_path = output_dir / "logp_rows.jsonl"
    _write_jsonl(rows_path, output_rows)
    summary = _summarize(
        output_rows,
        candidate_count=len(candidate_rows),
        candidate_jsonl=str(candidate_jsonl),
        checkpoint_specs=checkpoint_specs,
        model_args=model_args,
        batchsize=args.batchsize,
    )
    _write_json(output_dir / "summary.json", summary)
    (output_dir / "report.md").write_text(_report(summary), encoding="utf-8")
    print(f"fixed candidate logp audit complete: {output_dir}")
    print(f"  rows: {len(output_rows)}")
    if "after_minus_before_by_consensus_label" in summary:
        print(f"  delta_by_label: {summary['after_minus_before_by_consensus_label']}")


def _score_checkpoint(
    *,
    jax: Any,
    data: tuple[Any, ...],
    candidate_rows: list[dict[str, Any]],
    params: Any,
    parallel_logp_fn: Any,
    checkpoint_label: str,
    checkpoint_path: str,
    checkpoint_file: str,
    checkpoint_epoch: int | None,
    batchsize: int,
    seed: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    sample_count = len(candidate_rows)
    num_devices = max(1, int(jax.local_device_count()))
    if batchsize < num_devices:
        batchsize = num_devices
    if batchsize % num_devices != 0:
        batchsize = int(math.ceil(batchsize / num_devices) * num_devices)
    per_device = batchsize // num_devices
    num_batches = math.ceil(sample_count / batchsize)
    key = jax.random.PRNGKey(seed)
    for batch_idx in range(num_batches):
        start = batch_idx * batchsize
        end = min(start + batchsize, sample_count)
        real_count = end - start
        pad_count = batchsize - real_count
        batch = jax.tree_util.tree_map(lambda x: x[start:end], data)
        if pad_count:
            batch = jax.tree_util.tree_map(lambda x: _pad_array(jax, x, pad_count), batch)
        batch = jax.tree_util.tree_map(lambda x: x.reshape((num_devices, per_device) + x.shape[1:]), batch)
        key, subkey = jax.random.split(key)
        subkeys = jax.random.split(subkey, num_devices)
        logp_g, logp_w, logp_xyz, logp_a, logp_l = parallel_logp_fn(params, subkeys, *batch)
        logp_g = logp_g.reshape((batchsize,))[:real_count]
        logp_w = logp_w.reshape((batchsize,))[:real_count]
        logp_xyz = logp_xyz.reshape((batchsize,))[:real_count]
        logp_a = logp_a.reshape((batchsize,))[:real_count]
        logp_l = logp_l.reshape((batchsize,))[:real_count]
        totals = (logp_g + logp_w + logp_xyz + logp_a + logp_l)[:real_count]
        for offset, row in enumerate(candidate_rows[start:end]):
            idx = start + offset
            output.append(
                {
                    "row_index": idx,
                    "candidate_id": row.get("candidate_id"),
                    "formula": row.get("formula") or row.get("composition"),
                    "source_side": row.get("source_side"),
                    "consensus_label": row.get("consensus_label"),
                    "panel_reason": row.get("panel_reason"),
                    "checkpoint_label": checkpoint_label,
                    "checkpoint_path": checkpoint_path,
                    "checkpoint_file": checkpoint_file,
                    "checkpoint_epoch": checkpoint_epoch,
                    "logp_total": float(totals[offset]),
                    "logp_g": float(logp_g[offset]),
                    "logp_w": float(logp_w[offset]),
                    "logp_xyz": float(logp_xyz[offset]),
                    "logp_a": float(logp_a[offset]),
                    "logp_l": float(logp_l[offset]),
                }
            )
    return output


def _parallel_logp_fn(jax: Any, logp_fn: Any) -> Any:
    def score(params: Any, key: Any, composition: Any, G: Any, L: Any, XYZ: Any, A: Any, W: Any) -> tuple[Any, ...]:
        return logp_fn(params, key, composition, G, L, XYZ, A, W, False)

    return jax.pmap(score, in_axes=(None, 0, 0, 0, 0, 0, 0, 0))


def _pad_array(jax: Any, value: Any, pad_count: int) -> Any:
    if pad_count <= 0:
        return value
    pad = jax.numpy.repeat(value[-1:], pad_count, axis=0)
    return jax.numpy.concatenate([value, pad], axis=0)


def _summarize(
    rows: list[dict[str, Any]],
    *,
    candidate_count: int,
    candidate_jsonl: str,
    checkpoint_specs: list[tuple[str, Path]],
    model_args: dict[str, Any],
    batchsize: int,
) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    by_candidate: dict[str, dict[str, float]] = defaultdict(dict)
    candidate_meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("checkpoint_label")),
            str(row.get("consensus_label")),
            str(row.get("source_side")),
            str(row.get("panel_reason")),
        )
        groups[key].append(float(row["logp_total"]))
        cid = str(row.get("candidate_id"))
        by_candidate[cid][str(row.get("checkpoint_label"))] = float(row["logp_total"])
        candidate_meta[cid] = {
            "formula": row.get("formula"),
            "source_side": row.get("source_side"),
            "consensus_label": row.get("consensus_label"),
            "panel_reason": row.get("panel_reason"),
        }

    grouped = [
        {
            "checkpoint_label": checkpoint_label,
            "consensus_label": consensus_label,
            "source_side": source_side,
            "panel_reason": panel_reason,
            "count": len(values),
            "mean_logp_total": statistics.fmean(values),
            "median_logp_total": statistics.median(values),
        }
        for (checkpoint_label, consensus_label, source_side, panel_reason), values in sorted(groups.items())
    ]

    labels = [label for label, _ in checkpoint_specs]
    deltas: list[dict[str, Any]] = []
    if "before" in labels and "after" in labels:
        for candidate_id, scores in by_candidate.items():
            if "before" not in scores or "after" not in scores:
                continue
            meta = candidate_meta[candidate_id]
            deltas.append(
                {
                    "candidate_id": candidate_id,
                    **meta,
                    "after_minus_before_logp": scores["after"] - scores["before"],
                    "before_logp_total": scores["before"],
                    "after_logp_total": scores["after"],
                }
            )

    delta_by_label = _mean_delta(deltas, "consensus_label")
    delta_by_reason = _mean_delta(deltas, "panel_reason")
    stable_gap = None
    if "stable" in delta_by_label and "unstable" in delta_by_label:
        stable_gap = delta_by_label["stable"]["mean_after_minus_before_logp"] - delta_by_label["unstable"]["mean_after_minus_before_logp"]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflow": "crystalformer_fixed_candidate_logp_audit",
        "candidate_jsonl": candidate_jsonl,
        "candidate_count": candidate_count,
        "checkpoint_specs": [{"label": label, "path": str(path)} for label, path in checkpoint_specs],
        "model_args": model_args,
        "batchsize": batchsize,
        "score_group_summary": grouped,
        "after_minus_before_by_consensus_label": delta_by_label,
        "after_minus_before_by_panel_reason": delta_by_reason,
        "stable_minus_unstable_delta_gap": stable_gap,
        "local_only": True,
        "runs_generation": False,
        "runs_mlip": False,
        "runs_dft": False,
        "runs_training": False,
        "downloads": False,
        "calls_external_apis": False,
        "caveat": (
            "This scores fixed generated candidates under CrystalFormer checkpoints. "
            "It is a model-likelihood audit, not generation, MLIP validation, DFT, "
            "or hull-confirmed stability."
        ),
    }
    return summary


def _mean_delta(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key))].append(float(row["after_minus_before_logp"]))
    return {
        label: {
            "count": len(values),
            "mean_after_minus_before_logp": statistics.fmean(values),
            "median_after_minus_before_logp": statistics.median(values),
        }
        for label, values in sorted(grouped.items())
    }


def _report(summary: dict[str, Any]) -> str:
    lines = [
        "# CrystalFormer Fixed-Candidate LogP Audit",
        "",
        "## Scope",
        f"- candidate_count: {summary['candidate_count']}",
        f"- candidate_jsonl: `{summary['candidate_jsonl']}`",
        f"- caveat: {summary['caveat']}",
        "",
        "## Checkpoints",
    ]
    for spec in summary["checkpoint_specs"]:
        lines.append(f"- {spec['label']}: `{spec['path']}`")
    lines.extend(["", "## After Minus Before By Consensus Label", "", "| label | count | mean delta | median delta |", "| --- | ---: | ---: | ---: |"])
    for label, stats in summary.get("after_minus_before_by_consensus_label", {}).items():
        lines.append(
            f"| {label} | {stats['count']} | {stats['mean_after_minus_before_logp']:.6g} | {stats['median_after_minus_before_logp']:.6g} |"
        )
    lines.extend(["", "## After Minus Before By Panel Reason", "", "| reason | count | mean delta | median delta |", "| --- | ---: | ---: | ---: |"])
    for label, stats in summary.get("after_minus_before_by_panel_reason", {}).items():
        lines.append(
            f"| {label} | {stats['count']} | {stats['mean_after_minus_before_logp']:.6g} | {stats['median_after_minus_before_logp']:.6g} |"
        )
    lines.extend(
        [
            "",
            f"- stable_minus_unstable_delta_gap: {summary.get('stable_minus_unstable_delta_gap')}",
            "",
            "Interpretation: a positive stable-minus-unstable delta gap means the follow-up checkpoint gives a larger log-probability increase to stable consensus candidates than to unstable consensus candidates on the same fixed candidate panel.",
        ]
    )
    return "\n".join(lines) + "\n"


def _with_composition(jax: Any, find_composition_vector: Any, mult_table: Any, data: tuple[Any, ...]) -> tuple[Any, ...]:
    if len(data) == 6:
        return data
    G, L, XYZ, A, W = data
    M = jax.vmap(lambda g, w: mult_table[g - 1, w], in_axes=(0, 0))(G, W)
    composition = jax.vmap(find_composition_vector, (0, 0), 0)(A, M)
    return composition, G, L, XYZ, A, W


def _parse_checkpoints(items: list[str], project_root: Path) -> list[tuple[str, Path]]:
    out = []
    seen = set()
    for item in items:
        if "=" not in item:
            raise SystemExit(f"checkpoint must be LABEL=path: {item}")
        label, path = item.split("=", 1)
        if not label:
            raise SystemExit(f"empty checkpoint label: {item}")
        if label in seen:
            raise SystemExit(f"duplicate checkpoint label: {label}")
        seen.add(label)
        out.append((label, _resolve(project_root, path)))
    return out


def _resolve(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
