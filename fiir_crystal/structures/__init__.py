"""Stdlib-only structure records used at external adapter boundaries."""

from fiir_crystal.structures.records import CrystalStructureRecord
from fiir_crystal.structures.serialization import read_jsonl, write_jsonl

__all__ = ["CrystalStructureRecord", "read_jsonl", "write_jsonl"]
