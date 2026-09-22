# HTN-Concord — Data Dictionary & Cleaning Strategy (v1)

Scope: adult **primary (essential) hypertension**, initiation + intensification, plus high-value
contraindications (pregnancy, angioedema history, hyperkalemia K⁺ ≥5.5 mmol/L). **Reduced eGFR is *not* a
contraindication** — the guideline *prefers* ACEI/ARB at eGFR <60; it is a comorbidity modifier plus a
monitoring requirement (corrected 2026-07-18). This document lists every table used, defines the
variables that feed the Deterministic Guideline Engine, and specifies how each source is cleaned into a
canonical `PatientProfile`.

Prepared 2026-07-08. Aligned with the Notion *🇬🇧 HTN-Concord — Master Plan (English)* hub (the page formerly
titled "Consolidated Plan") and the 2025 AHA/ACC guideline (DOI 10.1161/HYP.0000000000000249).
Chinese counterpart: `HTN-Concord_DataDictionary_and_CleaningStrategy_zh.md` — **update both together.**

> 📘 **Companion document.** This file is the *reference* — every table across all four datasets, plus
> the correction history. For a single-substrate **walkthrough** covering why each column was chosen,
> the three-layer data-type contract, the missing-data policy (and why we do not impute), and the
> step-by-step NHANES execution order, see `HTN-Concord_DataProcessing_Walkthrough.md`
> (Chinese: `..._Walkthrough_zh.md`).

---

## 0. Status of the data (read first)

| Source | Local? | Location | Note |
|---|---|---|---|
| **NHANES 2017–2018 (cycle J)** | ✅ | `Data/NHANES/` | 13 `.XPT` files. Pipeline built **and run**: 4,806 schema-valid adult profiles + QA report. See §1. **Gap: `MCQ_J` is NOT downloaded** — it is the source of `clinical_cvd` (a Stage-1 initiation trigger), which is therefore null for every NHANES row. |
| MIMIC-IV 3.1 (hosp + icu) | ✅ | `Data/mimic-iv-3.1/` | gzip CSV |
| MIMIC-IV-Note 2.2 | ✅ | `Data/mimic-iv-note.../note/` | `discharge.csv.gz` = 1.1 GB |
| MIMIC-IV-ED 2.2 | ✅ | `Data/mimic-iv-ed-2.2/ed/` | gzip CSV |
| eICU-CRD 2.0 | ✅ | `Data/eicu-collaborative-research-database-2.0/` | plain CSV |

**Datasets → tasks:** NHANES → Task A/B + PREVENT + mortality (Task D). MIMIC-IV(+ED+Note) → Task B/C
+ `dod` plausibility. eICU → **descoped 2026-07-18** to a ~500-stay abstention-calibration probe (every eICU
BP is acute, so a full pipeline would emit ~200k rows carrying no decision label).

> ⚠️ **eICU "no notes" was factually wrong.** eICU ships a 306 MB `note.csv`. The conclusion survives — the
> content is path/value fragments, not narrative prose, so it is still unsuitable for Task C — but the
> premise was false wherever this document asserted it (corrected 2026-07-18).

---

## 1. NHANES 2017–2018 (cycle `_J`) — PRIMARY

Files are SAS `.XPT`; one row per respondent keyed by **`SEQN`**. Open decision in the plan: use cycle **J
only** vs pool the pre-pandemic **`P_` (2017–Mar 2020)** files (`P_` variables share names but the join key
and weights differ — do not mix J and P_ in one frame). Recommendation below assumes **J**; switch every
`*_J` to `P_*` and use `WTMECPRP` weights if pooling.

### Tables & variables used

