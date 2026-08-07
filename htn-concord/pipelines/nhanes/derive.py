"""Derived clinical variables shared across all sources (see DATA dict §6).

These turn cleaned columns into engine inputs: eGFR (CKD-EPI 2021 race-free),
BP stage, diabetes resolution, CKD/albuminuria, contraindication flags, and the
PREVENT 10-year risk score. Computing them here (not per-source) keeps the
PatientProfile schema identical across NHANES / MIMIC / eICU.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipelines.common import prevent

from . import config


def egfr_ckdepi_2021(creatinine: pd.Series, age: pd.Series, sex: pd.Series) -> pd.Series:
    """CKD-EPI 2021 race-free creatinine equation (Inker et al., NEJM 2021).

    eGFR = 142 * min(Scr/k,1)^a * max(Scr/k,1)^-1.200 * 0.9938^age * (1.012 if female)
    k = 0.7 (F) / 0.9 (M); a = -0.241 (F) / -0.302 (M).
    """
    scr = pd.to_numeric(creatinine, errors="coerce")
    female = sex.eq("female")
    k = np.where(female, 0.7, 0.9)
    a = np.where(female, -0.241, -0.302)
    ratio = scr / k
    egfr = (
        142.0
        * np.minimum(ratio, 1.0) ** a
        * np.maximum(ratio, 1.0) ** -1.200
        * 0.9938 ** pd.to_numeric(age, errors="coerce")
        * np.where(female, 1.012, 1.0)
    )
    return pd.Series(egfr, index=creatinine.index).round(1)


def bp_stage(sbp: pd.Series, dbp: pd.Series) -> pd.Series:
    """2025 AHA/ACC categories (OR logic: higher of SBP/DBP category wins).

    Boundaries are half-open (``>=``) so non-integer BP means fall through cleanly.
    An earlier version used ``Series.between(130, 139)``, which voided any mean BP
    landing between the integer bounds (e.g. 139.5/79) to NA even though the reading
    was valid -- 56 of 4,806 NHANES rows. Because ``engine/`` stages independently via
    ``vocab.bp_stage_scalar``, that also made the profile column disagree with the
    engine. This now mirrors the scalar rule exactly; ``vocab`` remains the single
    source of truth for both thresholds and ordering. Fixed 2026-07-18.
    """
    t = config.BP_THRESHOLDS
    s = pd.to_numeric(sbp, errors="coerce")
    d = pd.to_numeric(dbp, errors="coerce")
    known = s.notna() & d.notna()
    stage2 = (s >= t["stage2_sbp"]) | (d >= t["stage2_dbp"])
    stage1 = (s >= t["stage1_sbp"]) | (d >= t["stage1_dbp"])
    elevated = s >= t["elevated_sbp"]
    stage = pd.Series(pd.NA, index=sbp.index, dtype="object")
    stage = stage.mask(known, "normal")
    stage = stage.mask(known & elevated, "elevated")
    stage = stage.mask(known & stage1, "stage1")
    stage = stage.mask(known & stage2, "stage2")  # most severe applied last
    return stage


def resolve_diabetes(df: pd.DataFrame) -> pd.Series:
    """Self-report OR lab-confirmed (HbA1c >= 6.5%) when GHB present."""
    self_dx = df.get("diabetes_self", pd.Series(pd.NA, index=df.index)).astype("boolean")
    if "hba1c" in df:
        a1c = pd.to_numeric(df["hba1c"], errors="coerce")
        lab = (a1c >= config.HBA1C_DIABETES).astype("boolean").mask(a1c.isna())
        # Kleene OR: True|NA=True, False|NA=NA, NA|NA=NA -> abstains only when truly unknown
        return self_dx | lab
    return self_dx


def ckd_albuminuria(egfr: pd.Series, uacr: pd.Series) -> pd.Series:
    """CKD: eGFR < 60 **OR** UACR >= 30 mg/g (KDIGO; matches the guideline's own
    "albuminuria >=30 mg/g or eGFR <60" phrasing -- it is an OR, not an AND).

    Kleene OR, matching ``resolve_diabetes``: True if either criterion is met;
    False only when *both* labs are present and both negative; NA otherwise. The
    previous ``.fillna(False)`` laundered "unknown" into "known-negative", which
    let the engine take the Stage-1 low-risk branch on patients whose kidney
    status was never measured -- the exact guess the ABSTAIN contract forbids.
    Fixed 2026-07-18.
    """
    e = pd.to_numeric(egfr, errors="coerce")
    u = pd.to_numeric(uacr, errors="coerce")
    low_egfr = (e < config.EGFR_CKD).astype("boolean").mask(e.isna())
    high_uacr = (u >= config.UACR_ALBUMINURIA).astype("boolean").mask(u.isna())
    return low_egfr | high_uacr


def contraindications(df: pd.DataFrame) -> pd.Series:
    """Set of engine contraindication flags per row (NHANES: K+ only reliably)."""
    k = pd.to_numeric(df.get("potassium"), errors="coerce")
    preg = df.get("pregnant")
    out = []
    for i in df.index:
        flags = []
        if pd.notna(k.get(i)) and k[i] >= config.K_HYPERKALEMIA:
            flags.append("hyperkalemia")
        # Pregnancy (HC-96), from DEMO.RIDEXPRG via clean_demo. Positive-only: only a
        # recorded pregnancy sets the flag, so "not ascertained" never reads as "not
        # pregnant". The engine treats this flag as a scope gate and abstains on it --
        # before HC-96 it was never read, and a pregnant Stage-2 row was labelled
        # INITIATE as ground truth. See DataDictionary S1 rule 2.
        # `is True` would be wrong here: a pandas row yields numpy.bool_(True), and
        # `numpy.bool_(True) is True` is False. notna() screens None/NaN so that an
        # unascertained pregnancy cannot read as either pregnant or not-pregnant.
        pv = None if preg is None else preg.get(i)
        if pv is not None and pd.notna(pv) and bool(pv):
            flags.append("pregnancy")
        # angioedema_hx is not ascertainable in NHANES -> exercised via the HC-95
        # contraindication stress set only (plan risk #4). Left empty rather than guessed.
        out.append(flags)
    return pd.Series(out, index=df.index)


def prevent_10yr(df: pd.DataFrame) -> pd.Series:
    """AHA PREVENT 10-year total-CVD risk % (Khan et al., Circulation 2024).

    Assembles inputs per row and delegates to the pure ``prevent`` module (HC-31:
    coefficients transcribed from Khan 2024 Table S12A and validated against its
    worked example). A value is NaN only when inputs are incomplete or age is
    outside 30-79 (PREVENT not validated there) — never a fabricated number, which
    would corrupt the Stage-1 (>=7.5%) initiation label. NaN here MUST be treated by
    the engine as "no PREVENT trigger / abstain", not as low risk.
    """
    required = ["age", "sex", "sbp", "total_chol", "hdl", "diabetes",
                "current_smoker", "egfr", "on_bp_meds", "statin_use"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  PREVENT: inputs missing {missing}; returning NaN column.")
        return pd.Series(np.nan, index=df.index, dtype="float64")

    def _row(r) -> float:
        def _b(v):
            return None if pd.isna(v) else bool(v)
        inp = prevent.PreventInputs(
            age=r["age"], sex=r["sex"],
            total_chol_mgdl=r["total_chol"], hdl_mgdl=r["hdl"],
            sbp=r["sbp"], on_bp_meds=_b(r["on_bp_meds"]),
            diabetes=_b(r["diabetes"]), current_smoker=_b(r["current_smoker"]),
            egfr=r["egfr"], statin=_b(r["statin_use"]),
        )
        val = prevent.prevent_10yr_cvd_risk(inp)
        return np.nan if val is None else val

    return df.apply(_row, axis=1).astype("float64")
