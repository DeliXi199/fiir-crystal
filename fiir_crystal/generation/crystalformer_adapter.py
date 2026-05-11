"""Adapter for deepmodeling/CrystalFormer output directories.

The adapter is intentionally a boundary layer: it does not import or install
CrystalFormer, JAX, torch, pymatgen, ASE, or any other crystal toolkit.
"""

from __future__ import annotations

import ast
import csv
import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fiir_crystal.structures import CrystalStructureRecord
from fiir_crystal.structures.records import (
    Matrix3,
    composition_from_species,
    lattice_matrix_from_parameters,
)
from fiir_crystal.structures.serialization import read_jsonl as read_structure_jsonl


CRYSTALFORMER_SOURCE = "deepmodeling/CrystalFormer"


@dataclass(slots=True)
class CrystalFormerAdapter:
    """Load or invoke deepmodeling/CrystalFormer through a local output boundary."""

    config: dict[str, Any] = field(default_factory=dict)
    name: str = "crystalformer"
    last_subprocess: dict[str, Any] | None = None

    def generate(self, config: dict[str, Any] | None = None) -> list[CrystalStructureRecord]:
        """Optionally run an external command, then load generated outputs."""

        merged = _merge_dicts(self.config, _generation_config(config or {}))
        if bool(merged.get("run_generation", False)):
            self._run_generation_command(merged)
        output_dir = merged.get("output_dir") or merged.get("normalized_output")
        if not output_dir:
            raise ValueError("CrystalFormerAdapter requires output_dir or normalized_output.")
        self.config = merged
        return self.load_outputs(output_dir)

    def load_outputs(self, output_dir: str | Path) -> list[CrystalStructureRecord]:
        """Load CrystalFormer outputs from a file or directory."""

        path = Path(output_dir)
        if not path.exists():
            raise FileNotFoundError(f"CrystalFormer output path does not exist: {path}")
        source_format = str(self.config.get("source_format", "auto"))
        records = self._load_path(path, source_format)
        if not records:
            raise ValueError(f"No CrystalFormer candidates were found in {path}")
        return records

    def _run_generation_command(self, config: dict[str, Any]) -> None:
        command = config.get("crystalformer_command")
        if not command:
            raise ValueError("run_generation=true requires crystalformer_command.")
        args = command if isinstance(command, list) else shlex.split(str(command))
        work_dir = config.get("crystalformer_work_dir")
        cwd = Path(work_dir) if work_dir else None
        if cwd is not None and not cwd.exists():
            raise FileNotFoundError(f"CrystalFormer work dir does not exist: {cwd}")
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd is not None else None,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.last_subprocess = {
            "args": args,
            "cwd": str(cwd) if cwd is not None else None,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def _load_path(self, path: Path, source_format: str) -> list[CrystalStructureRecord]:
        if source_format in {"normalized_jsonl", "jsonl"}:
            target = _first_existing(path, ["candidates.jsonl", "normalized.jsonl"]) if path.is_dir() else path
            return read_structure_jsonl(target)
        if source_format in {"crystalformer_raw_csv", "raw_csv", "sampling_csv"}:
            target = _first_csv(path) if path.is_dir() else path
            return self._load_sampling_csv(target)
        if source_format in {"crystalformer_struct_csv", "struct_csv"}:
            target = _first_csv(path) if path.is_dir() else path
            return self._load_struct_csv(target)
        if source_format in {"cif_directory", "cif_dir"}:
            return self._load_cif_directory(path)
        if source_format == "manifest":
            manifest = path / "manifest.json" if path.is_dir() else path
            return self._load_manifest(manifest)
        if source_format != "auto":
            raise ValueError(f"Unsupported CrystalFormer source_format: {source_format}")
        return self._auto_load(path)

    def _auto_load(self, path: Path) -> list[CrystalStructureRecord]:
        if path.is_file():
            if path.name == "manifest.json":
                return self._load_manifest(path)
            if path.suffix.lower() == ".jsonl":
                return read_structure_jsonl(path)
            if path.suffix.lower() == ".csv":
                return self._load_struct_csv(path) if _csv_looks_struct_like(path) else self._load_sampling_csv(path)
            if path.suffix.lower() == ".cif":
                return [self._record_from_cif(path)]
            raise ValueError(f"Unsupported CrystalFormer output file: {path}")

        manifest = path / "manifest.json"
        if manifest.exists():
            records = self._load_manifest(manifest)
            if records:
                return records

        for name in ("candidates.jsonl", "normalized.jsonl", "structures.jsonl"):
            candidate = path / name
            if candidate.exists():
                return read_structure_jsonl(candidate)

        csv_files = sorted(path.glob("*.csv"))
        if csv_files:
            struct_files = [item for item in csv_files if _csv_looks_struct_like(item)]
            if struct_files:
                records: list[CrystalStructureRecord] = []
                for csv_path in struct_files:
                    records.extend(self._load_struct_csv(csv_path))
                return records
            records = []
            for csv_path in csv_files:
                records.extend(self._load_sampling_csv(csv_path))
            return records

        return self._load_cif_directory(path)

    def _load_manifest(self, manifest_path: Path) -> list[CrystalStructureRecord]:
        if not manifest_path.exists():
            raise FileNotFoundError(f"CrystalFormer manifest does not exist: {manifest_path}")
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            raise ValueError(f"CrystalFormer manifest must be a JSON object: {manifest_path}")

        records: list[CrystalStructureRecord] = []
        for key in ("records", "candidates"):
            items = manifest.get(key)
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError(f"manifest {key} entries must be objects")
                    record = CrystalStructureRecord.from_dict(item)
                    record.metadata.setdefault("manifest_path", str(manifest_path))
                    records.append(record)

        for key in ("normalized_output", "normalized_jsonl"):
            if manifest.get(key):
                records.extend(self._load_path(_resolve(manifest_path.parent, manifest[key]), "normalized_jsonl"))

        for key in ("cif_directory", "cif_dir"):
            if manifest.get(key):
                records.extend(self._load_path(_resolve(manifest_path.parent, manifest[key]), "cif_directory"))

        files = manifest.get("files", manifest.get("outputs", manifest.get("output_files", [])))
        if isinstance(files, list):
            for item in files:
                if isinstance(item, str):
                    records.extend(self._load_path(_resolve(manifest_path.parent, item), "auto"))
                elif isinstance(item, dict):
                    file_path = item.get("path") or item.get("file")
                    if not file_path:
                        continue
                    records.extend(
                        self._load_path(
                            _resolve(manifest_path.parent, file_path),
                            str(item.get("source_format", "auto")),
                        )
                    )
                else:
                    raise ValueError("manifest files entries must be strings or objects")

        if not records and "candidate_id" in manifest:
            records.append(CrystalStructureRecord.from_dict(manifest))
        return records

    def _load_sampling_csv(self, csv_path: Path) -> list[CrystalStructureRecord]:
        rows = _read_csv(csv_path)
        return [
            self._record_from_sampling_row(row, index, csv_path)
            for index, row in enumerate(rows, start=1)
        ]

    def _load_struct_csv(self, csv_path: Path) -> list[CrystalStructureRecord]:
        rows = _read_csv(csv_path)
        records: list[CrystalStructureRecord] = []
        for index, row in enumerate(rows, start=1):
            record = self._record_from_sampling_row(row, index, csv_path, require_structured_fields=False)
            structure_ref = _first_value(
                row,
                "structure_ref",
                "cif_path",
                "cif_file",
                "cif_filename",
                "structure_path",
                "path",
            )
            cif_string = _first_value(row, "cif", "cif_string", "structure_cif")
            if structure_ref:
                record.structure_ref = str(_resolve(csv_path.parent, structure_ref))
            elif cif_string:
                record.structure_ref = str(cif_string)
            record.metadata["source_format"] = "crystalformer_struct_csv"
            record.metadata["csv_path"] = str(csv_path)
            records.append(record)
        return records

    def _load_cif_directory(self, directory: Path) -> list[CrystalStructureRecord]:
        if directory.is_file():
            if directory.suffix.lower() != ".cif":
                raise ValueError(f"Expected CIF file or directory, got: {directory}")
            return [self._record_from_cif(directory)]
        cif_paths = sorted(path for path in directory.iterdir() if path.suffix.lower() == ".cif")
        return [self._record_from_cif(path) for path in cif_paths]

    def _record_from_cif(self, path: Path) -> CrystalStructureRecord:
        return CrystalStructureRecord(
            candidate_id=path.stem,
            species=(),
            frac_coords=(),
            lattice_matrix=(),
            pbc=(True, True, True),
            composition=None,
            num_sites=0,
            space_group=None,
            wyckoff_letters=None,
            prototype=None,
            structure_ref=str(path),
            source=CRYSTALFORMER_SOURCE,
            metadata={
                "filename": path.name,
                "suffix": path.suffix,
                "source_format": "cif_directory",
                "stability_mode": "unavailable_without_offline_validation",
            },
        )

    def _record_from_sampling_row(
        self,
        row: dict[str, str],
        index: int,
        csv_path: Path,
        require_structured_fields: bool = True,
    ) -> CrystalStructureRecord:
        candidate_id = _first_value(row, "candidate_id", "sample_id", "id", "name")
        species = _parse_species(_first_value(row, "species", "atom_types", "elements", "A"))
        frac_coords = _parse_coords(_first_value(row, "frac_coords", "fractional_coords", "coords", "X"))
        lattice = _parse_lattice(row)
        composition = _first_value(row, "composition", "formula", "target_formula")
        wyckoff = _parse_tokens(_first_value(row, "wyckoff_letters", "wyckoff", "W"))
        num_sites = _optional_int(_first_value(row, "num_sites", "num_atoms", "natoms"))
        record = CrystalStructureRecord(
            candidate_id=str(candidate_id or f"crystalformer_{csv_path.stem}_{index:06d}"),
            species=species,
            frac_coords=frac_coords,
            lattice_matrix=lattice,
            pbc=(True, True, True),
            composition=str(composition) if composition else composition_from_species(species),
            num_sites=num_sites if num_sites is not None else len(species) or len(frac_coords),
            space_group=_optional_int(_first_value(row, "space_group", "spacegroup", "sg", "g")),
            wyckoff_letters=wyckoff or None,
            prototype=_none_if_empty(_first_value(row, "prototype")),
            structure_ref=_none_if_empty(_first_value(row, "structure_ref")),
            source=CRYSTALFORMER_SOURCE,
            metadata={
                "raw_row": dict(row),
                "csv_path": str(csv_path),
                "source_format": "crystalformer_raw_csv",
                "stability_mode": "unavailable_without_offline_validation",
            },
        )
        _copy_sampling_metadata(row, record.metadata)
        errors = record.validate_basic()
        if require_structured_fields:
            if not species:
                errors.append("missing_species")
            if not frac_coords:
                errors.append("missing_frac_coords")
            if not lattice:
                errors.append("missing_lattice_matrix")
        if errors:
            record.metadata["parse_warnings"] = sorted(set(errors))
            record.metadata["partial_record"] = True
        return record


def _generation_config(config: dict[str, Any]) -> dict[str, Any]:
    generation = config.get("generation") if isinstance(config.get("generation"), dict) else None
    return dict(generation or config)


def _merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    merged.update(right)
    return merged


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CrystalFormer CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _csv_looks_struct_like(path: Path) -> bool:
    if "struct" in path.stem.lower():
        return True
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return False
    names = {item.strip().lower() for item in header}
    return bool(names & {"cif", "cif_string", "structure_cif", "cif_path", "cif_file", "structure_path"})


def _first_existing(directory: Path, names: list[str]) -> Path:
    for name in names:
        candidate = directory / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"None of {names} exist in {directory}")


