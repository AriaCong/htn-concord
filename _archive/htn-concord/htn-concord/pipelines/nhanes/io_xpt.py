"""Read NHANES SAS transport (.XPT) files into pandas DataFrames.

Uses pandas' built-in XPORT reader (no extra dependency). SEQN is coerced to a
nullable integer and set as the index-friendly key column.
"""
from __future__ import annotations

import pandas as pd

from . import config


def read_component(component: str) -> pd.DataFrame:
    path = config.raw_path(component)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing. Run: python -m pipelines.nhanes.download {component}"
        )
    df = pd.read_sas(path, format="xport", encoding="utf-8")
    # NHANES numeric columns load as float; keep SEQN as a clean integer key.
    if "SEQN" in df.columns:
        df["SEQN"] = df["SEQN"].astype("Int64")
    return df


def try_read(component: str) -> pd.DataFrame | None:
    """Return None (with a warning) for absent optional components."""
    try:
        return read_component(component)
    except FileNotFoundError as exc:
        if component in config.OPTIONAL:
            print(f"  optional component {component} not found — skipping. ({exc})")
            return None
        raise
