"""Standard structure records for generated crystal candidates.

This module deliberately avoids crystal-toolkit imports. It stores enough
structured information for FIIR Crystal to run lightweight failure attribution
while keeping CIFs or other rich external representations behind references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import acos, cos, degrees, sin, sqrt
from typing import Any


Vector3 = tuple[float, float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]
CRYSTALFORMER_SEQUENCE_FIELDS = ("g", "W", "A", "X", "L")


@dataclass(slots=True)
class CrystalStructureRecord:
    """Canonical stdlib record for external generator outputs."""

    candidate_id: str
    species: tuple[str, ...]
    frac_coords: tuple[Vector3, ...]
    lattice_matrix: Matrix3 | tuple[()]
    pbc: tuple[bool, bool, bool]
    composition: str | None
    num_sites: int
    space_group: int | None
    wyckoff_letters: tuple[str, ...] | None
    prototype: str | None
    structure_ref: str | None
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""

        return {
            "candidate_id": self.candidate_id,
            "species": list(self.species),
            "frac_coords": [list(coord) for coord in self.frac_coords],
            "lattice_matrix": [list(row) for row in self.lattice_matrix],
            "pbc": list(self.pbc),
            "composition": self.composition,
            "num_sites": self.num_sites,
            "space_group": self.space_group,
            "wyckoff_letters": (
                None if self.wyckoff_letters is None else list(self.wyckoff_letters)
            ),
            "prototype": self.prototype,
            "structure_ref": self.structure_ref,
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrystalStructureRecord":
        """Deserialize from a JSON-compatible dictionary."""

        candidate_id = data.get("candidate_id", data.get("sample_id"))
        if not candidate_id:
            raise ValueError("CrystalStructureRecord requires candidate_id.")
        species = tuple(str(item) for item in data.get("species", ()))
        frac_coords = tuple(_tuple3(coord, "frac_coords") for coord in data.get("frac_coords", ()))
        lattice_matrix = _matrix3_or_empty(data.get("lattice_matrix", ()))
        pbc = _pbc(data.get("pbc", (True, True, True)))
        composition = data.get("composition")
        num_sites = int(data.get("num_sites", len(species) or len(frac_coords)))
        wyckoff = data.get("wyckoff_letters")
        return cls(
            candidate_id=str(candidate_id),
            species=species,
            frac_coords=frac_coords,
            lattice_matrix=lattice_matrix,
            pbc=pbc,
            composition=None if composition is None else str(composition),
            num_sites=num_sites,
            space_group=_optional_int(data.get("space_group", data.get("spacegroup"))),
            wyckoff_letters=None if wyckoff is None else tuple(str(item) for item in wyckoff),
            prototype=None if data.get("prototype") is None else str(data["prototype"]),
            structure_ref=None if data.get("structure_ref") is None else str(data["structure_ref"]),
            source=str(data.get("source", "unknown")),
            metadata=dict(data.get("metadata", {})),
        )

    def to_structure_like(self) -> Any:
        """Convert to FIIR's existing lightweight `StructureLike` object."""

        from fiir_crystal.failure import StructureLike

        lengths = lattice_lengths(self.lattice_matrix)
        angles = lattice_angles(self.lattice_matrix)
        metadata = {
            "source": self.source,
            "external_record_type": self.__class__.__name__,
            "structure_ref": self.structure_ref,
            "pbc": list(self.pbc),
            "species": list(self.species),
            "wyckoff_letters": (
                None if self.wyckoff_letters is None else list(self.wyckoff_letters)
            ),
            "stability_mode": self.metadata.get(
                "stability_mode",
                "unavailable_without_offline_validation",
            ),
            "stability_unavailable_reason": self.metadata.get(
                "stability_unavailable_reason",
                "no offline validation, MLIP relaxation, or DFT result was provided",
            ),
            **self.metadata,
        }
        num_atoms = self.num_sites or len(self.species) or len(self.frac_coords)
        return StructureLike(
            candidate_id=self.candidate_id,
            composition=self.composition or composition_from_species(self.species),
            num_atoms=num_atoms,
            space_group=self.space_group,
            prototype=self.prototype,
            mock_geometry_score=float(metadata.get("mock_geometry_score", 0.0)),
            mock_chemistry_score=float(metadata.get("mock_chemistry_score", 0.0)),
            mock_stability_score=(
                None
                if metadata.get("mock_stability_score") is None
                else float(metadata["mock_stability_score"])
            ),
            lattice_lengths=lengths,
            lattice_angles=angles,
            frac_coords=self.frac_coords or None,
            metadata=metadata,
        )

    def validate_basic(self) -> list[str]:
        """Return basic schema and shape problems without crystal-toolkit checks."""

        errors: list[str] = []
        if not self.candidate_id:
            errors.append("missing_candidate_id")
        if len(self.pbc) != 3:
            errors.append("pbc_must_have_three_flags")
        if self.num_sites < 0:
            errors.append("num_sites_must_be_nonnegative")
        if self.species and self.num_sites and len(self.species) != self.num_sites:
            errors.append("species_count_mismatch")
        if self.frac_coords and self.num_sites and len(self.frac_coords) != self.num_sites:
            errors.append("coord_count_mismatch")
        if self.species and self.frac_coords and len(self.species) != len(self.frac_coords):
            errors.append("species_coord_count_mismatch")
        if self.lattice_matrix and len(self.lattice_matrix) != 3:
            errors.append("lattice_matrix_must_have_three_rows")
        for row in self.lattice_matrix:
            if len(row) != 3:
                errors.append("lattice_matrix_rows_must_have_three_values")
                break
        for coord in self.frac_coords:
            if len(coord) != 3:
                errors.append("frac_coords_rows_must_have_three_values")
                break
        if self.space_group is not None and not 1 <= self.space_group <= 230:
            errors.append("space_group_out_of_range")
        return errors

    def crystalformer_sequence_status(self) -> tuple[str, list[str]]:
        """Return raw CrystalFormer sequence completeness from metadata."""

        return crystalformer_sequence_status(self.metadata)


