"""Configuration for the NHANES → PatientProfile cleaning pipeline.

The pipeline is parametrized by CYCLE so the same code runs on either the single
2017-2018 cycle (suffix ``_J``) or the pre-pandemic 2017-March-2020 pool (prefix
``P_``). Switch by setting the ``NHANES_CYCLE`` env var or editing ``CYCLE`` below.

Open decision (plan #1): "J" is the default for building/validating; flip to
"P_pre_pandemic" for the final, larger substrate. See README.
"""
from __future__ import annotations

import os
from pathlib import Path

import vocab
from pipelines.common.qa import Range

# ---------------------------------------------------------------------------
# Cycle selection
# ---------------------------------------------------------------------------
CYCLE = os.environ.get("NHANES_CYCLE", "J")  # "J" | "P_pre_pandemic"

# CDC's 2024 site redesign moved data files to this path (the old
# /Nchs/Nhanes/2017-2018/ path now returns an HTML "Page Not Found").
# Cycle J files live under Public/2017/DataFiles/ ; the pre-pandemic P_ pool
# lives under Public/2017/DataFiles/ as well (same folder, P_ prefix).
_BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles"
# RXQ_DRUG is a standalone multi-cycle lexicon hosted under the 1988 folder.
_DRUG_LEXICON_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/1988/DataFiles/RXQ_DRUG.xpt"

# Component-name -> base file stem (without cycle suffix/prefix or extension).
# The MEC weight column also differs by cycle and is resolved in weight_col().
_COMPONENTS = {
    "DEMO":     "DEMO",      # demographics
    "BPXO":     "BPXO",      # oscillometric blood pressure
    "BIOPRO":   "BIOPRO",    # standard biochemistry (creatinine, potassium)
    "ALB_CR":   "ALB_CR",    # albumin-creatinine ratio (UACR)
    "DIQ":      "DIQ",       # diabetes questionnaire
    "BPQ":      "BPQ",       # blood-pressure questionnaire
    "RXQ_RX":   "RXQ_RX",    # prescription medications (long, per-drug rows)
    "BMX":      "BMX",       # body measures (BMI)
    "SMQ":      "SMQ",       # smoking questionnaire
    "TCHOL":    "TCHOL",     # total cholesterol
    "HDL":      "HDL",       # HDL cholesterol
    "GHB":      "GHB",       # glycohemoglobin / HbA1c (optional, for PREVENT + dx)
}

# Standalone drug-ingredient lexicon used to map RXQ_RX drug IDs -> therapeutic
# class. NOT cycle-suffixed; verify the exact URL/extension before first fetch.
DRUG_LEXICON_STEM = "RXQ_DRUG"

# NCHS linked mortality (Task D) — fixed-width .dat, separate host/format.
MORTALITY_URL = (
    "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/"
    "linked_mortality/NHANES_2017_2018_MORT_2019_PUBLIC.dat"
)

# Optional components: pipeline runs (with warnings) if these are absent.
OPTIONAL = {"GHB"}


def _stem(component: str) -> str:
    """Return the cycle-specific file stem, e.g. DEMO -> 'DEMO_J' or 'P_DEMO'."""
    base = _COMPONENTS[component]
    if CYCLE == "J":
        return f"{base}_J"
    if CYCLE == "P_pre_pandemic":
        return f"P_{base}"
    raise ValueError(f"Unknown CYCLE {CYCLE!r}; expected 'J' or 'P_pre_pandemic'")


def file_url(component: str) -> str:
    """Full CDC download URL for a component's .xpt file in the current cycle."""
    return f"{_BASE_URL}/{_stem(component)}.xpt"


def file_registry() -> dict[str, str]:
    """component -> download URL for every table this pipeline consumes."""
    reg = {c: file_url(c) for c in _COMPONENTS}
    reg[DRUG_LEXICON_STEM] = _DRUG_LEXICON_URL
    return reg


def weight_col() -> str:
    """MEC exam weight column name for the selected cycle."""
    return "WTMEC2YR" if CYCLE == "J" else "WTMECPRP"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]          # .../htn-concord
DATA = ROOT / "data" / "nhanes"
# Raw .XPT files live in the user's shared Data folder (overridable via env).
# Defaults to <project>/Data/NHANES, resolved relative to this repo's parent.
RAW = Path(
    os.environ.get("NHANES_RAW_DIR", ROOT.parent / "Data" / "NHANES")
)
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
QA = DATA / "qa"
for _p in (RAW, INTERIM, PROCESSED, QA):
    _p.mkdir(parents=True, exist_ok=True)


def raw_path(component: str) -> Path:
    """Local path where a component's downloaded .XPT file lives (in RAW)."""
    stem = DRUG_LEXICON_STEM if component == DRUG_LEXICON_STEM else _stem(component)
    return RAW / f"{stem}.XPT"


# ---------------------------------------------------------------------------
# Plausibility ranges (values outside -> NA, logged by qa.py). See DATA dict §7.
# ---------------------------------------------------------------------------
RANGES: dict[str, Range] = {
    "sbp":        Range(60, 290),
    "dbp":        Range(30, 200),
    "creatinine": Range(0.1, 20),    # mg/dL
    "potassium":  Range(1.5, 9),     # mmol/L
    "age":        Range(0, 120),      # plausibility only; adult cohort (>=18) filtered separately
    "bmi":        Range(10, 90),
    "total_chol": Range(50, 600),    # mg/dL
    "hdl":        Range(5, 200),     # mg/dL
    "uacr":       Range(0, 30000),   # mg/g
}

# Questionnaire sentinels that mean "no data" -> NA.
REFUSED = 7
DONT_KNOW = 9

# Clinical thresholds + BP staging live in the shared vocab module (HC-3).
# Re-exported here for the pipeline's existing call sites; vocab is the source.
BP_THRESHOLDS = vocab.BP_THRESHOLDS
K_HYPERKALEMIA = vocab.K_HYPERKALEMIA
UACR_ALBUMINURIA = vocab.UACR_ALBUMINURIA
EGFR_CKD = vocab.EGFR_CKD
HBA1C_DIABETES = vocab.HBA1C_DIABETES
PREVENT_STAGE1_TREAT = vocab.PREVENT_STAGE1_TREAT
