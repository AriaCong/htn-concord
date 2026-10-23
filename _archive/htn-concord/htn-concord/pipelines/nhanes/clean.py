"""Per-component cleaning: raw NHANES tables -> tidy, one-row-per-SEQN frames.

Each function returns a frame keyed by SEQN with engine-facing column names. All
"refused/don't know" sentinels become NA; range checks live in qa.apply_ranges,
applied in build_profiles after merge so violations are logged in one place.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _na_sentinels(s: pd.Series) -> pd.Series:
    """Turn NHANES questionnaire "refused" (7) / "don't know" (9) codes into NA so
    they are treated as missing data, not as real answers."""
    return s.replace({config.REFUSED: pd.NA, config.DONT_KNOW: pd.NA})


def clean_demo(df: pd.DataFrame) -> pd.DataFrame:
    """DEMO -> demographics: age, sex, race/ethnicity, plus the survey design
    columns (weight, PSU, stratum) needed for population-weighted estimates."""
    out = pd.DataFrame({
        "SEQN": df["SEQN"],
        "age": df["RIDAGEYR"],            # 80 = topcoded "80+"
        "sex": df["RIAGENDR"].map({1: "male", 2: "female"}),
        "race_eth": df.get("RIDRETH3"),   # subgroup reporting only
        # RIDEXPRG (HC-96): 1 = pregnant, 2 = not pregnant, 3 = cannot ascertain.
        # Asked only of women 20-44, so <NA> is the norm and must stay three-valued:
        # mapping the absent majority to False would assert "not pregnant" about
        # people who were never asked. The engine reads this as a scope gate.
        "pregnant": (df["RIDEXPRG"].map({1: True, 2: False})
                     if "RIDEXPRG" in df else pd.Series(pd.NA, index=df.index)),
        config.weight_col(): df.get(config.weight_col()),
        "sdmvpsu": df.get("SDMVPSU"),
        "sdmvstra": df.get("SDMVSTRA"),
    })
    return out


def clean_bp(df: pd.DataFrame) -> pd.DataFrame:
    """Mean of available oscillometric readings 1-3; require >=1 valid pair."""
    sys_cols = [c for c in ("BPXOSY1", "BPXOSY2", "BPXOSY3") if c in df]
    dia_cols = [c for c in ("BPXODI1", "BPXODI2", "BPXODI3") if c in df]
    # Optional AHA convention: discard reading #1. Toggle here once, document it.
    discard_first = False
    if discard_first and len(sys_cols) > 1:
        sys_cols, dia_cols = sys_cols[1:], dia_cols[1:]
    sbp = df[sys_cols].mean(axis=1, skipna=True)
    dbp = df[dia_cols].mean(axis=1, skipna=True)
    n_valid = df[sys_cols].notna().sum(axis=1)
    out = pd.DataFrame({
        "SEQN": df["SEQN"],
        "sbp": sbp.where(n_valid >= 1),
        "dbp": dbp.where(n_valid >= 1),
        "bp_n_readings": n_valid,
    })
    return out


def clean_biopro(df: pd.DataFrame) -> pd.DataFrame:
    """BIOPRO -> biochemistry: serum creatinine (drives eGFR) and potassium
    (drives the hyperkalemia contraindication)."""
    return pd.DataFrame({
        "SEQN": df["SEQN"],
        "creatinine": df["LBXSCR"],   # mg/dL
        "potassium": df["LBXSKSI"],   # mmol/L (already SI)
    })


def clean_alb_cr(df: pd.DataFrame) -> pd.DataFrame:
    """ALB_CR -> urine albumin-creatinine ratio (UACR), the albuminuria marker
    used with eGFR to flag CKD."""
    return pd.DataFrame({
        "SEQN": df["SEQN"],
        "uacr": df["URDACT"],         # mg/g
    })


def clean_diq(df: pd.DataFrame) -> pd.DataFrame:
    """DIQ -> self-reported diabetes status (DIQ010), split into a definite-yes
    flag and a borderline flag, both preserving NA when the answer is unknown."""
    d = _na_sentinels(df["DIQ010"])
    na = d.isna()  # refused/don't-know/missing -> preserve NA so the engine can ABSTAIN
    return pd.DataFrame({
        "SEQN": df["SEQN"],
        # 1=Yes diabetic; 3=borderline -> not diabetic for Stage-1 trigger, kept separately
        "diabetes_self": d.eq(1).astype("boolean").mask(na),
        "diabetes_borderline": d.eq(3).astype("boolean").mask(na),
    })


def clean_bpq(df: pd.DataFrame) -> pd.DataFrame:
    """BPQ -> blood-pressure questionnaire: whether the person was ever told they
    have hypertension, and whether they are currently taking BP medication.

    'On BP meds' is skip-gated (only people told to take meds are asked the follow-up),
    so we reconstruct the true value below rather than blindly treating skips as NA."""
    told = _na_sentinels(df["BPQ020"]) if "BPQ020" in df else pd.Series(pd.NA, index=df.index)
    on_med = _na_sentinels(df["BPQ050A"]) if "BPQ050A" in df else pd.Series(pd.NA, index=df.index)

    # on_bp_meds is skip-gated: BPQ050A is asked only of those told to take meds.
    # Reconstruct the true value; only genuine refused/don't-know in-path stays NA
    # (blanket NA-preservation would wrongly abstain the untreated/undiagnosed).
    on = pd.Series(pd.NA, index=df.index, dtype="boolean")
    on[told.eq(2)] = False       # never told high BP -> not on BP meds
    if "BPQ040A" in df:
        told_take = _na_sentinels(df["BPQ040A"])
        on[told_take.eq(2)] = False   # told, but never advised to take meds
    on[on_med.eq(2)] = False     # advised, but not currently taking
    on[on_med.eq(1)] = True      # currently taking -> PREVENT treated-BP + intensify

    return pd.DataFrame({
        "SEQN": df["SEQN"],
        "told_hypertension": told.eq(1).astype("boolean").mask(told.isna()),
        "on_bp_meds": on,
    })


def clean_bmx(df: pd.DataFrame) -> pd.DataFrame:
    """BMX -> body-mass index (used in the PREVENT heart-failure model, not total CVD)."""
    return pd.DataFrame({"SEQN": df["SEQN"], "bmi": df["BMXBMI"]})


def clean_smq(df: pd.DataFrame) -> pd.DataFrame:
    """SMQ -> current-smoker flag (a PREVENT risk input).

    Also skip-gated: never-smokers are not asked the 'do you smoke now?' question, so
    we resolve them to non-smokers instead of leaving them NA."""
    # SMQ040 (now smoke) is skip-gated behind SMQ020 (ever smoked >=100 cigarettes):
    # never-smokers are not asked SMQ040 and are true non-smokers, not unknowns.
    ever = _na_sentinels(df["SMQ020"]) if "SMQ020" in df else pd.Series(pd.NA, index=df.index)
    now = _na_sentinels(df["SMQ040"]) if "SMQ040" in df else pd.Series(pd.NA, index=df.index)
    smoker = pd.Series(pd.NA, index=df.index, dtype="boolean")
    smoker[ever.eq(2)] = False       # never smoked >=100 -> non-smoker
    smoker[now.eq(3)] = False         # former smoker (not now)
    smoker[now.isin([1, 2])] = True   # every day / some days -> current
    return pd.DataFrame({"SEQN": df["SEQN"], "current_smoker": smoker})


def clean_tchol(df: pd.DataFrame) -> pd.DataFrame:
    """TCHOL -> total cholesterol (mg/dL); with HDL it gives non-HDL for PREVENT."""
    return pd.DataFrame({"SEQN": df["SEQN"], "total_chol": df["LBXTC"]})


def clean_hdl(df: pd.DataFrame) -> pd.DataFrame:
    """HDL -> HDL cholesterol (mg/dL), a PREVENT risk input."""
    return pd.DataFrame({"SEQN": df["SEQN"], "hdl": df["LBDHDD"]})


def clean_ghb(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """GHB -> HbA1c (%). Optional component: returns None if the file is absent,
    in which case diabetes falls back to self-report only."""
    if df is None:
        return None
    return pd.DataFrame({"SEQN": df["SEQN"], "hba1c": df["LBXGH"]})  # %
