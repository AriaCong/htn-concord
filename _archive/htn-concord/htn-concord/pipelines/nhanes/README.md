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
NHANES-specific (this package):

| File | Role |
|---|---|
| `config.py` | cycle selection, file registry/URLs, range *values*, clinical thresholds |
| `download.py` | fetch `.XPT` from CDC (idempotent) |
| `io_xpt.py` | read `.XPT` → DataFrame |
| `clean.py` | per-component cleaning, sentinel→NA, one row per SEQN |
| `drug_class.py` | RXQ_RX (+RXQ_DRUG) → engine med-class set |
| `build_profiles.py` | orchestration → processed PatientProfile table |

Source-agnostic (`pipelines/common/`, extracted by HC-97 — **do not re-implement
any of it here**; MIMIC and eICU import the same modules, and a second copy is how
HC-8 silently mis-staged 56 rows):

| File | Role |
|---|---|
| `derive.py` | eGFR (CKD-EPI 2021), BP stage, diabetes, CKD/albuminuria, contraindications, PREVENT. Thresholds from `vocab` |
| `prevent.py` | PREVENT 10-yr total-CVD model (Khan 2024 Table S12A) |
| `qa.py` | range gating (reject to NA, never clip) + QA report writer; ranges and output path are parameters |
| `validate.py` | `patient_profile.schema.json` enforcement |

## Known TODOs (do not skip before labels)
1. ~~**PREVENT coefficients** are not implemented~~ — **done (HC-31)**. Transcribed from
   Khan 2024 Supplemental Table S12A and validated against that table's worked example
   (women 14.684%, men 16.317%) in `tests/test_prevent.py`. The standing rule holds:
   **never fabricate a coefficient** — a wrong PREVENT value corrupts the ≥7.5%
   initiation label, and `None`/NaN must read as "abstain", never as "low risk".
2. **Mortality linkage** (`mortality.py`) — parse the fixed-width NCHS LMF `.dat`.
3. **Verify `RXQ_DRUG` URL/extension** and confirm `RXDDRUG` vs lexicon join for the cycle.
4. **Decide** the "discard BP reading #1" convention (`clean.clean_bp`, currently off).
5. ~~Not yet run against real data~~ — **run 2026-07-18**: 4,806 schema-valid adult profiles emitted from
   `Data/NHANES/` (13 `.XPT`). Re-run after the `bp_stage` / `ckd_albuminuria` fixes of the same date.
```
