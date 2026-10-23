"""Validate PatientProfile rows against schemas/patient_profile.schema.json.

Enforces the "one canonical contract" invariant the whole architecture rests on:
every source's output must validate here before it is written. Fails loudly.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "patient_profile.schema.json"


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def _row_to_jsonable(row: dict) -> dict:
    """pandas NA/NaN -> None; numpy scalars -> python; lists pass through."""
    out = {}
    for k, v in row.items():
        if isinstance(v, list):
            out[k] = v
        elif v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
            out[k] = None
        elif pd.isna(v):
            out[k] = None
        elif hasattr(v, "item"):        # numpy scalar
            out[k] = v.item()
        else:
            out[k] = v
    return out


def validate_profiles(df: pd.DataFrame, sample: int | None = None) -> int:
    """Validate every row (or a sample) against the schema. Raises on first
    violation with the offending row index. Returns count validated."""
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "jsonschema is required for contract validation; add it to requirements."
        ) from exc

    schema = _load_schema()
    validator = jsonschema.Draft7Validator(schema)
    frame = df.sample(sample, random_state=0) if sample and sample < len(df) else df
    n = 0
    for idx, row in frame.iterrows():
        record = _row_to_jsonable(row.to_dict())
        errors = sorted(validator.iter_errors(record), key=lambda e: e.path)
        if errors:
            msgs = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
            raise ValueError(f"PatientProfile row {idx} violates schema: {msgs}")
        n += 1
    return n
