"""HC-18 -- MIMIC cohort selection. The single home of the index-encounter rule.

DESIGN INVARIANT, carry this sentence into the paper:

    An HTN ICD code selects the patient/encounter (the anchor). It NEVER
    generates the label. Chronic staging is derived independently from
    outpatient OMR taken *before* that encounter.

Three sub-cohorts, per the spec:

* **Primary** -- the earliest HTN-anchor admission that both carries a
  medication reconciliation at its own ED stay and has >=2 OMR BP readings on
  distinct dates within 365 d strictly before ``admittime``. The only cohort
  that can receive an initiate-versus-intensify label, because it is the only
  one where ``on_bp_meds`` is knowable. **8,919 subjects** as measured by the
  HC-98 gate.

  Note the rule binds on the *reconciliation*, not on ED linkage. 9,492 index
  encounters are ED-linked but only 8,921 of those stays carry a reconciliation,
  and a stay without one cannot establish ``on_bp_meds`` -- which is the entire
  reason the linkage was required. Signed off 2026-09-20.

* **OMR-only** -- >=2 OMR BP on distinct dates, with no HTN ICD requirement.
  Captures undiagnosed and undertreated patients, where the concordance gaps are
  most interesting.

* **Text-robustness** -- anchor patients with a discharge summary, no OMR
  requirement. Task-C extraction and error propagation.

The counting functions live here rather than in ``feasibility`` so that the
attrition waterfall and the profile builder cannot drift apart: the waterfall
must justify the cohort the builder actually produces.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

import vocab

from . import config, ed, omr_bp


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------
def anchor_subject_hadms(path_or_buf: Any = None) -> pd.DataFrame:
    """(subject_id, hadm_id) pairs whose diagnosis is an HTN anchor code.

    Anchor sets come from ``vocab``; they are never re-typed here. Secondary
    hypertension (ICD-9 405, ICD-10 I15) is excluded by ``vocab.is_htn_anchor``
    itself -- it is out of scope for a primary-HTN benchmark, and an earlier
    draft of the data dictionary wrongly listed it as included.
    """
    src = config.HOSP / "diagnoses_icd.csv.gz" if path_or_buf is None else path_or_buf
    dx = pd.read_csv(
        src,
        usecols=["subject_id", "hadm_id", "icd_code", "icd_version"],
        dtype={"icd_code": "string", "icd_version": "Int64"},
    )
    pairs = dx[["icd_code", "icd_version"]].drop_duplicates()
    pairs = pairs.assign(is_anchor=[
        vocab.is_htn_anchor(c, v) if pd.notna(v) else False
        for c, v in zip(pairs["icd_code"], pairs["icd_version"])
    ])
    anchor_codes = pairs.loc[pairs["is_anchor"], ["icd_code", "icd_version"]]
    anchor = dx.merge(anchor_codes, on=["icd_code", "icd_version"], how="inner")
    return anchor[["subject_id", "hadm_id"]].drop_duplicates().reset_index(drop=True)


def earliest_anchor_admit(
    diagnoses: Any = None, admissions: Any = None
) -> pd.DataFrame:
    """Per subject: the earliest anchor encounter, as [subject_id, hadm_id,
    index_admit].

    Ties on ``admittime`` break on the smallest ``hadm_id`` so the index
    encounter is deterministic across runs. An earlier version took a group
    minimum and dropped ``hadm_id``, which left the choice dependent on row
    order and made the ED join impossible.
    """
    anchor = anchor_subject_hadms(diagnoses)
    src = config.HOSP / "admissions.csv.gz" if admissions is None else admissions
    adm = pd.read_csv(
        src,
        usecols=["subject_id", "hadm_id", "admittime"],
        parse_dates=["admittime"],
    )
    merged = anchor.merge(adm, on=["subject_id", "hadm_id"], how="inner")
    merged = merged.sort_values(["subject_id", "admittime", "hadm_id"])
    idx = merged.drop_duplicates(subset="subject_id", keep="first")
    return (
        idx[["subject_id", "hadm_id", "admittime"]]
        .rename(columns={"admittime": "index_admit"})
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# ED linkage
# ---------------------------------------------------------------------------
def ed_linked_hadms(edstays: Any = None) -> set[int]:
    """hadm_ids that have an ED stay -- the precondition for a reconciliation."""
    src = config.ED / "edstays.csv.gz" if edstays is None else edstays
    return set(ed.load_edstays(src)["hadm_id"].astype(int).tolist())


def hadms_with_medrecon(edstays: Any = None, medrecon: Any = None) -> set[int]:
    """hadm_ids whose OWN ED stay carries at least one reconciled med row.

    Stay-level, deliberately. Asking whether the subject has a reconciliation
    somewhere in their history is looser and inflates the cohort: the
    reconciliation that establishes ``on_bp_meds`` has to belong to the index
    visit, or it describes a different point in time.
    """
    est = config.ED / "edstays.csv.gz" if edstays is None else edstays
    rec = config.ED / "medrecon.csv.gz" if medrecon is None else medrecon
    rec_stays = set(
        pd.read_csv(rec, usecols=["stay_id"])["stay_id"]
        .dropna().astype(int).unique().tolist()
    )
    stays = ed.load_edstays(est)
    return set(stays[stays["stay_id"].isin(rec_stays)]["hadm_id"].astype(int).tolist())


# ---------------------------------------------------------------------------
# Blood pressure windowing
# ---------------------------------------------------------------------------
def qualifying_omr(
    index: pd.DataFrame,
    omr: Any = None,
    window_days: int | None = None,
    min_dates: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(subjects meeting the BP rule, their qualifying readings).

    Readings must fall **strictly before** the index admission -- at least one
    full day prior. A same-day reading sits at or after the decision point, so
    it cannot describe the chronic pressure the decision was made on.
    """
    window = config.WINDOW_PRIMARY_DAYS if window_days is None else window_days
    need = config.MIN_READINGS_PRIMARY if min_dates is None else min_dates

    src = config.HOSP / "omr.csv.gz" if omr is None else omr
    bp = omr_bp.load_omr_bp(src)
    j = bp.merge(index[["subject_id", "index_admit"]], on="subject_id", how="inner")
    days = (j["index_admit"] - j["chartdate"]).dt.days
    j = j[(days >= 1) & (days <= window)]

    dates = j.groupby("subject_id")["chartdate"].nunique()
    keep = set(dates[dates >= need].index)
    return index[index["subject_id"].isin(keep)].reset_index(drop=True), \
        j[j["subject_id"].isin(keep)].reset_index(drop=True)


