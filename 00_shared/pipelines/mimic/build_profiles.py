"""HC-18 -- orchestrate MIMIC-IV cleaning into canonical PatientProfile rows.

    cohort -> labs -> icd -> meds -> derive -> range-gate -> validate -> QA

Mirrors ``pipelines/nhanes/build_profiles.py`` deliberately. Derivation, range
gating and schema validation all come from ``pipelines/common``: the same eGFR,
the same staging thresholds, the same contract. Nothing below the cleaning
boundary branches on data source.

    python -m pipelines.mimic.build_profiles              # primary cohort
    python -m pipelines.mimic.build_profiles --absence prior_only

Two MIMIC-specific choices that a reader should not have to infer:

* **Age is offset to the index admission**, not raw ``anchor_age``:
  ``anchor_age + (index_year - anchor_year)``. ``anchor_age`` is the age at the
  patient's anchor year, which can be years away from the index encounter. Ages
  89+ are topcoded to 91, and those rows fall outside PREVENT's 30-79 window
  anyway.
* **The absence reading is an explicit switch**, never a default that hides.
  ``prior_only`` counts diagnoses from admissions strictly before the index
  ``admittime``; ``prior_plus_index`` also counts the index encounter's own
  codes. They differ materially -- 71.4% versus 90.2% resolvable on the decision
  cohort -- so both are produced and both are reported.
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

import vocab
from pipelines.common import derive, qa, validate

from . import cohort, config, icd, labs, meds

# Same column contract as NHANES, minus the survey-design columns, which have no
# MIMIC analogue. Order is fixed so the emitted CSV is diffable across runs.
PROFILE_COLUMNS = [
    "subject_id", "hadm_id", "source", "age", "sex", "race_eth",
    "sbp", "dbp", "bp_stage", "bp_context", "bp_n_readings",
    "creatinine", "egfr", "potassium", "uacr", "ckd_albuminuria",
    "diabetes", "clinical_cvd", "hba1c",
    "total_chol", "hdl", "bmi", "current_smoker",
    "told_hypertension", "on_bp_meds", "med_classes", "statin_use",
    "prevent_10yr", "contraindications",
]

# MIMIC plausibility ranges. The VALUES are a per-source choice; the gating
# MECHANISM is shared (reject to NA, never clip; run before derivation).
RANGES: dict[str, qa.Range] = {
    "sbp":        qa.Range(vocab.SBP_MIN, vocab.SBP_MAX),
    "dbp":        qa.Range(vocab.DBP_MIN, vocab.DBP_MAX),
    "creatinine": qa.Range(0.1, 20),      # mg/dL
    "potassium":  qa.Range(1.5, 9),       # mmol/L (MIMIC records mEq/L)
    "age":        qa.Range(0, 120),
    "total_chol": qa.Range(50, 600),      # mg/dL
    "hdl":        qa.Range(5, 200),       # mg/dL
    "uacr":       qa.Range(0, 30000),     # mg/g
    "hba1c":      qa.Range(2, 20),        # %
}

ABSENCE_READINGS = ("prior_only", "prior_plus_index")


def _age_at_index(cohort_df: pd.DataFrame, patients: pd.DataFrame) -> pd.Series:
    """anchor_age + (index_year - anchor_year).

    Raw anchor_age is the age at the patient's anchor year, which may be years
    from the index encounter; using it directly would misplace patients relative
    to the PREVENT 30-79 window and to the adult cutoff.
    """
    m = cohort_df.merge(patients, on="subject_id", how="left")
    offset = m["index_admit"].dt.year - m["anchor_year"]
    return (m["anchor_age"] + offset).astype("Float64")


def _hadm_scope(cohort_df: pd.DataFrame, reading: str) -> tuple[set, set]:
    """(prior_hadms, index_hadms) for the chosen absence reading."""
    adm = pd.read_csv(
        config.HOSP / "admissions.csv.gz",
        usecols=["subject_id", "hadm_id", "admittime"],
        parse_dates=["admittime"],
    )
    adm = adm[adm["subject_id"].isin(set(cohort_df["subject_id"]))]
    adm = adm.merge(cohort_df[["subject_id", "index_admit"]], on="subject_id", how="inner")
    prior = set(adm.loc[adm["admittime"] < adm["index_admit"], "hadm_id"])
    index = set(cohort_df["hadm_id"])
    return (prior, set()) if reading == "prior_only" else (prior, index)


def build(reading: str = "prior_plus_index") -> pd.DataFrame:
    if reading not in ABSENCE_READINGS:
        raise ValueError(f"reading must be one of {ABSENCE_READINGS}, got {reading!r}")
    print(f"Building MIMIC-IV primary profiles (absence reading = {reading})")
    row_counts: dict[str, int] = {}

    coh, readings = cohort.primary_cohort()
    row_counts["cohort_subjects"] = int(len(coh))
    print(f"  cohort: {len(coh):,} subjects (HC-26 rule)")

    bp = cohort.summarize_bp(readings)

    patients = pd.read_csv(
        config.HOSP / "patients.csv.gz",
        usecols=["subject_id", "gender", "anchor_age", "anchor_year"],
    )
    df = coh.merge(patients[["subject_id", "gender"]], on="subject_id", how="left")
    df["age"] = _age_at_index(coh, patients).to_numpy()
    df["sex"] = df["gender"].map({"F": "female", "M": "male"})
    df = df.drop(columns=["gender"])

    df = df.merge(bp, on="subject_id", how="left")

    print("  labs (itemid-filtered, strictly pre-admittime)...", flush=True)
    lb = labs.load_labs(config.HOSP / "labevents.csv.gz", coh)
    row_counts["lab_subjects_with_any_value"] = int(
        lb.drop(columns=["subject_id"]).notna().any(axis=1).sum()
    )
    df = df.merge(lb, on="subject_id", how="left")

    print("  diagnoses crosswalk...", flush=True)
    prior_hadms, index_hadms = _hadm_scope(coh, reading)
    dx = pd.read_csv(
        config.HOSP / "diagnoses_icd.csv.gz",
        usecols=["subject_id", "hadm_id", "icd_code", "icd_version"],
        dtype={"icd_code": "string", "icd_version": "Int64"},
    )
    flags = icd.crosswalk(dx, coh, prior_hadms, index_hadms)
    coded_contra = icd.contraindications_from_flags(flags)
    df = df.merge(flags.drop(columns=["has_any_dx"]), on="subject_id", how="left")

    print("  medication reconciliation...", flush=True)
    md = meds.pre_index_meds(
        config.ED / "medrecon.csv.gz", config.ED / "edstays.csv.gz", coh
    )
    df = df.merge(md.drop(columns=["has_medrecon"]), on="subject_id", how="left")

    # ---- range gate FIRST, then derive from clean inputs --------------------
    df, violations = qa.apply_ranges(df, RANGES)

    # ---- derived engine fields, all from the shared core --------------------
    df["egfr"] = derive.egfr_ckdepi_2021(df["creatinine"], df["age"], df["sex"])
    df["bp_stage"] = derive.bp_stage(df["sbp"], df["dbp"])
    df["ckd_albuminuria"] = derive.ckd_albuminuria(df["egfr"], df["uacr"])
    # Diabetes is the Kleene OR of the coded flag and lab confirmation, matching
    # NHANES's self-report OR HbA1c: True beats unknown, False only when both
    # limbs are known negative.
    df["diabetes"] = derive.resolve_diabetes(
        df.rename(columns={"diabetes": "diabetes_self"})
    )
    df["prevent_10yr"] = derive.prevent_10yr(df)

    # Contraindications: coded flags plus the lab-derived hyperkalemia limb.
    # Assembled here, not in icd.py, because potassium is not a code.
    k = pd.to_numeric(df["potassium"], errors="coerce")
    hyperk = (k >= vocab.K_HYPERKALEMIA).fillna(False).to_numpy(dtype=bool)
    df["contraindications"] = [
        sorted(set(coded) | ({"hyperkalemia"} if hk else set()))
        for coded, hk in zip(coded_contra.to_numpy(), hyperk)
    ]

    df["source"] = "mimic_iv"
    # Every profile BP here is outpatient OMR taken before the index admission.
    # ED and ICU readings never reach this column -- they are `admission`
    # context and the engine abstains on them.
    df["bp_context"] = "office"
    # Every primary-cohort subject was selected by an HTN anchor code.
    df["told_hypertension"] = True
    df["race_eth"] = pd.NA      # not used for labelling; engine is race-neutral
    df["bmi"] = pd.NA           # omr BMI rows: cohort description only, HC-18 follow-up
    df["med_classes"] = df["med_classes"].apply(
        lambda v: v if isinstance(v, list) else []
    )

    for c in PROFILE_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[PROFILE_COLUMNS]

    # Enforce the canonical contract before anything downstream consumes it.
    # subject_id/hadm_id are extra properties, which the schema permits; they
    # are the join key to the hidden-label store and never reach a vignette.
    n_ok = validate.validate_profiles(df)
    print(f"  schema: {n_ok:,} profiles validate against patient_profile.schema.json")

    qa.write_report(
        df, violations, row_counts,
        config.QA / f"mimic_qa_primary_{reading}.json",
        extra={
            "cohort": "primary",
            "absence_reading": reading,
            "cohort_rule": (
                "earliest HTN-anchor admission with an index-stay ED medication "
                "reconciliation and >=2 OMR BP on distinct dates within "
                f"{config.WINDOW_PRIMARY_DAYS} d strictly before admittime"
            ),
            "bp_summary_statistic": "mean (HC-23)",
            "lab_lookback_days": config.LAB_LOOKBACK_DAYS,
            "contraindication_counts": {
                c: int(sum(c in row for row in df["contraindications"]))
                for c in vocab.CONTRAINDICATION_FLAGS
            },
            "on_bp_meds": {
                "true": int((df["on_bp_meds"] == True).sum()),    # noqa: E712
                "false": int((df["on_bp_meds"] == False).sum()),  # noqa: E712
                "unknown": int(df["on_bp_meds"].isna().sum()),
            },
        },
    )
    return df


_LIST_COLUMNS = ["med_classes", "contraindications"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--absence", choices=ABSENCE_READINGS, default="prior_plus_index")
    args = ap.parse_args()

    df = build(args.absence)
    csv = config.PROCESSED / f"mimic_profiles_primary_{args.absence}.csv"
    csv_df = df.copy()
    for c in _LIST_COLUMNS:
        csv_df[c] = csv_df[c].apply(lambda v: json.dumps(v if isinstance(v, list) else []))
    csv_df.to_csv(csv, index=False)
    print(f"  wrote {csv}  ({len(df):,} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