def _first_csv(directory: Path) -> Path:
    files = sorted(directory.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {directory}")
    return files[0]


def _resolve(base: Path, raw_path: Any) -> Path:
    path = Path(str(raw_path))
    return path if path.is_absolute() else base / path


def _first_value(row: dict[str, str], *names: str) -> str | None:
    lookup = {key.lower(): value for key, value in row.items()}
    for name in names:
        value = lookup.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _none_if_empty(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(str(value)))


def _literal(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
    return text


def _parse_species(value: Any) -> tuple[str, ...]:
    parsed = _literal(value)
    if parsed is None:
        return ()
    if isinstance(parsed, str):
        text = parsed.replace(";", ",").replace("|", ",")
        tokens = [item.strip() for item in text.replace(" ", ",").split(",") if item.strip()]
        return tuple(tokens)
    if isinstance(parsed, (list, tuple)):
        return tuple(str(item) for item in _flatten(parsed))
    return (str(parsed),)


def _parse_tokens(value: Any) -> tuple[str, ...]:
    parsed = _literal(value)
    if parsed is None:
        return ()
    if isinstance(parsed, str):
        if "," in parsed or ";" in parsed or "|" in parsed:
            return tuple(item.strip() for item in parsed.replace(";", ",").replace("|", ",").split(",") if item.strip())
        return tuple(parsed.strip()) if parsed.strip() else ()
    if isinstance(parsed, (list, tuple)):
        return tuple(str(item) for item in _flatten(parsed))
    return (str(parsed),)


def _parse_coords(value: Any) -> tuple[tuple[float, float, float], ...]:
    parsed = _literal(value)
    if parsed is None:
        return ()
    if isinstance(parsed, str):
        rows = [row.strip() for row in parsed.split(";") if row.strip()]
        coords = []
        for row in rows:
            parts = [part for part in row.replace(",", " ").split() if part]
            if len(parts) == 3:
                coords.append((float(parts[0]), float(parts[1]), float(parts[2])))
        return tuple(coords)
    if isinstance(parsed, (list, tuple)):
        if parsed and all(not isinstance(item, (list, tuple)) for item in parsed):
            flat = [float(item) for item in parsed]
            return tuple(
                (flat[index], flat[index + 1], flat[index + 2])
                for index in range(0, len(flat) - 2, 3)
            )
        return tuple((float(row[0]), float(row[1]), float(row[2])) for row in parsed if len(row) == 3)
    return ()


def _parse_lattice(row: dict[str, str]) -> Matrix3 | tuple[()]:
    value = _first_value(row, "lattice_matrix", "lattice", "L")
    parsed = _literal(value)
    matrix = _matrix_from_literal(parsed)
    if matrix:
        return matrix

    lengths = _parse_float_sequence(_first_value(row, "lattice_lengths", "lengths"))
    if len(lengths) == 3:
        return (
            (lengths[0], 0.0, 0.0),
            (0.0, lengths[1], 0.0),
            (0.0, 0.0, lengths[2]),
        )

    params = [
        _first_value(row, "a"),
        _first_value(row, "b"),
        _first_value(row, "c"),
        _first_value(row, "alpha"),
        _first_value(row, "beta"),
        _first_value(row, "gamma"),
    ]
    if all(value not in (None, "") for value in params):
        return lattice_matrix_from_parameters(*(float(value) for value in params if value is not None))
    if isinstance(parsed, (list, tuple)) and len(parsed) == 6:
        values = [float(item) for item in parsed]
        return lattice_matrix_from_parameters(*values)
    return ()


def _matrix_from_literal(parsed: Any) -> Matrix3 | tuple[()]:
    if parsed is None:
        return ()
    if isinstance(parsed, str):
        values = _parse_float_sequence(parsed)
        if len(values) == 9:
            return (
                (values[0], values[1], values[2]),
                (values[3], values[4], values[5]),
                (values[6], values[7], values[8]),
            )
        if len(values) == 3:
            return (
                (values[0], 0.0, 0.0),
                (0.0, values[1], 0.0),
                (0.0, 0.0, values[2]),
            )
        return ()
    if isinstance(parsed, (list, tuple)):
        if len(parsed) == 3 and all(isinstance(row, (list, tuple)) and len(row) == 3 for row in parsed):
            return (
                (float(parsed[0][0]), float(parsed[0][1]), float(parsed[0][2])),
                (float(parsed[1][0]), float(parsed[1][1]), float(parsed[1][2])),
                (float(parsed[2][0]), float(parsed[2][1]), float(parsed[2][2])),
            )
        if len(parsed) == 9:
            values = [float(item) for item in parsed]
            return (
                (values[0], values[1], values[2]),
                (values[3], values[4], values[5]),
                (values[6], values[7], values[8]),
            )
        if len(parsed) == 3:
            values = [float(item) for item in parsed]
            return (
                (values[0], 0.0, 0.0),
                (0.0, values[1], 0.0),
                (0.0, 0.0, values[2]),
            )
    return ()


def _parse_float_sequence(value: Any) -> list[float]:
    parsed = _literal(value)
    if parsed is None:
        return []
    if isinstance(parsed, str):
        text = parsed.replace(";", " ").replace(",", " ")
        return [float(item) for item in text.split() if item]
    if isinstance(parsed, (list, tuple)):
        return [float(item) for item in _flatten(parsed)]
    return [float(parsed)]


def _flatten(items: Any) -> list[Any]:
    flat: list[Any] = []
    for item in items:
        if isinstance(item, (list, tuple)):
            flat.extend(_flatten(item))
        else:
            flat.append(item)
    return flat


def _copy_sampling_metadata(row: dict[str, str], metadata: dict[str, Any]) -> None:
    score_like = {
        "score",
        "logprob",
        "log_probability",
        "temperature",
        "sample_temperature",
        "sampling_temperature",
        "rank",
    }
    lookup = {key.lower(): value for key, value in row.items()}
    for key in score_like:
        if key in lookup and lookup[key] not in (None, ""):
            metadata[key] = lookup[key]
