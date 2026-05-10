"""JSON/JSONL I/O helpers for lightweight FIIR experiments."""

from fiir_crystal.io.jsonl import (
    JsonlFormatError,
    read_json,
    read_jsonl,
    read_mock_candidates_jsonl,
    write_json,
    write_jsonl,
)

__all__ = [
    "JsonlFormatError",
    "read_json",
    "read_jsonl",
    "read_mock_candidates_jsonl",
    "write_json",
    "write_jsonl",
]