def summarize_bp(readings: pd.DataFrame) -> pd.DataFrame:
    """Per-subject [sbp, dbp, bp_n_readings] from qualifying OMR readings.

    **MEAN, not median.** HC-23 was resolved 2026-08-08 against the guideline
    source: the 2025 AHA/ACC text specifies the average of >=2 readings
    throughout and never a median. NHANES already computes the mean, so both
    arms agree -- which is the property the shared derivation core exists to
    guarantee. Median is retained as a pre-registered sensitivity analysis.

    ``bp_n_readings`` counts distinct DATES, not rows: three readings taken at
    one visit are one occasion, and the guideline's ">=2 readings at >=2 visits"
    is about occasions.
    """
    agg = readings.groupby("subject_id", as_index=False)[["sbp", "dbp"]].mean()
    n = (
        readings.groupby("subject_id")["chartdate"].nunique()
        .rename("bp_n_readings").reset_index()
    )
    return agg.merge(n, on="subject_id", how="left")


# ---------------------------------------------------------------------------
# Sub-cohorts
# ---------------------------------------------------------------------------
def primary_cohort(
    diagnoses: Any = None,
    admissions: Any = None,
    edstays: Any = None,
    medrecon: Any = None,
    omr: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The decision cohort: ([subject_id, hadm_id, index_admit], readings)."""
    idx = earliest_anchor_admit(diagnoses, admissions)
    idx = idx[idx["hadm_id"].isin(hadms_with_medrecon(edstays, medrecon))]
    return qualifying_omr(idx, omr)
