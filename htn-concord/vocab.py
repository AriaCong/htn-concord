"""Shared controlled vocabulary (HC-3) — single source of truth for the whole system.

Both the data pipelines (`pipelines/*`) and the guideline engine (`engine/*`) import
from here so medication classes, comorbidity/contraindication flags, HTN ICD anchor
sets, and clinical thresholds can never drift between cleaning and labeling.

Pure module: no I/O, no pandas, no source-specific logic. Everything is scalar/string
so both a row-wise pipeline and the engine can call it.
"""
from __future__ import annotations

import re

# =============================================================================
# Medication classes
# =============================================================================
MED_CLASSES: tuple[str, ...] = (
    "thiazide", "acei", "arb", "dhp_ccb", "nondhp_ccb",
    "beta_blocker", "loop_diuretic", "mra", "alpha_blocker",
)
# 2025 AHA/ACC first-line antihypertensive classes (race-neutral).
FIRST_LINE_CLASSES: frozenset[str] = frozenset({"thiazide", "acei", "arb", "dhp_ccb"})

# NHANES/EHR combination pills arrive as one string of joined ingredients
# (e.g. "HYDROCHLOROTHIAZIDE; LISINOPRIL"). Split so every component classifies.
_DRUG_SEP = re.compile(r"[;/,+&]| and ", re.IGNORECASE)

# Exact/substring ingredient stems -> class. Specific stems only (no bare
# "pril"/"olol" substrings) to avoid false positives like prilocaine -> acei.
_DRUG_KEYWORD_CLASS: dict[str, str] = {
    "hydrochlorothiazide": "thiazide", "chlorthalidone": "thiazide",
    "indapamide": "thiazide", "metolazone": "thiazide", "chlorothiazide": "thiazide",
    "amlodipine": "dhp_ccb", "nifedipine": "dhp_ccb", "felodipine": "dhp_ccb",
    "nicardipine": "dhp_ccb", "isradipine": "dhp_ccb", "nisoldipine": "dhp_ccb",
    "diltiazem": "nondhp_ccb", "verapamil": "nondhp_ccb",
    "furosemide": "loop_diuretic", "bumetanide": "loop_diuretic", "torsemide": "loop_diuretic",
    "spironolactone": "mra", "eplerenone": "mra",
    "doxazosin": "alpha_blocker", "prazosin": "alpha_blocker", "terazosin": "alpha_blocker",
    "carvedilol": "beta_blocker", "labetalol": "beta_blocker",  # suffix rule misses these
}
# Token-suffix rules applied to each split token (avoid mid-word false matches).
_DRUG_SUFFIX_CLASS: dict[str, str] = {
    "pril": "acei",           # lisinopril, enalapril, ... (not prilocaine)
    "sartan": "arb",          # losartan, valsartan, ...
    "olol": "beta_blocker",   # metoprolol, atenolol, ...
}


def classify_drug(name: str | None) -> list[str]:
    """Sorted set of engine classes present in a drug string (handles combos)."""
    n = (name or "").lower()
    classes: set[str] = set()
    for tok in (t.strip() for t in _DRUG_SEP.split(n) if t.strip()):
        for kw, cls in _DRUG_KEYWORD_CLASS.items():
            if kw in tok:
                classes.add(cls)
        for suf, cls in _DRUG_SUFFIX_CLASS.items():
            if tok.endswith(suf):
                classes.add(cls)
    return sorted(classes)


def is_statin(name: str | None) -> bool:
    """Statins end in 'statin' (atorvastatin, rosuvastatin, ...). PREVENT input."""
    return "statin" in (name or "").lower()


# =============================================================================
# Comorbidity & contraindication flags
# =============================================================================
COMORBIDITY_FLAGS: tuple[str, ...] = ("diabetes", "ckd", "clinical_cvd")
CONTRAINDICATION_FLAGS: tuple[str, ...] = ("pregnancy", "angioedema_hx", "hyperkalemia")


