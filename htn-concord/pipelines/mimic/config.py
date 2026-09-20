"""Paths and cohort constants for the MIMIC-IV pipeline."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]                 # .../htn-concord
MIMIC_DIR = Path(os.environ.get("MIMIC_DIR", ROOT.parent / "Data" / "mimic-iv-3.1"))
HOSP = MIMIC_DIR / "hosp"
QA = ROOT / "data" / "mimic" / "qa"
QA.mkdir(parents=True, exist_ok=True)

# Chronic-BP cohort windows (architecture spec §2.2). Primary rule vs fallback.
WINDOW_PRIMARY_DAYS = 365
WINDOW_FALLBACK_DAYS = 730
MIN_READINGS_PRIMARY = 2      # distinct dates
MIN_READINGS_FALLBACK = 1

MIN_AGE = 18

# MIMIC-IV-ED 2.2 and MIMIC-IV-Note 2.2 ship as separate PhysioNet downloads and
# therefore separate directories. ED supplies medrecon -- the ONLY leakage-safe
# source of on_bp_meds. Note supplies the Task-C discharge summaries.
ED = Path(os.environ.get(
    "MIMIC_ED_DIR", MIMIC_DIR.parent / "mimic-iv-ed-2.2"
)) / "ed"
NOTE = Path(os.environ.get(
    "MIMIC_NOTE_DIR",
    MIMIC_DIR.parent / "mimic-iv-note-deidentified-free-text-clinical-notes-2.2",
)) / "note"

# labevents is 2.4 GB gzipped (~158M rows). ALWAYS filter by itemid inside a
# chunk loop; never load the table whole. Use `valuenum`, never `value`, which
# may hold the deid token "___".
#
# Multiple itemids per analyte because MIMIC carries duplicates across lab
# systems. O1: 51070 (UACR), 52546 and 52024 (creatinine) are UNVERIFIED --
# scripts/verify_mimic_itemids.py confirms they exist and carry the expected
# units before any use.
LAB_ITEMIDS: dict[str, tuple[int, ...]] = {
    "creatinine": (50912, 52546, 52024),   # mg/dL
    "potassium":  (50971,),                # mmol/L
    "uacr":       (51070,),                # mg/g -- without it CKD collapses to the eGFR limb
    "hba1c":      (50852,),                # %
    "total_chol": (50907,),                # mg/dL -- PREVENT
    "hdl":        (50904,),                # mg/dL -- PREVENT
}

# Labs bind STRICTLY BEFORE admittime (HC-27). A bidirectional "nearest lab"
# rule would let a value drawn DURING the admission set egfr and the
# hyperkalemia flag -- post-index leakage. 365 d matches the BP window: a
# two-year-old potassium must not set a contraindication.
LAB_LOOKBACK_DAYS = 365
LAB_LOOKBACK_SENSITIVITY_DAYS = 730

# Chunk size for the heavy labevents pass. Chunked pandas rather than DuckDB:
# no new dependency, one idiom across the codebase, and the Parquet cache in
# data/mimic/interim/ absorbs the cost of the slow single-threaded pass.
LAB_CHUNK_ROWS = 5_000_000

INTERIM = ROOT / "data" / "mimic" / "interim"
INTERIM.mkdir(parents=True, exist_ok=True)
