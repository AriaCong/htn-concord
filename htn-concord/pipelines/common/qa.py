"""Range gating + QA reporting, shared across every source.

apply_ranges nulls out-of-range numeric values and records every violation.
write_report emits row counts + missingness so QA happens before any label run.

Ranges and the output path are parameters rather than imports: NHANES, MIMIC and
eICU each supply their own, while the gating semantics stay identical. The gate
REJECTS to NA and never clips -- a clipped 350 mmHg becomes a plausible-looking
290 that then produces a confident Stage-2 label from data known to be corrupt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Range:
    lo: float
    hi: float


def apply_ranges(
    df: pd.DataFrame, ranges: dict[str, Range]
) -> tuple[pd.DataFrame, list[dict]]:
    """Set values outside ``ranges`` to NA; return (df, violation log).

    Must run BEFORE derivation: deriving first would let an implausible
    creatinine produce an eGFR based on a value deleted a line later.
    """
    df = df.copy()
    log: list[dict] = []
    for col, rng in ranges.items():
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        bad = (vals < rng.lo) | (vals > rng.hi)
        n_bad = int(bad.fillna(False).sum())
        if n_bad:
            log.append({"column": col, "lo": rng.lo, "hi": rng.hi, "n_nulled": n_bad})
            df.loc[bad.fillna(False), col] = pd.NA
    return df, log


def write_report(
    df: pd.DataFrame,
    violations: list[dict],
    row_counts: dict[str, int],
    out_path: Path,
    extra: dict | None = None,
) -> Path:
    """Emit the per-source QA report. Written BEFORE any label run.

    ``extra`` carries source-specific fields (the NHANES cycle, a MIMIC cohort
    rule) so the shared writer never has to know about any of them.
    """
    report = {
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
    if extra:
        report.update(extra)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"  QA report -> {out_path}")
    return out_path