def crystalformer_sequence_status(metadata: dict[str, Any]) -> tuple[str, list[str]]:
    """Classify preserved CrystalFormer `g` / `W` / `A` / `X` / `L` fields."""

    if metadata.get("raw_sequence_status") and isinstance(metadata.get("missing_sequence_fields"), list):
        return str(metadata["raw_sequence_status"]), [str(item) for item in metadata["missing_sequence_fields"]]

    fields = metadata.get("raw_sequence_fields")
    if not isinstance(fields, dict):
        fields = {
            field: metadata.get(f"raw_{field}")
            for field in CRYSTALFORMER_SEQUENCE_FIELDS
            if metadata.get(f"raw_{field}") is not None
        }
    missing = [
        field
        for field in CRYSTALFORMER_SEQUENCE_FIELDS
        if _missing_sequence_value(fields.get(field)) and _missing_sequence_value(metadata.get(f"raw_{field}"))
    ]
    if len(missing) == len(CRYSTALFORMER_SEQUENCE_FIELDS):
        return "missing", missing
    if missing:
        return "partial", missing
    return "full", []


def has_crystalformer_raw_sequence(metadata: dict[str, Any]) -> bool:
    """Return whether metadata contains a DPO-usable raw CrystalFormer sequence."""

    if metadata.get("raw_crystalformer_row") is not None:
        return True
    fields = metadata.get("raw_sequence_fields")
    if isinstance(fields, dict) and any(
        not _missing_sequence_value(fields.get(field)) for field in CRYSTALFORMER_SEQUENCE_FIELDS
    ):
        return True
    return any(
        not _missing_sequence_value(metadata.get(f"raw_{field}"))
        for field in CRYSTALFORMER_SEQUENCE_FIELDS
    )


def _missing_sequence_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def lattice_lengths(matrix: Matrix3 | tuple[()]) -> tuple[float, float, float] | None:
    """Return row-vector lattice lengths from a matrix."""

    if len(matrix) != 3:
        return None
    return tuple(_norm(row) for row in matrix)  # type: ignore[return-value]


def lattice_angles(matrix: Matrix3 | tuple[()]) -> tuple[float, float, float] | None:
    """Return alpha, beta, gamma angles in degrees from row-vector lattice."""

    if len(matrix) != 3:
        return None
    a_vec, b_vec, c_vec = matrix
    return (
        _angle(b_vec, c_vec),
        _angle(a_vec, c_vec),
        _angle(a_vec, b_vec),
    )


def lattice_matrix_from_parameters(
    a: float,
    b: float,
    c: float,
    alpha: float,
    beta: float,
    gamma: float,
) -> Matrix3:
    """Build a conventional row-vector lattice matrix from lengths and angles."""

    alpha_r = alpha * 3.141592653589793 / 180.0
    beta_r = beta * 3.141592653589793 / 180.0
    gamma_r = gamma * 3.141592653589793 / 180.0
    ax = a
    bx = b * cos(gamma_r)
    by = b * sin(gamma_r)
    cx = c * cos(beta_r)
    cy = c * (cos(alpha_r) - cos(beta_r) * cos(gamma_r)) / sin(gamma_r)
    cz_sq = max(0.0, c * c - cx * cx - cy * cy)
    return (
        (ax, 0.0, 0.0),
        (bx, by, 0.0),
        (cx, cy, sqrt(cz_sq)),
    )


def composition_from_species(species: tuple[str, ...]) -> str:
    """Create a simple formula string from ordered species tokens."""

    if not species:
        return ""
    counts: dict[str, int] = {}
    order: list[str] = []
    for item in species:
        if item not in counts:
            order.append(item)
            counts[item] = 0
        counts[item] += 1
    parts = []
    for element in order:
        count = counts[element]
        parts.append(element if count == 1 else f"{element}{count}")
    return "".join(parts)


def _tuple3(value: Any, field_name: str) -> Vector3:
    if len(value) != 3:
        raise ValueError(f"{field_name} rows must contain three numeric values.")
    return (float(value[0]), float(value[1]), float(value[2]))


def _matrix3_or_empty(value: Any) -> Matrix3 | tuple[()]:
    if value in (None, "", []):
        return ()
    if len(value) != 3:
        raise ValueError("lattice_matrix must contain three rows.")
    return (
        _tuple3(value[0], "lattice_matrix"),
        _tuple3(value[1], "lattice_matrix"),
        _tuple3(value[2], "lattice_matrix"),
    )


def _pbc(value: Any) -> tuple[bool, bool, bool]:
    if len(value) != 3:
        raise ValueError("pbc must contain three boolean values.")
    return (bool(value[0]), bool(value[1]), bool(value[2]))


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _norm(vector: Vector3) -> float:
    return sqrt(sum(component * component for component in vector))


def _angle(left: Vector3, right: Vector3) -> float:
    denom = _norm(left) * _norm(right)
    if denom == 0.0:
        return 0.0
    cosine = max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / denom))
    return degrees(acos(cosine))
