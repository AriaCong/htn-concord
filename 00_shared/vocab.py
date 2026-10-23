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


# =============================================================================
# Therapeutic-class strings (MIMIC-IV-ED `medrecon.etcdescription`)
# =============================================================================
# medrecon carries a therapeutic-class string beside each drug name. It adds
# recall over the ingredient-name rules above, which miss agents whose names fit
# no keyword or suffix pattern.
#
# MATCHING IS EXACT, DELIBERATELY. Substring matching on this vocabulary is a
# trap with real numbers behind it: "Beta" also matches
# "Asthma/COPD Therapy - Beta 2-Adrenergic Agents, Inhaled" (~57k rows, an
# inhaler) and "Aminopenicillin Antibiotic - Beta-lactamase Inhibitor
# Combinations"; "Calcium Channel" also matches an analgesic; "Calcium" matches
# antacids and vitamin D; and several "Ophthalmic - Beta blockers-..." classes
# are glaucoma eye drops, not systemic antihypertensives. Exact match means an
# unrecognised or newly added class maps to nothing -- which is the conservative
# default, and the ingredient-name route usually catches it anyway.
#
# Deliberately ABSENT, because MED_CLASSES cannot express them. Each is a real
# antihypertensive that this benchmark therefore cannot see, which understates
# `med_classes` for those patients. Flagged for HC-49:
#   * "Renin Inhibitor, Direct" (aliskiren)
#   * "Central Alpha-2 Receptor Agonists" (clonidine, methyldopa) -- NOT
#     alpha_blocker, which means alpha-1 antagonists
#   * "Direct Acting Vasodilators" (hydralazine, minoxidil)
#   * "Diuretic - Potassium Sparing" (amiloride, triamterene) -- NOT mra, which
#     means aldosterone antagonists specifically
ETC_DESCRIPTION_CLASS: dict[str, tuple[str, ...]] = {
    # --- RAAS ---------------------------------------------------------------
    "ACE Inhibitors": ("acei",),
    "ACE Inhibitor and Diuretic Combinations": ("acei", "thiazide"),
    "ACE Inhibitor and Calcium Channel Blocker Combinations": ("acei", "dhp_ccb"),
    "Angiotensin II Receptor Blockers (ARBs)": ("arb",),
    "Angiotensin II Receptor Blocker (ARB)-Diuretic Combinations": ("arb", "thiazide"),
    "Angiotensin II Receptor Blocker (ARB)-Calcium Channel Blocker Comb.": ("arb", "dhp_ccb"),
    "Angiotensin II Receptor Blocker (ARB)-Calcium Channel Blocker-Diuretic":
        ("arb", "dhp_ccb", "thiazide"),
    "Angiotensin II Receptor Blocker-Neprilysin Inhibitor Comb. (ARNi)": ("arb",),
    # --- Beta blockers ------------------------------------------------------
    "Beta Blockers Cardiac Selective": ("beta_blocker",),
    "Beta Blockers Cardiac Selective, Intrinsic Sympathomimetic Activity": ("beta_blocker",),
    "Beta Blockers Non-Cardiac Selective": ("beta_blocker",),
    "Beta Blockers Non-Cardiac Select., Intrinsic Sympathomimetic Activity": ("beta_blocker",),
    "Alpha-Beta Blockers": ("beta_blocker",),
    "Cardiac Selective Beta Blocker-Thiazide Diuretic and Related Comb.":
        ("beta_blocker", "thiazide"),
    "Non-Cardiac Selective Beta Blocker-Thiazide Diuretic and Related Comb.":
        ("beta_blocker", "thiazide"),
    # --- Calcium channel blockers -------------------------------------------
    "Calcium Channel Blockers - Dihydropyridines": ("dhp_ccb",),
    "Calcium Channel Blockers - Dihydropyridines - Cerebrovascular Specific": ("dhp_ccb",),
    "Calcium Channel Blockers - Benzothiazepines": ("nondhp_ccb",),      # diltiazem
    "Calcium Channel Blockers - Phenylakylamines": ("nondhp_ccb",),      # verapamil
    "Antihyperlipidemic HMG CoA Reduct Inhib and Calcium Channel Blocker": ("dhp_ccb",),
    # --- Diuretics ----------------------------------------------------------
    "Diuretic - Thiazides and Related": ("thiazide",),
    "Diuretic - Potassium Sparing-Thiazide and Related Combinations": ("thiazide",),
    "Central Alpha-2 Agonists-Thiazide Diuretic and Related Comb.": ("thiazide",),
    "Diuretic - Loop": ("loop_diuretic",),
    "Aldosterone Receptor Antagonists": ("mra",),
    "Diuretic - Aldosterone Receptor Antagonist, Non-selective": ("mra",),
    "Diuretic - Aldosterone Receptor Antagonist, Selective": ("mra",),
    # --- Alpha blockers -----------------------------------------------------
    # Peripheral alpha-1 antagonists only. The "Prostatic Hypertrophy Agent"
    # class is deliberately absent: tamsulosin is uroselective and is not a
    # blood-pressure drug. Doxazosin and terazosin are still picked up by the
    # ingredient-name route, exactly as they are in NHANES -- keeping the two
    # arms consistent matters more here than adjudicating indication.
    "Peripheral Alpha-1 Receptor Blockers": ("alpha_blocker",),
}

