"""Optional structure parsers for external generator artifacts.

The core package stays standard-library only. Optional parser backends are
imported lazily and failures are represented as fallback records so audit runs
can continue.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from fiir_crystal.structures.records import (
    CRYSTALFORMER_SEQUENCE_FIELDS,
    CrystalStructureRecord,
    Matrix3,
    composition_from_species,
    crystalformer_sequence_status,
)


def parse_cif_text_optional(
    cif_text: str,
    *,
    parser_backend: str = "auto",
    candidate_id: str | None = None,
    source_path: str | None = None,
) -> CrystalStructureRecord:
    """Parse CIF text when an optional backend is available.

    `parser_backend="none"` always returns an unparsed fallback record.
    `parser_backend="auto"` tries pymatgen and falls back when pymatgen is not
    installed. Parser exceptions are converted to `parse_status="parse_error"`.
    """

    backend = _normalize_backend(parser_backend)
    candidate = candidate_id or _candidate_id_from_cif(cif_text) or "cif_inline"
    if backend == "none":
        return _fallback_cif_record(
            candidate,
            cif_text,
            source_path=source_path,
            parser_backend=backend,
            parse_status="unparsed_cif",
        )

    try:
        from pymatgen.core import Structure  # type: ignore[import-not-found]
    except ImportError as exc:
        if backend == "auto":
            return _fallback_cif_record(
                candidate,
                cif_text,
                source_path=source_path,
                parser_backend=backend,
                parse_status="unparsed_cif",
                note="pymatgen_not_installed",
            )
        return _fallback_cif_record(
            candidate,
            cif_text,
            source_path=source_path,
            parser_backend=backend,
            parse_status="parse_error",
            error=exc,
        )

    try:
        structure = Structure.from_str(cif_text, fmt="cif")
        species = tuple(str(site.specie.symbol) for site in structure)
        frac_coords = tuple(
            (float(coord[0]), float(coord[1]), float(coord[2]))
            for coord in structure.frac_coords
        )
        lattice_matrix = tuple(
            (float(row[0]), float(row[1]), float(row[2]))
            for row in structure.lattice.matrix
        )
        metadata = _base_parser_metadata(
            parser_backend="pymatgen",
            parse_status="parsed_full_structure",
            source_path=source_path,
        )
        metadata["source_format"] = "cif"
        return CrystalStructureRecord(
            candidate_id=candidate,
            species=species,
            frac_coords=frac_coords,
            lattice_matrix=lattice_matrix,  # type: ignore[arg-type]
            pbc=(True, True, True),
            composition=str(structure.composition.reduced_formula),
            num_sites=len(species),
            space_group=None,
            wyckoff_letters=None,
            prototype=None,
            structure_ref=source_path,
            source="optional_parser",
            metadata=metadata,
        )
    except Exception as exc:  # pragma: no cover - exercised only with pymatgen installed
        return _fallback_cif_record(
            candidate,
            cif_text,
            source_path=source_path,
            parser_backend="pymatgen",
            parse_status="parse_error",
            error=exc,
        )


def parse_cif_file_optional(
    path: str | Path,
    *,
    parser_backend: str = "auto",
) -> CrystalStructureRecord:
    """Parse a CIF file with optional backends or return a fallback record."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        return _fallback_cif_record(
            source.stem or "missing_cif",
            "",
            source_path=str(source),
            parser_backend=_normalize_backend(parser_backend),
            parse_status="parse_error",
            error=exc,
        )
    record = parse_cif_text_optional(
        text,
        parser_backend=parser_backend,
        candidate_id=source.stem,
        source_path=str(source),
    )
    record.structure_ref = str(source)
    record.metadata.setdefault("filename", source.name)
    return record


def parse_struct_csv_row(
    row: dict[str, Any],
    *,
    candidate_id: str | None = None,
) -> CrystalStructureRecord:
    """Convert an `awl2struct`-style CSV row into a conservative record."""

    candidate = str(candidate_id or _first_value(row, "candidate_id", "sample_id", "id", "name") or "struct_row")
    species = _parse_species(_first_value(row, "species", "atom_types", "elements", "A"))
    frac_coords = _parse_coords(_first_value(row, "frac_coords", "fractional_coords", "coords", "X"))
    lattice = _parse_lattice(_first_value(row, "lattice_matrix", "lattice", "L"))
    composition = _first_value(row, "composition", "formula", "target_formula")
    structure_ref = _first_value(row, "structure_ref", "cif_path", "cif_file", "cif_filename", "structure_path", "path")
    cif_text = _first_value(row, "cif", "cif_string", "structure_cif")
    metadata = _metadata_from_struct_row(row)
    metadata["parse_status"] = "parsed_full_structure" if species and frac_coords and lattice else "unparsed_cif"
    metadata["source_format"] = "crystalformer_struct_csv"
    return CrystalStructureRecord(
        candidate_id=candidate,
        species=species,
        frac_coords=frac_coords,
        lattice_matrix=lattice,
        pbc=(True, True, True),
        composition=str(composition) if composition else composition_from_species(species),
        num_sites=len(species) or len(frac_coords),
        space_group=_optional_int(_first_value(row, "space_group", "spacegroup", "sg", "g")),
        wyckoff_letters=None,
        prototype=None,
        structure_ref=str(structure_ref or cif_text) if (structure_ref or cif_text) else None,
        source="deepmodeling/CrystalFormer",
        metadata=metadata,
    )