| File (`_J`) | Variable | Meaning | Units / codes |
|---|---|---|---|
| **DEMO_J** | `SEQN` | Respondent ID (join key, all files) | int |
| | `RIDAGEYR` | Age at screening | years; **80 = topcoded "80+"** |
| | `RIAGENDR` | Sex | 1=Male, 2=Female |
| | `RIDRETH3` | Race/ethnicity | for **subgroup reporting only** — engine is race-neutral |
| | `WTMEC2YR`, `SDMVPSU`, `SDMVSTRA` | MEC weight, PSU, stratum | for survey-weighted prevalence / mortality |
| **BPXO_J** | `BPXOSY1–3` | Systolic BP, oscillometric, reads 1–3 | mmHg |
| | `BPXODI1–3` | Diastolic BP, reads 1–3 | mmHg |
| **BIOPRO_J** | `LBXSCR` | Serum creatinine | mg/dL |
| | `LBXSKSI` | Serum potassium | **mmol/L (SI)** |
| **ALB_CR_J** | `URDACT` | Urine albumin-creatinine ratio (UACR) | mg/g |
| | `URXUMA`,`URXUCR` | urine albumin, urine creatinine | source of UACR |
| **DIQ_J** | `DIQ010` | "Doctor told you have diabetes" | 1=Yes,2=No,3=Borderline,7=Refused,9=Don't know |
| **BPQ_J** | `BPQ020` | Ever told high BP | 1/2/7/9 |
| | `BPQ030` | Told high BP ≥2 times | 1/2/7/9 |
| | `BPQ040A` | Told to take BP medication | 1/2/7/9 |
| | `BPQ050A` | **Now taking** BP medication | 1/2/7/9 |
| **RXQ_RX_J** | `RXDDRUG`,`RXDDRGID` | drug name / generic ID | long format, many rows per `SEQN` |
| | `RXDCOUNT` | number of Rx | int |
| **BMX_J** | `BMXBMI` | Body mass index | kg/m² |
| **SMQ_J** | `SMQ020` | Smoked ≥100 cigarettes in life | 1/2 |
| | `SMQ040` | Now smoke | 1=every day,2=some days,3=not at all |
| **TCHOL_J** | `LBXTC` | Total cholesterol | mg/dL |
| **HDL_J** | `LBDHDD` | HDL cholesterol | mg/dL |
| **NCHS LMF** | `MORTSTAT`,`PERMTH_EXM`,`UCOD_LEADING` | mortality status, person-months, cause | Task D only |
| **GHB_J** | `LBXGH` | HbA1c (%) | lab limb of the diabetes flag (≥6.5%); **was missing from this table** though the pipeline consumes it |
| **RXQ_DRUG** | `RXDDRGID`,`RXDDRGNM` | drug-info lookup | joined to `RXQ_RX_J` for drug→class; **was missing from this table** |
| **DEMO_J** | `RIDEXPRG` | Pregnancy status | 1 = pregnant, 2 = not, 3 = cannot ascertain. ✅ **Wired 2026-07-19 (HC-24)** → `pregnant` → `contraindications`; see cleaning rule 2 |
| **MCQ_J** ⚠️ | `MCQ160B–F` | CHF / CHD / angina / MI / stroke | **NOT DOWNLOADED.** Sole source of `clinical_cvd`; until added, that trigger is null for every NHANES row |

