"""HC-13 — MIMIC chronic-HTN cohort feasibility gate (COUNTING ONLY, no modeling).

Answers: how many subjects survive each cohort rule? Requiring >=2 outpatient OMR
BP readings *before* the earliest anchor HTN encounter compounds attrition (many
patients' first MIMIC appearance IS the HTN encounter). This reports the attrition
waterfall so we can decide the v1 rule (365d / >=2) vs the fallback (730d / >=1)
BEFORE building the cohort. No profiles are produced here.

    python -m pipelines.mimic.feasibility
"""
from __future__ import annotations

import json
import re

import pandas as pd

import vocab

from . import config

_BP_RE = re.compile(r"^\s*\d{2,3}\s*/\s*\d{2,3}")  # "120/80"-ish


def _anchor_subject_hadms() -> pd.DataFrame:
    """Rows (subject_id, hadm_id) whose diagnosis is an HTN anchor code."""
    dx = pd.read_csv(
        config.HOSP / "diagnoses_icd.csv.gz",
        usecols=["subject_id", "hadm_id", "icd_code", "icd_version"],
        dtype={"icd_code": "string", "icd_version": "Int64"},
    )
    # Classify only the distinct (code, version) pairs, then map back — cheap.
    pairs = dx[["icd_code", "icd_version"]].drop_duplicates()
    pairs["is_anchor"] = pairs.apply(
        lambda r: vocab.is_htn_anchor(r["icd_code"], int(r["icd_version"])), axis=1
    )
    anchor_codes = pairs[pairs["is_anchor"]][["icd_code", "icd_version"]]
    anchor = dx.merge(anchor_codes, on=["icd_code", "icd_version"], how="inner")
    return anchor[["subject_id", "hadm_id"]].drop_duplicates()


def _earliest_anchor_admit() -> pd.DataFrame:
    """Per subject: earliest admittime among anchor encounters."""
    anchor = _anchor_subject_hadms()
    adm = pd.read_csv(
        config.HOSP / "admissions.csv.gz",
        usecols=["subject_id", "hadm_id", "admittime"],
        parse_dates=["admittime"],
    )
    merged = anchor.merge(adm, on=["subject_id", "hadm_id"], how="inner")
    return (
        merged.groupby("subject_id")["admittime"].min()
        .rename("index_admit").reset_index()
    )


def _omr_bp() -> pd.DataFrame:
    """Outpatient OMR blood-pressure rows with a parseable value and a date."""
    omr = pd.read_csv(
        config.HOSP / "omr.csv.gz",
        usecols=["subject_id", "chartdate", "result_name", "result_value"],
        dtype={"result_name": "string", "result_value": "string"},
        parse_dates=["chartdate"],
    )
    bp = omr[omr["result_name"].str.startswith("Blood Pressure", na=False)].copy()
    bp = bp[bp["result_value"].str.match(_BP_RE, na=False)]
    return bp[["subject_id", "chartdate"]]


def build_waterfall() -> dict:
    patients = pd.read_csv(
        config.HOSP / "patients.csv.gz", usecols=["subject_id", "anchor_age"]
    )
    n_subjects = patients["subject_id"].nunique()
    n_adults = patients.loc[patients["anchor_age"] >= config.MIN_AGE, "subject_id"].nunique()

    idx = _earliest_anchor_admit()                     # anchor subjects + index date
    n_anchor = idx["subject_id"].nunique()

    bp = _omr_bp()
    n_any_omr_bp = bp["subject_id"].nunique()

    # OMR-only cohort (no HTN ICD required): subjects with >=2 distinct BP dates.
    omr_dates = bp.groupby("subject_id")["chartdate"].nunique()
    n_omr_only_ge2 = int((omr_dates >= config.MIN_READINGS_PRIMARY).sum())

    # Anchor patients with qualifying PRIOR OMR (before index, within a window).
    j = bp.merge(idx, on="subject_id", how="inner")
    j["days_before"] = (j["index_admit"] - j["chartdate"]).dt.days
    prior = j[j["days_before"] > 0]                    # strictly before index
    n_anchor_any_prior = prior["subject_id"].nunique()

    def _qualify(window_days: int, min_reads: int) -> int:
        w = prior[prior["days_before"] <= window_days]
        distinct = w.groupby("subject_id")["chartdate"].nunique()
        return int((distinct >= min_reads).sum())

    n_primary = _qualify(config.WINDOW_PRIMARY_DAYS, config.MIN_READINGS_PRIMARY)
    n_fallback = _qualify(config.WINDOW_FALLBACK_DAYS, config.MIN_READINGS_FALLBACK)

    return {
        "all_subjects": int(n_subjects),
        "adults_ge18": int(n_adults),
        "with_htn_anchor_dx": int(n_anchor),
        "anchor_with_any_prior_omr_bp": int(n_anchor_any_prior),
        "PRIMARY_anchor_ge2_within_365d": int(n_primary),
        "FALLBACK_anchor_ge1_within_730d": int(n_fallback),
        "any_omr_bp_subjects": int(n_any_omr_bp),
        "OMR_only_cohort_ge2_dates": int(n_omr_only_ge2),
        "params": {
            "primary": f">={config.MIN_READINGS_PRIMARY} distinct dates within {config.WINDOW_PRIMARY_DAYS}d before index",
            "fallback": f">={config.MIN_READINGS_FALLBACK} reading within {config.WINDOW_FALLBACK_DAYS}d before index",
        },
    }


def main() -> int:
    w = build_waterfall()
    print("MIMIC-IV chronic-HTN cohort — attrition waterfall (counting only)\n")
    order = [
        ("All subjects (hosp)", "all_subjects"),
        ("  Adults >=18", "adults_ge18"),
        ("  With HTN anchor dx (earliest anchor encounter)", "with_htn_anchor_dx"),
        ("    ...with ANY prior OMR BP", "anchor_with_any_prior_omr_bp"),
        ("    PRIMARY: >=2 OMR BP on distinct dates <365d before index", "PRIMARY_anchor_ge2_within_365d"),
        ("    FALLBACK: >=1 OMR BP <730d before index", "FALLBACK_anchor_ge1_within_730d"),
        ("OMR-only cohort: any OMR BP", "any_omr_bp_subjects"),
        ("  OMR-only: >=2 distinct BP dates (undiagnosed capture)", "OMR_only_cohort_ge2_dates"),
    ]
    for label, key in order:
        print(f"{w[key]:>8,}  {label}")
    out = config.QA / "feasibility_waterfall.json"
    out.write_text(json.dumps(w, indent=2))
    print(f"\nsaved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
