"""Typed loader for the HC-10 profile CSV.

`pipelines/nhanes` writes profiles to CSV, where everything is a string. The engine
is deliberately strict about types -- `vocab.bp_stage_scalar` raises on a string SBP
rather than silently mis-comparing it -- so a CSV row cannot be fed to `evaluate()`
directly. This module is the missing seam: CSV text in, schema-typed profile out.

Coercion is driven by `schemas/patient_profile.schema.json` rather than a hand-kept
field list, so a new column picks up the right type automatically instead of
arriving as a string and failing somewhere downstream.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Mapping

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "patient_profile.schema.json"

# Identity/design columns the pipeline emits alongside the schema fields. Kept as
# text: they are join keys and survey weights, never engine inputs.
_PASSTHROUGH: frozenset[str] = frozenset({"SEQN", "sdmvpsu", "sdmvstra", "WTMEC2YR"})

_NULLS: frozenset[str] = frozenset({"", "NA", "nan", "NaN", "None", "null"})


@lru_cache(maxsize=1)
def _field_types() -> dict[str, set[str]]:
    """Declared JSON-schema types per field, as a set (fields are usually T|null)."""
    schema = json.loads(_SCHEMA_PATH.read_text())
    out: dict[str, set[str]] = {}
    for name, spec in schema.get("properties", {}).items():
        declared = spec.get("type", "string")
        out[name] = set(declared) if isinstance(declared, list) else {declared}
    return out


def _coerce(name: str, raw: str, types: set[str]) -> Any:
    if raw in _NULLS:
        return None
    if "array" in types:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []
    if "boolean" in types:
        if raw in ("True", "true", "1"):
            return True
        if raw in ("False", "false", "0"):
            return False
        return None
    if "number" in types or "integer" in types:
        try:
            return float(raw)
        except ValueError:
            # A field declared numeric that also permits strings (race_eth) keeps
            # its text; anything else unparseable becomes a missing value, which
            # the engine's three-valued logic already handles as "unknown".
            return raw if "string" in types else None
    return raw


def coerce_row(row: Mapping[str, str]) -> dict[str, Any]:
    """One CSV row -> a schema-typed PatientProfile (plus passthrough identifiers)."""
    types = _field_types()
    out: dict[str, Any] = {}
    for name, raw in row.items():
        if name in _PASSTHROUGH:
            out[name] = raw
        elif name in types:
            out[name] = _coerce(name, raw, types[name])
        else:
            out[name] = None if raw in _NULLS else raw
    return out


def load_profiles_csv(path: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Read a profile CSV into typed profiles ready for `evaluate()` and `render()`."""
    return list(iter_profiles_csv(path, limit))


def iter_profiles_csv(path: str | Path, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Streaming form of `load_profiles_csv` (the full NHANES corpus is 4,806 rows)."""
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            if limit is not None and i >= limit:
                return
            yield coerce_row(row)
