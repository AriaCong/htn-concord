"""Orchestrate NHANES cleaning -> one PatientProfile row per SEQN.

Pipeline: read -> clean each component -> merge on SEQN -> derive engine fields ->
range-gate -> cohort filter -> QA report -> write processed parquet + csv.

Cohort (plan): adults >=18 with >=1 valid oscillometric reading.
"""
from __future__ import annotations

import json
from functools import reduce

import pandas as pd

from . import clean, config, derive, drug_class, io_xpt, qa, validate

# Output column order for the canonical PatientProfile.
PROFILE_COLUMNS = [
    "SEQN", "source", "age", "sex", "race_eth",
    "sbp", "dbp", "bp_stage", "bp_context", "bp_n_readings",
    "creatinine", "egfr", "potassium", "uacr", "ckd_albuminuria",
    "diabetes", "clinical_cvd", "hba1c",
    "total_chol", "hdl", "bmi", "current_smoker",
    "told_hypertension", "on_bp_meds", "med_classes", "statin_use",
    "prevent_10yr", "contraindications",
    config.weight_col(), "sdmvpsu", "sdmvstra",
]


def _merge(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Left-join every cleaned component frame on SEQN into one wide table
    (skipping any that are None, i.e. absent optional components)."""
    frames = [f for f in frames if f is not None]
    return reduce(lambda l, r: l.merge(r, on="SEQN", how="left"), frames)


def build() -> pd.DataFrame:
    print(f"Building NHANES profiles (cycle={config.CYCLE})")
    row_counts: dict[str, int] = {}

    def _read(comp):
        df = io_xpt.try_read(comp)
        if df is not None:
            row_counts[comp] = len(df)
        return df

    demo = clean.clean_demo(_read("DEMO"))
    bp = clean.clean_bp(_read("BPXO"))
    biopro = clean.clean_biopro(_read("BIOPRO"))
    alb = clean.clean_alb_cr(_read("ALB_CR"))
    diq = clean.clean_diq(_read("DIQ"))
    bpq = clean.clean_bpq(_read("BPQ"))
    bmx = clean.clean_bmx(_read("BMX"))
    smq = clean.clean_smq(_read("SMQ"))
    tchol = clean.clean_tchol(_read("TCHOL"))
    hdl = clean.clean_hdl(_read("HDL"))
    ghb = clean.clean_ghb(_read("GHB"))

    # Meds: long RXQ_RX + optional lexicon -> class set + statin flag per SEQN.
    rxq = _read("RXQ_RX")
    lexicon = drug_class.load_lexicon()
    meds = drug_class.med_classes_by_seqn(rxq, lexicon)
    statins = drug_class.statin_use_by_seqn(rxq, lexicon)   # PREVENT input

    df = _merge([demo, bp, biopro, alb, diq, bpq, bmx, smq, tchol, hdl, ghb, meds, statins])
    df["statin_use"] = df["statin_use"].astype("boolean").fillna(False)  # not-on-statin default

    # ---- range gate FIRST, then derive from clean inputs ----------------------
    # (deriving before gating would let an implausible SBP/creatinine produce a
    # stage/eGFR that is then based on a value we delete.)
    df, violations = qa.apply_ranges(df)

    # ---- derive engine fields -------------------------------------------------
    df["egfr"] = derive.egfr_ckdepi_2021(df["creatinine"], df["age"], df["sex"])
    df["bp_stage"] = derive.bp_stage(df["sbp"], df["dbp"])
    df["diabetes"] = derive.resolve_diabetes(df)
    df["ckd_albuminuria"] = derive.ckd_albuminuria(df["egfr"], df["uacr"])
    df["contraindications"] = derive.contraindications(df)
    df["prevent_10yr"] = derive.prevent_10yr(df)
    df["med_classes"] = df["med_classes"].apply(
        lambda v: v if isinstance(v, list) else []
    )
    df["source"] = "nhanes"
    df["bp_context"] = "chronic"   # NHANES exam BP; MIMIC/eICU set office/admission

    # ---- cohort ---------------------------------------------------------------
    before = len(df)
    df = df[(df["age"] >= 18) & df["sbp"].notna()].copy()
    print(f"  cohort: {before} -> {len(df)} (adults with >=1 valid BP)")

    for c in PROFILE_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[PROFILE_COLUMNS]

    # Enforce the canonical contract before anything downstream consumes it.
    n_ok = validate.validate_profiles(df)
    print(f"  schema: {n_ok} profiles validate against patient_profile.schema.json")

    qa.write_report(df, violations, row_counts)
    return df


_LIST_COLUMNS = ["med_classes", "contraindications"]


def main() -> int:
    df = build()
    pq = config.PROCESSED / f"nhanes_profiles_{config.CYCLE}.parquet"
    csv = config.PROCESSED / f"nhanes_profiles_{config.CYCLE}.csv"
    try:
        df.to_parquet(pq, index=False)   # parquet preserves list dtype natively
        print(f"  wrote {pq}")
    except Exception as exc:  # pyarrow optional
        print(f"  parquet skipped ({exc}); csv still lossless via JSON encoding")
    # JSON-encode list columns so the CSV round-trips to real lists (json.loads),
    # not a lossy Python repr like "['thiazide']".
    csv_df = df.copy()
    for c in _LIST_COLUMNS:
        if c in csv_df.columns:
            csv_df[c] = csv_df[c].apply(
                lambda v: json.dumps(v if isinstance(v, list) else [])
            )
    csv_df.to_csv(csv, index=False)
    print(f"  wrote {csv}  ({len(df)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
