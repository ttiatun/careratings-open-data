"""Load the release schema (schema/release_schema.json)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "release_schema.json"

# Schema type -> DuckDB type used when casting and when checking output columns.
DUCKDB_TYPES = {"string": "VARCHAR", "integer": "INTEGER", "number": "DOUBLE", "boolean": "BOOLEAN", "date": "DATE"}


@lru_cache(maxsize=1)
def load_schema(path: Path | None = None) -> dict:
    return json.loads((path or SCHEMA_PATH).read_text(encoding="utf-8"))


def table_columns(table: str, schema: dict | None = None) -> list[dict]:
    schema = schema or load_schema()
    return schema["tables"][table]["columns"]


def column_names(table: str, schema: dict | None = None) -> list[str]:
    return [c["name"] for c in table_columns(table, schema)]
