# NHANES cleaning pipeline (HTN-Concord)

Turns raw NHANES files into one canonical **PatientProfile** row per respondent
(`SEQN`), the hidden structured label for Tasks A/B and the PREVENT/mortality
substrate. Companion spec: `docs/HTN-Concord_DataDictionary_and_CleaningStrategy.md`.

## Why 2017-2018 (cycle J)
Oscillometric BP (`BPXO`, the variables `BPXOSY1-3/BPXODI1-3` we use) was **introduced
in 2017-2018** — earlier cycles only have manual auscultatory `BPX`. 2017-2018 is also
the last complete cycle before NHANES was halted in March 2020, so the only larger
option is the **pre-pandemic pool** (2017-March 2020, `P_` prefix, `WTMECPRP` weights).
Set the cycle with the `NHANES_CYCLE` env var: `J` (default) or `P_pre_pandemic`.

## Tables consumed
DEMO, BPXO, BIOPRO, ALB_CR, DIQ, BPQ, RXQ_RX, **RXQ_DRUG** (drug-ID→class lexicon),
BMX, SMQ, TCHOL, HDL, **GHB** (HbA1c, optional). NCHS Linked Mortality File is Task D
(fetched separately; `mortality.py` TODO).

## Run
```bash
cd htn-concord
pip install -r requirements.txt

# 1. download raw .XPT into data/nhanes/raw/  (unblocks the pipeline)
python -m pipelines.nhanes.download

# 2. build profiles -> data/nhanes/processed/nhanes_profiles_J.csv (+ .parquet)
python -m pipelines.nhanes.build_profiles

# pooled pre-pandemic instead:
NHANES_CYCLE=P_pre_pandemic python -m pipelines.nhanes.download
NHANES_CYCLE=P_pre_pandemic python -m pipelines.nhanes.build_profiles
```
A QA report (row counts, missingness, range violations, BP-stage distribution) is
written to `data/nhanes/qa/` on every build.

## Module map
| File | Role |
|---|---|
| `config.py` | cycle selection, file registry/URLs, ranges, clinical thresholds |
| `download.py` | fetch `.XPT` from CDC (idempotent) |
| `io_xpt.py` | read `.XPT` → DataFrame |
| `clean.py` | per-component cleaning, sentinel→NA, one row per SEQN |
| `derive.py` | eGFR (CKD-EPI 2021), BP stage, diabetes, CKD/albuminuria, contraindications, PREVENT |
| `drug_class.py` | RXQ_RX (+RXQ_DRUG) → engine med-class set |
| `qa.py` | range gating + QA report |
| `build_profiles.py` | orchestration → processed PatientProfile table |

## Known TODOs (do not skip before labels)
1. **PREVENT coefficients** (`derive.prevent_10yr`) are *not* implemented — inputs are
   assembled but the Khan 2023 supplement coefficients must be transcribed. Until then
   Stage-1 initiation relies on clinical CVD/diabetes/CKD triggers only. **Do not
   fabricate coefficients** — a wrong PREVENT value corrupts the ≥7.5% initiation label.
2. **Mortality linkage** (`mortality.py`) — parse the fixed-width NCHS LMF `.dat`.
3. **Verify `RXQ_DRUG` URL/extension** and confirm `RXDDRUG` vs lexicon join for the cycle.
4. **Decide** the "discard BP reading #1" convention (`clean.clean_bp`, currently off).
5. ~~Not yet run against real data~~ — **run 2026-07-18**: 4,806 schema-valid adult profiles emitted from
   `Data/NHANES/` (13 `.XPT`). Re-run after the `bp_stage` / `ckd_albuminuria` fixes of the same date.
```
