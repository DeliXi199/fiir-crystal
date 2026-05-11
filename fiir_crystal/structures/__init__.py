"""Stdlib-only structure records used at external adapter boundaries."""

from fiir_crystal.structures.records import (
    CRYSTALFORMER_SEQUENCE_FIELDS,
    CrystalStructureRecord,
    crystalformer_sequence_status,
    has_crystalformer_raw_sequence,
)
from fiir_crystal.structures.serialization import read_jsonl, write_jsonl

__all__ = [
    "CRYSTALFORMER_SEQUENCE_FIELDS",
    "CrystalStructureRecord",
    "crystalformer_sequence_status",
    "has_crystalformer_raw_sequence",
    "read_jsonl",
    "write_jsonl",
]
