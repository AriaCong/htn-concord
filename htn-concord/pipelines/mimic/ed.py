"""HC-20 -- MIMIC-IV-ED 2.2: the join spine, home meds, and acute vitals.

Three jobs, and a hard line between them:

* ``edstays`` is the spine linking an ED visit (``stay_id``) to a hospital
  admission (``hadm_id``). Nothing else joins ED to hosp.
* ``medrecon`` is the ONLY leakage-safe source of home medications, and
  therefore of ``on_bp_meds`` -- the variable separating *initiate* from
  *intensify*. Inpatient ``prescriptions`` are written after the decision and
  discharge medications are literally the label; neither can establish what the
  patient was already taking.
* ``triage`` and ``vitalsign`` blood pressures are **acute, without exception**.
  Every row emitted here carries ``bp_context="admission"``, on which the engine
  abstains from chronic staging. Chronic staging comes from outpatient OMR only
  (``omr_bp``). An ED BP that leaked in as "chronic" would stage a hypertensive
  urgency as if it were the patient's usual pressure.

Functions take a path or buffer, like ``omr_bp``, so tests never touch the real
credentialed files.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

import vocab


# ---------------------------------------------------------------------------
# Spine
# ---------------------------------------------------------------------------
def load_edstays(path_or_buf: Any) -> pd.DataFrame:
    """[subject_id, hadm_id, stay_id, intime, outtime, disposition].

    Rows with no ``hadm_id`` are ED visits that went home. They are dropped
    because this pipeline exists to describe hospital index encounters; an ED
    visit with no admission has no index encounter to attach to.
    """
    df = pd.read_csv(
        path_or_buf,
        usecols=["subject_id", "hadm_id", "stay_id", "intime", "outtime", "disposition"],
        dtype={"subject_id": "Int64", "hadm_id": "Int64", "stay_id": "Int64",
               "disposition": "string"},
        parse_dates=["intime", "outtime"],
    )
    df = df.dropna(subset=["hadm_id", "stay_id"]).copy()
    df["hadm_id"] = df["hadm_id"].astype("int64")
    df["stay_id"] = df["stay_id"].astype("int64")
    df["subject_id"] = df["subject_id"].astype("int64")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Home medications
# ---------------------------------------------------------------------------
def load_medrecon(path_or_buf: Any) -> pd.DataFrame:
    """Reconciled home meds, deduplicated on (subject_id, name, gsn).

    The dedupe is required by the spec and is not cosmetic: medrecon repeats a
    drug across reconciliation passes within one visit, and an undeduplicated
    count would make a single agent look like several.
    """
    df = pd.read_csv(
        path_or_buf,
        usecols=["subject_id", "stay_id", "name", "gsn", "etcdescription"],
        dtype={"subject_id": "Int64", "stay_id": "Int64",
               "name": "string", "gsn": "string", "etcdescription": "string"},
    )
    df = df.dropna(subset=["stay_id"]).copy()
    df["stay_id"] = df["stay_id"].astype("int64")
    df["subject_id"] = df["subject_id"].astype("int64")
    return df.drop_duplicates(subset=["subject_id", "name", "gsn"]).reset_index(drop=True)


def _row_classes(row) -> list[str]:
    """Union of the ingredient-name and therapeutic-class routes.

    The name route is the same ``vocab.classify_drug`` NHANES uses, so the two
    arms classify identically wherever a name is recognisable. The
    therapeutic-class route adds recall for agents whose names match no keyword
    or suffix rule. Both live in ``vocab``; neither is re-typed here.
    """
    return sorted(
        set(vocab.classify_drug(row["name"]))
        | set(vocab.classify_etc_description(row["etcdescription"]))
    )


def med_classes_by_stay(path_or_buf: Any) -> pd.DataFrame:
    """One row per ED stay: [stay_id, subject_id, med_classes, on_bp_meds,
    statin_use, n_medrecon_rows].

    ``on_bp_meds`` is False -- a real negative -- when a reconciliation exists
    and contains no antihypertensive. It is never False by default: a stay with
    no reconciliation simply does not appear in this frame, and the caller must
    treat its absence as NA. Defaulting absence to False would systematically
    relabel *intensify* cases as *initiate*.
    """
    df = load_medrecon(path_or_buf)
    if df.empty:
        return pd.DataFrame(columns=["stay_id", "subject_id", "med_classes",
                                     "on_bp_meds", "statin_use", "n_medrecon_rows"])

    df["_classes"] = df.apply(_row_classes, axis=1)
    df["_statin"] = df.apply(
        lambda r: bool(vocab.is_statin(r["name"]))
        or vocab.is_statin_etc_description(r["etcdescription"]),
        axis=1,
    )

    grouped = df.groupby(["stay_id", "subject_id"], as_index=False).agg(
        med_classes=("_classes", lambda g: sorted({c for cs in g for c in cs})),
        statin_use=("_statin", "any"),
        n_medrecon_rows=("name", "size"),
    )
    grouped["on_bp_meds"] = grouped["med_classes"].map(lambda cs: len(cs) > 0)
    return grouped[["stay_id", "subject_id", "med_classes", "on_bp_meds",
                    "statin_use", "n_medrecon_rows"]]


# ---------------------------------------------------------------------------
# Acute vitals
# ---------------------------------------------------------------------------
def _numeric_bp(df: pd.DataFrame) -> pd.DataFrame:
    """Cast the zero-padded float strings ("71.0000") to numbers, drop rows with
    no pair, and reject implausible values to NA rather than clipping them.

    Clipping a 402 to 290 would turn a data-entry error into a plausible-looking
    hypertensive emergency.
    """
    out = df.copy()
    out["sbp"] = pd.to_numeric(out["sbp"], errors="coerce")
    out["dbp"] = pd.to_numeric(out["dbp"], errors="coerce")
    ok = (
        out["sbp"].between(vocab.SBP_MIN, vocab.SBP_MAX)
        & out["dbp"].between(vocab.DBP_MIN, vocab.DBP_MAX)
        & (out["sbp"] > out["dbp"])
    )
    out = out[ok.fillna(False)].copy()
    # Every ED reading is acute. This is the flag the engine abstains on.
    out["bp_context"] = "admission"
    return out.reset_index(drop=True)


def load_triage_bp(path_or_buf: Any) -> pd.DataFrame:
    """[subject_id, stay_id, sbp, dbp, acuity, chiefcomplaint, bp_context]."""
    df = pd.read_csv(
        path_or_buf,
        usecols=["subject_id", "stay_id", "sbp", "dbp", "acuity", "chiefcomplaint"],
        dtype={"subject_id": "Int64", "stay_id": "Int64",
               "sbp": "string", "dbp": "string", "chiefcomplaint": "string"},
    )
    out = _numeric_bp(df)
    out["acuity"] = pd.to_numeric(out["acuity"], errors="coerce")
    return out[["subject_id", "stay_id", "sbp", "dbp", "acuity",
                "chiefcomplaint", "bp_context"]]


def load_vitalsign_bp(path_or_buf: Any) -> pd.DataFrame:
    """[subject_id, stay_id, charttime, sbp, dbp, heartrate, bp_context]."""
    df = pd.read_csv(
        path_or_buf,
        usecols=["subject_id", "stay_id", "charttime", "sbp", "dbp", "heartrate"],
        dtype={"subject_id": "Int64", "stay_id": "Int64",
               "sbp": "string", "dbp": "string", "heartrate": "string"},
        parse_dates=["charttime"],
    )
    out = _numeric_bp(df)
    out["heartrate"] = pd.to_numeric(out["heartrate"], errors="coerce")
    return out[["subject_id", "stay_id", "charttime", "sbp", "dbp",
                "heartrate", "bp_context"]]


def hypertensive_urgency(bp: pd.DataFrame) -> pd.DataFrame:
    """Add a `hypertensive_urgency` flag (SBP >=180 or DBP >=120) to ED BP rows.

    This is the ONLY sanctioned use of an ED blood pressure. It is a severity
    descriptor for cohort reporting, never an input to chronic staging, and it
    is computed here rather than in the engine precisely so it cannot be
    mistaken for one.

    The 180/120 threshold is the conventional hypertensive-crisis cut-point. It
    is a descriptive label in this pipeline and is not used to generate any
    treatment decision, so it carries no labelling risk; it is flagged for HC-49
    with the rest of the encoded cut-points.
    """
    out = bp.copy()
    out["hypertensive_urgency"] = (out["sbp"] >= 180) | (out["dbp"] >= 120)
    return out