# =============================================================================
# HTN ICD anchor sets (MIMIC cohort — used by HC-13/16/18)
# =============================================================================
# Anchor = essential HTN + HTN heart/kidney (anchor only; comorbidity derived
# from dx/labs, never from the anchor code itself).
HTN_ANCHOR_ICD9: frozenset[str] = frozenset({"4010", "4011", "4019", "402", "403", "404"})
HTN_ANCHOR_ICD10_PREFIXES: tuple[str, ...] = ("I10", "I11", "I12", "I13")
# Secondary HTN — out of primary-HTN scope, excluded.
HTN_SECONDARY_ICD9: frozenset[str] = frozenset({"405"})
HTN_SECONDARY_ICD10_PREFIXES: tuple[str, ...] = ("I15",)


def _norm_icd(code: str) -> str:
    """Normalize an ICD code for comparison: drop the dot, trim, upper-case
    (so 'I11.0', ' i110 ', 'I110' all compare equal)."""
    return (code or "").replace(".", "").strip().upper()


def is_htn_anchor(code: str, version: int | str) -> bool:
    """True if an ICD-9 or ICD-10 code is an HTN anchor (and not secondary)."""
    c = _norm_icd(code)
    if str(version) == "9":
        return any(c.startswith(a) for a in HTN_ANCHOR_ICD9) and not is_htn_secondary(code, version)
    return c.startswith(HTN_ANCHOR_ICD10_PREFIXES) and not is_htn_secondary(code, version)


def is_htn_secondary(code: str, version: int | str) -> bool:
    """True for *secondary* HTN codes (ICD-9 405 / ICD-10 I15), which are out of
    scope for this primary-HTN benchmark and must be excluded from the anchor set."""
    c = _norm_icd(code)
    if str(version) == "9":
        return any(c.startswith(s) for s in HTN_SECONDARY_ICD9)
    return c.startswith(HTN_SECONDARY_ICD10_PREFIXES)


# =============================================================================
# Clinical thresholds (2025 AHA/ACC)
# =============================================================================
K_HYPERKALEMIA = 5.5        # mmol/L -> avoid ACEI/ARB
UACR_ALBUMINURIA = 30       # mg/g   -> CKD w/ albuminuria
EGFR_CKD = 60               # mL/min/1.73m^2
HBA1C_DIABETES = 6.5        # %      -> lab-confirmed diabetes
PREVENT_STAGE1_TREAT = 7.5  # % 10-yr CVD risk -> treat Stage 1

# BP plausibility gate (global cleaning convention §4): readings outside these ranges
# are rejected to NA, never clipped. Shared so every source's BP parser (NHANES mean,
# MIMIC OMR) applies one range. Distinct from BP_THRESHOLDS, which are staging cutoffs.
SBP_MIN, SBP_MAX = 60, 290
DBP_MIN, DBP_MAX = 30, 200

# BP staging thresholds (unchanged from 2017).
BP_THRESHOLDS = {
    "elevated_sbp": 120,
    "stage1_sbp": 130, "stage1_dbp": 80,
    "stage2_sbp": 140, "stage2_dbp": 90,
}


def bp_stage_scalar(sbp: float | None, dbp: float | None) -> str | None:
    """Scalar 2025 AHA/ACC stage (higher of SBP/DBP category wins). None if unknown.

    The pipeline uses a vectorized version in derive.py built on these same
    thresholds; the engine uses this scalar form. Both share BP_THRESHOLDS.
    """
    if sbp is None or dbp is None or sbp != sbp or dbp != dbp:  # None or NaN
        return None
    t = BP_THRESHOLDS
    if sbp >= t["stage2_sbp"] or dbp >= t["stage2_dbp"]:
        return "stage2"
    if sbp >= t["stage1_sbp"] or dbp >= t["stage1_dbp"]:
        return "stage1"
    if sbp >= t["elevated_sbp"]:
        return "elevated"
    return "normal"
