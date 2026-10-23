#!/bin/zsh
# E0 (2026-09-23): build the A and B case sets from NHANES 2017-18.
# Needs ../htn-concord-main (read-only, for prevent.py and nhanes_profiles_J.csv) and 01_data/raw/NHANES/MCQ_J.XPT.
# Writes out/cases.jsonl, out/cohort_summary.json, out/pilot_seqns.txt (exclude these SEQNs from the formal study).
cd "${0:A:h}/../.."
uv run --no-project --with pandas --with numpy python build_cases.py