### Cleaning rules — NHANES
1. **Missing sentinels.** Questionnaire `7`/`9` (refused / don't know) → `NA`. Never treat as data.
   Lab/BP blanks stay `NA`.
2. **Cohort filter.** `RIDAGEYR ≥ 18` **and** ≥1 non-null oscillometric reading.
   **Pregnancy (corrected 2026-07-18):** pregnancy **is** ascertainable in NHANES — `DEMO_J.RIDEXPRG`
   (1 = pregnant), 55 respondents, **45 of whom are currently in the emitted profile table with an empty
   `contraindications` list**. The old text pointed at `RHQ*` (not on disk, not needed) and `derive.py`
   wrongly asserted pregnancy was unascertainable. This is a *safety* gap, not a cosmetic one: once HC-36
   lands, the engine could emit "initiate ACEI/ARB" for a pregnant patient **as ground truth** — the exact
   thing `unsafe_recommendation` is meant to catch. Required: read `RIDEXPRG`, set the `pregnancy` flag,
   and — since hypertensive pregnancy management is out of scope — have the engine **ABSTAIN**
   (`pregnancy_management_out_of_scope`) while still emitting the flag for contraindication scoring.
   ✅ **Done 2026-07-19 (HC-24, PR #5) exactly as specified above.** `clean_demo` carries `pregnant`
   from `RIDEXPRG` and keeps it **three-valued**: the question is asked only of women 20–44, so `<NA>`
   is the norm and mapping the absent majority to `False` would assert "not pregnant" about people who
   were never asked. `derive.contraindications()` reads it positive-only. The engine applies it as a
   **scope gate placed before staging**, so the abstention does not depend on BP — all 45 pregnant
   profiles now abstain, where 129 of their 135 rendered cases previously scored `lifestyle_only`.
   Anchor: `HTN-CONCORD:abstain-out-of-scope`. Drug-class consequences remain **HC-36**; the remaining
   out-of-scope guards (resistant/secondary HTN, ESRD, hypertensive emergency) remain **HC-28**.
3. **BP summarization — use the MEAN (HC-23 resolved 2026-08-08).** Require ≥1 valid pair. Range-check
   SBP 60–290, DBP 30–200; implausible → `NA` (never clipped).
   > ✅ **HC-23 resolved against the guideline source — the code was right and the documents were wrong.**
   > This section previously instructed *median everywhere*, harmonized 2026-07-18, and flagged
   > `pipelines/nhanes/clean.py` as non-compliant for computing the mean. Checked against
   > `docs/guidelines/jones-et-al-2025-*` (2025 AHA/ACC, DOI `10.1161/HYP.0000000000000249`), the finding
   > inverts: the guideline specifies **the average** throughout — *"Office BP should be based on the
   > average of available readings"*, §5.2.7 *"an average of ≥2 readings at ≥2 visits"*, and the staging
   > thresholds are stated as *"an average of SBP ≥130 mm Hg"*. The token "median" occurs once in the
   > whole guideline, in an unrelated passage on weight regain.
   >
   > The 2026-07-18 rationale argued for *harmonization* and then concluded *median*, which does not
   > follow — mean harmonizes identically. The one median-specific argument, robustness to MIMIC's
   > irregular right-skewed OMR reading counts, is an engineering concern that would make the engine
   > deviate from the guideline on `bp_stage`, the most load-bearing input in the pipeline. It is handled
   > instead by the range gates, the MIMIC ≥2-distinct-dates requirement, and a **median sensitivity
   > analysis** reported alongside the discard-reading-#1 sensitivity.
   >
   > **No re-emission, no figure moves.** The shipped `nhanes_profiles_J.csv` was always guideline-correct,
   > and MIMIC uses the mean too, so the two arms agree. Like every encoded rule, the averaging rule is
   > still in scope for HC-49 clinician face-validation.
   >
   > **Known limitation, unaffected by this:** NHANES is a single-visit protocol, so it satisfies "average
   > of ≥2 readings" but not "at ≥2 visits" — already documented as slight over-triggering on Stage-1.
   *Still open — must be settled before the benchmark freeze:* whether to **discard reading #1**. The flag
   already exists (`clean.py`, `discard_first=False`). Discarding costs almost no sample (only 10 rows have a
   single reading) and the first oscillometric reading runs high, so retaining it inflates Stage 1/2 and
   therefore the initiation label. Report a stage-distribution sensitivity table under both settings.
4. **Stage** (engine input, computed after cleaning): Elevated 120–129/<80; **Stage 1 130–139 or 80–89**;
   **Stage 2 ≥140 or ≥90**. Use the **mean** SBP/DBP (per §3 above; HC-23 resolved 2026-08-08).
5. **eGFR:** derive with **CKD-EPI 2021 race-free** from `LBXSCR`, age, sex (see §6). Do not use any
   race-based equation.
6. **Potassium** is already SI (mmol/L) — no conversion; contraindication flag `K⁺ ≥ 5.5`.
7. **CKD (corrected 2026-07-18 — it is an OR, not an AND).** CKD = **eGFR <60 mL/min/1.73 m² *OR*
   UACR ≥30 mg/g** (KDIGO, and the guideline's own phrasing: *"albuminuria ≥30 mg/g **or** eGFR <60"*). This
   single definition drives both the Stage-1 initiation trigger and the ACEI/ARB preference modifier (HC-35).
   The code was always a correct OR; the field name `ckd_albuminuria` and the "CKD **with** albuminuria" prose
   both implied an AND and should be read as `ckd`. Missing labs → **`NA`, never `False`** (Kleene OR).
8. **Diabetes flag:** `DIQ010==1`. Borderline (3) → not diabetic for the Stage-1-initiation trigger, but
   record separately.
9. **On-treatment flag:** `BPQ050A==1` (currently taking BP meds) — needed for PREVENT (`treated BP`) and
   for initiate-vs-intensify.
10. **Meds → class:** `RXQ_RX_J` is long; map `RXDDRGID`→ATC/therapeutic class via the NHANES drug-info
    file, collapse to engine classes (thiazide/ACEI/ARB/DHP-CCB/other). Pivot to one row per `SEQN` with a
    class set.
11. **Smoking (PREVENT):** current smoker = `SMQ040 ∈ {1,2}`.
12. **Join:** left-join all `_J` files to `DEMO_J` on `SEQN`; result = one `PatientProfile` per respondent.
13. **Survey design:** keep `WTMEC2YR/SDMVPSU/SDMVSTRA` on the frame; only apply for population-level
    estimates, **not** for per-vignette labels.

---

## 2. MIMIC-IV 3.1 — PRIMARY real-EHR (Tasks B & C, mortality)

Keys: `subject_id` (patient), `hadm_id` (hospital admission). Times are deidentified/date-shifted per
patient (year shifted, intervals preserved). `hosp/*` = hospital-wide; `icu/*` not on the HTN main line.

### Tables & variables used

| Table | Variable | Meaning | Notes for cleaning |
|---|---|---|---|
| **hosp/omr** | `subject_id`,`chartdate`,`seq_num`,`result_name`,`result_value` | Outpatient measurements | `result_name="Blood Pressure"` → `result_value` is a **`"SYS/DIA"` string**; also *Sitting/Standing/Lying* variants. `eGFR` present but sparse (≈279 rows) → derive instead. Weight(Lbs)/Height(Inches)/BMI here too. |
| **hosp/labevents** | `subject_id`,`hadm_id`,`itemid`,`charttime`,`valuenum`,`valueuom`,`ref_range_*`,`flag` | Labs | **Creatinine `itemid=50912`, Potassium `itemid=50971`** (per plan). `value` may be `"___"` (deid) → use `valuenum`. Filter by `itemid` first (table is 2.4 GB). |
| **hosp/d_labitems** | `itemid`,`label`,`fluid`,`category` | Lab dictionary | join to confirm itemids/units |
| **hosp/prescriptions** | `subject_id`,`hadm_id`,`drug`,`starttime`,`stoptime`,`route`,`dose_val_rx` | Inpatient meds | drug→class mapping; free-text `drug` names |
| **hosp/diagnoses_icd** | `subject_id`,`hadm_id`,`seq_num`,`icd_code`,`icd_version` | Coded dx | **mixed ICD-9 (`version=9`) and ICD-10 (`10`)** → must map both. HTN silver label + comorbidities. |
| **hosp/d_icd_diagnoses** | `icd_code`,`icd_version`,`long_title` | Dx dictionary | human-readable labels |
| **hosp/patients** | `subject_id`,`gender`,`anchor_age`,`anchor_year`,`anchor_year_group`,`dod` | Demographics + death | **`anchor_age`; age 89+ topcoded to 91**. `dod` = date of death (Task D). |
| **hosp/admissions** | `subject_id`,`hadm_id`,`admittime`,`dischtime`,`deathtime`,`race`,`insurance`,`hospital_expire_flag` | Admission-level | `hospital_expire_flag` in-hospital death; index-encounter selection. |
| **note/discharge** | `note_id`,`subject_id`,`hadm_id`,`charttime`,`text` | Free-text discharge summary | Task-C input; median ~10k chars; deid placeholders `___`. |

### Cleaning rules — MIMIC-IV
1. **Cohort (anchor code set — must match `vocab.py`):** adults with an **HTN anchor ICD** — ICD-9
   `4010`/`4011`/`4019` (+`402–404`, anchor-only) or ICD-10 `I10`, `I11–I13` — **and/or** ≥1 `omr` BP.
   **EXCLUDE ICD-9 `405` and ICD-10 `I15*` (secondary hypertension, out of scope).** The shipped code
   already excludes them (`vocab.HTN_SECONDARY_ICD10_PREFIXES`); an earlier version of this line wrongly
   listed `I15*` as *included*. Corrected 2026-07-18.
2. **Index-encounter rule (open decision — pick one & document):** e.g. first admission with an HTN dx
   that also has a discharge summary; keep 1 row per `subject_id`. Record the rule in code.
3. **OMR BP parsing:** split `result_value` on `/` → `sbp_omr`,`dbp_omr` (int). Keep only `result_name`
   starting with "Blood Pressure"; retain posture as a column. Range-check as in NHANES. This is the
   **chronic/outpatient** BP source.
4. **Context gate (Task C):** ICU/inpatient BP (chartevents/triage) → `context="admission"` → **engine
   abstains** on staging; only `omr` outpatient BP drives chronic staging. Enforce this flag on every BP row.
5. **Labs:** subset `labevents` to `itemid ∈ {50912, 50971}` **before** loading; use `valuenum` (ignore
   `"___"`); drop rows where `valuenum` is null. **Take the most recent value STRICTLY BEFORE `admittime`,
   within a pre-registered lookback window** — corrected 2026-07-18. The old wording ("nearest the index
   encounter") is bidirectional and would let a creatinine or potassium drawn *during* the index admission —
   i.e. after the decision, plausibly reflecting the treatment being evaluated — set `egfr` and the
   hyperkalemia flag. That is post-index leakage and contradicts the plan's own rule that comorbidities be
   time-bounded before `admittime`. Derive eGFR from creatinine (§6). Potassium already mmol/L
   (`valueuom` check). **Also verify creatinine itemid coverage** — `52546` ("Creatinine, Blood") and `52024`
   ("Creatinine, Whole Blood") exist alongside `50912`. **Missing: UACR** — `itemid 51070`
   ("Albumin/Creatinine, Urine"); without it MIMIC `ckd` collapses to the eGFR limb only and HC-35 under-fires.
6. **Diagnoses:** normalize ICD-9 vs ICD-10 with a single crosswalk to comorbidity flags
   (diabetes, CKD, angioedema history, pregnancy). Angioedema hx (ICD-10 `T78.3*`, `D84.1`) sets the
   ACEI-avoid flag — this is a key contraindication the benchmark targets.
7. **Meds → home-med list:** prefer **ED `medrecon`** (§3) for *home* meds; `prescriptions` is inpatient
   and noisier. Map `drug`→ engine class.
8. **Silver labels (Task C):** HTN status & facts derived from `diagnoses_icd` + `labevents` + `medrecon`,
   **not** from notes. Validate a hand sample (plan risk #3). This tests extraction fidelity, not concordance.
9. **Notes:** keep deid `___` tokens as-is (do not fabricate). One discharge summary per index `hadm_id`;
   dedupe on `note_id`. Strip nothing that changes clinical meaning.
10. **Death/Task D:** `dod` (patients) for post-discharge mortality; `hospital_expire_flag` for in-hospital.
    Plausibility only — never causal (confounding by indication).

---

## 3. MIMIC-IV-ED 2.2 — current-med reconciliation + hypertensive urgency

Keys: `subject_id`, `stay_id` (ED visit); links to `hadm_id` via `edstays`.

| Table | Variable | Meaning | Cleaning |
|---|---|---|---|
| **ed/medrecon** | `name`,`etcdescription`,`etccode`,`gsn`,`ndc` | Reconciled **home** meds | `etcdescription` = therapeutic class (e.g. "…Beta 2-Adrenergic Agents…") → map to engine class. Primary source of *current antihypertensives*. |
| **ed/triage** | `sbp`,`dbp`,`chiefcomplaint`,`acuity`,`pain` | Triage vitals | ED BP = **acute** → `context="admission"`, engine abstains on chronic staging; use for hypertensive-urgency flag only. |
| **ed/vitalsign** | `sbp`,`dbp`,`heartrate`,`charttime` | Repeated ED vitals | same acute-context rule |
| **ed/edstays** | `subject_id`,`hadm_id`,`stay_id`,`intime`,`outtime`,`disposition` | Visit spine | join key ED↔hosp |

Cleaning: cast vital columns from the padded float strings (e.g. `71.0000`) to numeric; range-check;
collapse `medrecon` to a per-`subject_id`/`stay_id` **class set**; dedupe on `(subject_id, name, gsn)`.
Treat all ED BP as acute context.

---

## 4. eICU-CRD 2.0 — descoped to an abstention-calibration probe (HC-21)

Key: `patientunitstayid` (ICU stay); patient across stays = `uniquepid`. **Times are integer offsets in
minutes from unit admission** (`*offset`), not timestamps — negative = before admission. **All BP here is
ICU/acute** → structured-only validation, engine abstains on chronic staging.

| Table | Variables used | Meaning | Cleaning |
|---|---|---|---|
| **patient** | `gender`,`age`,`ethnicity`,`hospitaldischargestatus`,`unittype`,`patientunitstayid` | Demographics/outcome | **`age` is a string; ">89" topcode** → map to 90 (numeric). `hospitaldischargestatus ∈ {Alive,Expired}`. |
| **pastHistory** | `pasthistorypath`,`pasthistoryvalue` | Comorbidities (incl. HTN) | path strings → comorbidity flags |
| **diagnosis** | `diagnosisstring`,`icd9code`,`diagnosispriority` | Dx | `icd9code` may hold ICD-9 **and** ICD-10 comma-joined; split & map |
| **admissionDrug** | `drugname`,`drugdosage`,`drughiclseqno` | Home meds at admission | drug→class; free text, needs normalization |
| **lab** | `labname`,`labresult`,`labmeasurenamesystem` | Labs incl. creatinine, potassium | filter `labname` in {creatinine, potassium}; `labresult` numeric; check units column |
| **apachePatientResult** | `apachescore`,`predictedhospitalmortality`,`actualhospitalmortality` | Severity/outcome | validation covariates only |

Cleaning: convert offsets only if you need ordering (nearest-to-admission lab); handle `>89`/`>300`
topcodes; unit-check labs (eICU mixes conventional units); build the same class-set med representation as
MIMIC so the engine sees one schema.

---

## 6. Cross-cutting derived variables (compute identically for every source)

These are engine inputs, computed **after** per-source cleaning so the `PatientProfile` schema is uniform.

| Derived field | Definition | Inputs |
|---|---|---|
| `sbp`,`dbp` | **mean** of valid readings (NHANES) / mean of qualifying pre-index OMR (MIMIC) / — (eICU acute) | source BP |
| `bp_stage` | Elevated / Stage 1 / Stage 2 per 2025 AHA/ACC thresholds | `sbp`,`dbp` |
| `egfr` | **CKD-EPI 2021 race-free**: 142·min(Scr/κ,1)^α·max(Scr/κ,1)^-1.200·0.9938^age·(1.012 if female); κ=0.7♀/0.9♂, α=-0.241♀/-0.302♂ | `LBXSCR`/creatinine, age, sex |
| `ckd_albuminuria` | eGFR<60 **or** UACR≥30 mg/g | egfr, UACR |
| `potassium` | serum K⁺ (mmol/L); flag `≥5.5` | lab |
| `diabetes` | dx code / `DIQ010==1` | dx / questionnaire |
| `prevent_10yr` | **PREVENT** base-model 10-yr **total**-CVD risk (ASCVD + heart failure; replaces the Pooled Cohort Equations) | age, sex, SBP, treated-BP, total chol, HDL, diabetes, smoking, eGFR, **statin use**. **NOT BMI and NOT UACR** — corrected 2026-07-18: BMI belongs to the *heart-failure* model and UACR to the *enhanced* model, neither of which this project uses. Valid only for **ages 30–79**; outside that range or with any input missing → `None` → engine abstains, **never** "low risk" |
| `on_bp_meds` | currently taking antihypertensive | `BPQ050A` / medrecon / prescriptions |
| `med_classes` | set ⊆ {thiazide, ACEI, ARB, DHP-CCB, other} | drug→class map |
| `contraindications` | {pregnancy, angioedema_hx, hyperkalemia(K≥5.5)} | dx / labs |

**Open decisions — status as of 2026-07-18:**
(a) **NHANES J-only vs `P_` pool → recommend J** for the frozen Paper-1 benchmark, with `P_` as a
pre-registered robustness appendix. Per-row labels never use survey weights, so the `WTMEC2YR`→`WTMECPRP`
switch only affects Task-D/prevalence estimates. The N gain is also smaller than previously claimed:
~9,254 → ~15,560 respondents ≈ **1.7×, not "roughly double"**.
(b) **MIMIC index-encounter rule → earliest anchor + 365 d/≥2 OMR, PLUS a mandatory ED linkage.** See §2.
(c) ~~PREVENT vs PCE~~ — **RESOLVED/LOCKED: PREVENT**, base total-CVD model, ≥7.5% threshold. PCE must not
be used (its threshold was ≥10% on ASCVD, a different endpoint).
(d) **Discard BP reading #1 → still open**; settle before the benchmark freeze and report both settings (§1).

---

## 7. Global cleaning conventions (apply everywhere)

1. **One canonical schema.** Every source → `schemas/patient_profile.schema.json`. Source-specific columns
   die at the cleaning boundary; downstream code never branches on source.
2. **Missing ≠ zero.** Preserve `NA`; map all "refused/don't know/unknown" sentinels to `NA`; the engine
   emits `ABSTAIN`/`not_encoded` when a required field is missing rather than guessing.
3. **Units are explicit.** Carry units through cleaning; assert expected units (mmol/L for K⁺, mg/dL for
   creatinine, mg/g for UACR, mmHg for BP) and fail loudly on mismatch. eICU/MIMIC unit drift is the main
   silent-error risk.
4. **Range/plausibility gates.** SBP 60–290, DBP 30–200, creatinine 0.1–20, K⁺ 1.5–9, age 18–120;
   out-of-range → `NA` with a logged reason, never silently clipped.
5. **Context flag on every BP.** `chronic` (NHANES / MIMIC `omr`) vs `admission` (ED / ICU / triage /
   chartevents). Chronic staging only from chronic BP; acute BP → engine abstains.
6. **Deid artifacts.** MIMIC `___` and date-shift: never impute across them; use `valuenum` not `value`;
   ages 89+/">89" topcodes handled explicitly per source (MIMIC→91, eICU→90, NHANES→80).
7. **Reproducibility.** Deterministic pipeline, pinned versions, checksummed inputs (SHA256SUMS present in
   each dataset), a data manifest, and a row-count/QA report per table. No manual edits.
8. **Leakage discipline (benchmark-critical).** The cleaned **structured row is the hidden label**; the
   LLM only ever sees the rendered vignette / raw note. Keep label columns physically separate from any
   text served to a model.
9. **PHI/credentialing.** MIMIC, eICU are credentialed — keep local, do not send raw records to external
   services; vignettes are derived/rendered, not raw rows.

---

## 8. Recommended execution order

1. ~~**Unblock NHANES**~~ — **done**; 13 `.XPT` files in `Data/NHANES/`. **Remaining gap: download `MCQ_J`**
   (`MCQ160B–F`: CHF, CHD, angina, MI, stroke) → `clinical_cvd`. Without it that Stage-1 initiation trigger is
   null for every NHANES row, biasing labels toward **under-treatment** — the unsafe direction, and the
   cheapest available gain in label validity.
2. ~~Build the **NHANES → PatientProfile** pipeline~~ — **done**; 4,806 profiles. Re-emitted 2026-07-18 after
   the `bp_stage` / `ckd_albuminuria` correctness fixes.
3. Build **MIMIC-IV** (labevents itemid-filtered load, OMR BP parser, ICD-9/10 crosswalk, medrecon join,
   discharge-note selection) → Tasks B/C.
4. Add **eICU** only as the ~500-stay abstention-calibration probe (HC-21, descoped) — not a full second
   structured substrate.
5. Emit a **QA report** (row counts, missingness, range-violation logs, unit assertions) before any
   engine/label run.
