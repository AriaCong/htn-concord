"""Pick 50 index discharge summaries from the HTN-Concord MIMIC cohort (ages 30-79).

Stratified 25/25 on whether PREVENT is computable from structured data, so the check
covers both the complete-input and the naturally-missing case. No LLM is called.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]  # project root (PhD GenAI)
PROC = ROOT / "00_shared/data/mimic/processed"
OUT = Path(__file__).parent / "out"
SEED = 20260923

prof = pd.read_csv(PROC / "mimic_profiles_primary_prior_plus_index.csv", low_memory=False)
notes = pd.read_csv(PROC / "mimic_taskc_notes_prior_plus_index.csv", low_memory=False)

prof = prof[(prof.age >= 30) & (prof.age <= 79)]
cand = notes.merge(prof[["subject_id", "hadm_id", "age", "sex", "prevent_10yr"]],
                   on=["subject_id", "hadm_id"], how="inner")
cand["prevent_ok"] = cand.prevent_10yr.notna()
print("candidate notes:", len(cand), "| prevent computable:", int(cand.prevent_ok.sum()))

pick = pd.concat([
    cand[cand.prevent_ok].sample(25, random_state=SEED),
    cand[~cand.prevent_ok].sample(25, random_state=SEED),
])
pick.to_csv(OUT / "sample_notes.csv", index=False)
print("wrote", len(pick), "notes;", pick.subject_id.nunique(), "subjects")