def _fallback_cif_record(
    candidate_id: str,
    cif_text: str,
    *,
    source_path: str | None,
    parser_backend: str,
    parse_status: str,
    note: str | None = None,
    error: BaseException | None = None,
) -> CrystalStructureRecord:
    metadata = _base_parser_metadata(
        parser_backend=parser_backend,
        parse_status=parse_status,
        source_path=source_path,
    )
    metadata["source_format"] = "cif"
    if note:
        metadata["parse_note"] = note
    if error is not None:
        metadata["parse_error_type"] = error.__class__.__name__
        metadata["parse_error_message"] = str(error)
    return CrystalStructureRecord(
        candidate_id=candidate_id,
        species=(),
        frac_coords=(),
        lattice_matrix=(),
        pbc=(True, True, True),
        composition=None,
        num_sites=0,
        space_group=None,
        wyckoff_letters=None,
        prototype=None,
        structure_ref=source_path if source_path is not None else cif_text,
        source="optional_parser",
        metadata=metadata,
    )


def _base_parser_metadata(
    *,
    parser_backend: str,
    parse_status: str,
    source_path: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "parser_backend": parser_backend,
        "parse_status": parse_status,
        "source_path": source_path,
        "stability_mode": "unavailable_without_offline_validation",
        "raw_sequence_fields": {field: None for field in CRYSTALFORMER_SEQUENCE_FIELDS},
    }
    status, missing = crystalformer_sequence_status(metadata)
    metadata["raw_sequence_status"] = status
    metadata["missing_sequence_fields"] = missing
    return metadata


def _metadata_from_struct_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "raw_crystalformer_row": dict(row),
        "raw_row": dict(row),
        "stability_mode": "unavailable_without_offline_validation",
        "source_model": "deepmodeling/CrystalFormer",
        "raw_sequence_fields": {
            field: _first_value(row, field)
            for field in CRYSTALFORMER_SEQUENCE_FIELDS
        },
    }
    for field, value in metadata["raw_sequence_fields"].items():
        metadata[f"raw_{field}"] = value
    status, missing = crystalformer_sequence_status(metadata)
    metadata["raw_sequence_status"] = status
    metadata["missing_sequence_fields"] = missing
    return metadata


def _normalize_backend(parser_backend: str) -> str:
    backend = parser_backend.lower().strip()
    if backend not in {"auto", "none", "pymatgen"}:
        raise ValueError(f"unsupported parser_backend: {parser_backend}")
    return backend


def _candidate_id_from_cif(cif_text: str) -> str | None:
    for line in cif_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("data_") and len(stripped) > 5:
            return _clean_identifier(stripped[5:])
    return None


def _clean_identifier(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip())
    return cleaned or "cif_inline"


def _first_value(row: dict[str, Any], *names: str) -> Any:
    lookup = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lookup.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None", "none"):
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
        return tuple(item.strip() for item in text.replace(" ", ",").split(",") if item.strip())
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


def _parse_lattice(value: Any) -> Matrix3 | tuple[()]:
    parsed = _literal(value)
    if parsed is None:
        return ()
    if isinstance(parsed, str):
        values = [float(item) for item in parsed.replace(";", " ").replace(",", " ").split() if item]
        if len(values) == 9:
            return (
                (values[0], values[1], values[2]),
                (values[3], values[4], values[5]),
                (values[6], values[7], values[8]),
            )
        if len(values) == 3:
            return ((values[0], 0.0, 0.0), (0.0, values[1], 0.0), (0.0, 0.0, values[2]))
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
    return ()


def _flatten(items: Any) -> list[Any]:
    flat: list[Any] = []
    for item in items:
        if isinstance(item, (list, tuple)):
            flat.extend(_flatten(item))
        else:
            flat.append(item)
    return flat