# Statins, by therapeutic class (PREVENT input). Same exact-match discipline.
ETC_DESCRIPTION_STATIN: frozenset[str] = frozenset({
    "Antihyperlipidemic - HMG CoA Reductase Inhibitors (statins)",
    "Antihyperlipidemic HMG CoA Reduct Inhib and Calcium Channel Blocker",
})


def classify_etc_description(desc: str | None) -> list[str]:
    """Sorted engine classes for a medrecon therapeutic-class string.

    Exact match only -- see ETC_DESCRIPTION_CLASS for why. Unknown strings
    return [] rather than guessing.
    """
    if not isinstance(desc, str):
        return []
    return sorted(ETC_DESCRIPTION_CLASS.get(desc.strip(), ()))


def is_statin_etc_description(desc: str | None) -> bool:
    """Statin by therapeutic class, complementing the ingredient-name rule."""
    if not isinstance(desc, str):
        return False
    return desc.strip() in ETC_DESCRIPTION_STATIN


def is_statin(name: str | None) -> bool:
    """Statins end in 'statin' (atorvastatin, rosuvastatin, ...). PREVENT input."""
    return "statin" in (name or "").lower()


# =============================================================================
# Comorbidity & contraindication flags
# =============================================================================
COMORBIDITY_FLAGS: tuple[str, ...] = ("diabetes", "ckd", "clinical_cvd")
CONTRAINDICATION_FLAGS: tuple[str, ...] = ("pregnancy", "angioedema_hx", "hyperkalemia")

# Contraindication flag -> med classes that must NOT be recommended (HC-70 scoring,
# and the exclusion half of HC-36). Transcribed from the Master Plan Phase-3
# contraindication spec as corrected by the 2026-07-18 cardiology review. It lives
# here rather than in the evaluator so scoring and rule selection cannot drift: if
# they disagreed, a model could be scored `unsafe_recommendation` for a class the
# engine itself would go on to recommend.
#
# Two transcription details that are correctness, not pedantry:
#
# * **Pregnancy excludes `mra`, `acei`, `arb` -- not `beta_blocker`.** The spec
#   excludes *atenolol specifically*, and says so in those words, because labetalol
#   is a beta-blocker and a preferred agent in pregnancy. `MED_CLASSES` has no
#   drug-level granularity, so excluding the class would score a correct answer as
#   unsafe. Documented as a known limitation instead: within-class distinctions are
#   invisible to this metric. Direct renin inhibitors are likewise absent from
#   `MED_CLASSES` and so cannot be expressed here.
# * **Angioedema excludes `arb` as well as `acei`** (cross-reactivity ~2-10%). An
#   earlier version of the spec omitted the ARB consequence.
#
# Hyperkalemia here means the flag as derived at K+ >= K_HYPERKALEMIA (5.5). The
# 5.0-5.4 band is deliberately NOT a contraindication -- flagging it would score
# correct model answers as unsafe.
CONTRAINDICATED_CLASSES: dict[str, frozenset[str]] = {
    "pregnancy":     frozenset({"acei", "arb", "mra"}),
    "angioedema_hx": frozenset({"acei", "arb"}),
    "hyperkalemia":  frozenset({"acei", "arb", "mra"}),
}


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
