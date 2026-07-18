"""Range gating + QA reporting (DATA dict §4, §7).

apply_ranges nulls out-of-range numeric values and records every violation.
write_report emits row counts + missingness so QA happens before any label run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config


def apply_ranges(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Set values outside config.RANGES to NA; return (df, violation log)."""
    df = df.copy()
    log: list[dict] = []
    for col, rng in config.RANGES.items():
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        bad = (vals < rng.lo) | (vals > rng.hi)
        n_bad = int(bad.fillna(False).sum())
        if n_bad:
            log.append({"column": col, "lo": rng.lo, "hi": rng.hi, "n_nulled": n_bad})
            df.loc[bad.fillna(False), col] = pd.NA
    return df, log


def write_report(df: pd.DataFrame, violations: list[dict], row_counts: dict[str, int]) -> Path:
    report = {
        "cycle": config.CYCLE,
        "n_profiles": int(len(df)),
        "source_row_counts": row_counts,
        "range_violations": violations,
        "missingness": {
            c: round(float(df[c].isna().mean()), 4) for c in df.columns
        },
        "bp_stage_distribution": (
            df["bp_stage"].value_counts(dropna=False).to_dict()
            if "bp_stage" in df else {}
        ),
    }
    # value_counts keys may be NA/np types; coerce to str for JSON.
    report["bp_stage_distribution"] = {
        str(k): int(v) for k, v in report["bp_stage_distribution"].items()
    }
    out = config.QA / f"nhanes_qa_{config.CYCLE}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"  QA report -> {out}")
    return out
