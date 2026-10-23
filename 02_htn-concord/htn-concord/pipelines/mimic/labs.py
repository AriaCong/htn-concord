"""HC-15 + HC-27 -- itemid-filtered lab loading, bound strictly before admittime.

``hosp/labevents`` is 2.4 GB gzipped (~158M rows). It is read in chunks and
filtered by ``itemid`` and cohort membership INSIDE the loop, so the whole table
is never in memory. Chunked pandas rather than a second query engine: no new
dependency, one idiom across the codebase, and the pass runs rarely.

Two rules here are label-validity rules, not performance details.

**HC-27 -- the time bound.** Take the most recent value **strictly before**
``admittime``, within a pre-registered lookback window. The superseded wording,
"the value nearest the index encounter", is *bidirectional*: it lets a
creatinine or potassium drawn **during** the index admission set ``egfr`` and
the hyperkalemia flag. That value is post-decision and very plausibly reflects
the therapy being evaluated, so it is leakage. Day 0 does not qualify either --
a draw timestamped at or after ``admittime`` is not before the decision.

No qualifying value yields ``NA``, so the engine abstains. A lab is never
carried forward across the gap, and never imputed.

**Use ``valuenum``, never ``value``.** The text column may hold the
de-identification token, and parsing it would turn a redaction into a number.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import config

# MIMIC records potassium as mEq/L, which for a monovalent ion is numerically
# identical to mmol/L -- no conversion, but the assertion must accept it or it
# rejects every MIMIC potassium. Verified against the real table by
# scripts/verify_mimic_itemids.py.
EXPECTED_UNITS: dict[str, frozenset[str]] = {
    "creatinine": frozenset({"mg/dL"}),
    "potassium":  frozenset({"mEq/L", "mmol/L"}),
    "uacr":       frozenset({"mg/g"}),
    "hba1c":      frozenset({"%"}),
    "total_chol": frozenset({"mg/dL"}),
    "hdl":        frozenset({"mg/dL"}),
}

_USECOLS = ["subject_id", "itemid", "charttime", "valuenum", "valueuom"]


def _itemid_to_analyte() -> dict[int, str]:
    return {i: a for a, ids in config.LAB_ITEMIDS.items() for i in ids}


def _check_units(df: pd.DataFrame) -> None:
    """Fail loudly on a unit we did not expect.

    Unit drift is the main silent-error risk in this dataset: a creatinine in
    umol/L is ~88x a creatinine in mg/dL, and it would sail through every range
    gate as an implausibly high but not impossible value, then produce a
    confident eGFR and a wrong CKD flag.
    """
    for analyte, allowed in EXPECTED_UNITS.items():
        seen = set(
            df.loc[df["analyte"] == analyte, "valueuom"].dropna().unique()
        )
        unexpected = seen - allowed
        if unexpected:
            raise ValueError(
                f"unexpected unit(s) for {analyte}: {sorted(unexpected)}; "
                f"expected one of {sorted(allowed)}. Refusing to convert silently."
            )


def load_labs(
    path_or_buf: Any,
    cohort: pd.DataFrame,
    lookback_days: int | None = None,
    chunk_rows: int | None = None,
) -> pd.DataFrame:
    """One row per cohort subject, one column per analyte.

    ``cohort`` must carry ``subject_id`` and ``index_admit``. ``lookback_days``
    defaults to the pre-registered 365; pass
    ``config.LAB_LOOKBACK_SENSITIVITY_DAYS`` for the pre-registered sensitivity.
    """
    lookback = config.LAB_LOOKBACK_DAYS if lookback_days is None else lookback_days
    chunksize = config.LAB_CHUNK_ROWS if chunk_rows is None else chunk_rows

    wanted = _itemid_to_analyte()
    subjects = set(cohort["subject_id"])

    frames: list[pd.DataFrame] = []
    reader = pd.read_csv(
        path_or_buf,
        usecols=_USECOLS,
        dtype={"subject_id": "Int64", "itemid": "Int64",
               "valuenum": "float64", "valueuom": "string"},
        parse_dates=["charttime"],
        chunksize=chunksize,
    )
    for chunk in reader:
        hit = chunk[
            chunk["itemid"].isin(wanted) & chunk["subject_id"].isin(subjects)
        ]
        # Drop null valuenum here rather than later: a row whose only value is
        # the deid token carries no number and must not survive as a NaN that
        # something downstream fills.
        hit = hit[hit["valuenum"].notna()]
        if len(hit):
            frames.append(hit)

    analytes = list(config.LAB_ITEMIDS)
    out = cohort[["subject_id"]].drop_duplicates().reset_index(drop=True)

    if not frames:
        for a in analytes:
            out[a] = pd.Series([pd.NA] * len(out), dtype="Float64")
        return out

    lab = pd.concat(frames, ignore_index=True)
    lab["analyte"] = lab["itemid"].map(wanted)
    _check_units(lab)

    lab = lab.merge(
        cohort[["subject_id", "index_admit"]].drop_duplicates("subject_id"),
        on="subject_id", how="inner",
    )

    # HC-27: strictly before admittime, within the window. `> 0` excludes a
    # same-instant draw; `<= window` excludes a stale one.
    delta = (lab["index_admit"] - lab["charttime"]).dt.total_seconds()
    lab = lab[(delta > 0) & (delta <= lookback * 86_400)]

    # Most recent qualifying value per (subject, analyte). Sorting by charttime
    # and keeping the last is stable and selects by RECENCY, never by itemid --
    # so a whole-blood creatinine cannot outrank a more recent serum one.
    lab = lab.sort_values(["subject_id", "analyte", "charttime"])
    latest = lab.drop_duplicates(subset=["subject_id", "analyte"], keep="last")

    wide = latest.pivot(index="subject_id", columns="analyte", values="valuenum")
    out = out.merge(wide.reset_index(), on="subject_id", how="left")
    for a in analytes:
        if a not in out.columns:
            out[a] = pd.NA
        out[a] = out[a].astype("Float64")
    return out[["subject_id"] + analytes]
