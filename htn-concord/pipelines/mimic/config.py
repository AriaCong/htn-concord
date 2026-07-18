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
