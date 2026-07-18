# HTN-Concord — Data Selection, Typing & Processing Walkthrough

**Purpose.** This document answers six questions end to end, for the NHANES substrate that is
actually built and running:

1. Which tables and columns do we take from which database?
2. **Why those columns** — what guideline decision does each one feed?
3. What data type is each column, at each stage?
4. What are the cleaning rules, and in what order do they run?
5. How do we handle missing data (and why we mostly *don't* fill it)?
6. What does the whole processing pipeline do, step by step?

**Relationship to the other data doc.** `HTN-Concord_DataDictionary_and_CleaningStrategy.md` is the
*reference* — it enumerates every table across all five datasets, including MIMIC-IV, MIMIC-ED, eICU
and Zigong HF, and it carries the correction history. **This document is the *walkthrough*** — it
follows one substrate (NHANES cycle J) from raw `.XPT` to validated `PatientProfile`, and it
concentrates on the reasoning the reference doc assumes you already have. Where the two disagree, the
reference doc wins on facts about *other* datasets; this doc wins on the NHANES execution order,
because it was written by reading `pipelines/nhanes/` directly.

**Chinese counterpart:** `HTN-Concord_DataProcessing_Walkthrough_zh.md` — **update both together.**

---

## 0. The one design decision everything else follows from

HTN-Concord's cleaned structured row is not a *dataset*. It is an **answer key**. The engine reads a
`PatientProfile` and emits a guideline decision that we then treat as ground truth for scoring LLMs.

That single fact drives every rule below, and it inverts the usual data-science instinct:

| Ordinary ML pipeline | HTN-Concord pipeline |
|---|---|
| Impute missing values so the model can train | **Never impute a clinical fact.** Missing → engine `ABSTAIN` |
| Clip outliers into range so nothing is lost | **Reject out-of-range to `NA`.** A clipped 350 mmHg becomes a fake 290 |
| Maximize N | Maximize *label validity*. A row we cannot label correctly is worse than a row we drop |
| False negatives and false positives trade off | **Asymmetric.** Guessing "no risk factor" causes under-treatment — the unsafe direction |

If you remember one sentence: **an unknown must survive the pipeline as an unknown**, because
"I don't have enough information to decide" is one of the answers the benchmark grades.

---

## 1. Which database, and why NHANES is the primary substrate

Five credentialed datasets sit in `Data/`. NHANES is the primary substrate for the frozen Paper-1
benchmark, and the reason is not sample size:

| Requirement for a guideline answer key | NHANES | MIMIC-IV | eICU |
|---|---|---|---|
| BP measured in a **chronic/outpatient** context (guideline staging assumes this) | ✅ standardized MEC exam | ⚠️ only `hosp/omr` | ❌ all acute ICU |
| **Protocolized repeat readings** (staging needs a stable BP, not one reading) | ✅ 3 oscillometric reads | ❌ irregular counts | ❌ |
| Every PREVENT input present in one row | ✅ | ⚠️ scattered, time-bounded | ❌ |
| Current **home** antihypertensives | ✅ `RXQ_RX` | ⚠️ `medrecon` (ED-linked only) | ⚠️ free text |
| Public, redistributable, reproducible by a reviewer | ✅ free download | ❌ credentialed | ❌ credentialed |
| Free-text clinical notes for Task C | ❌ | ✅ | ❌ |

NHANES wins on **decision context**. An ICU blood pressure of 168/94 is not Stage 2 hypertension — it
is a sick person in an ICU bed, and the 2025 AHA/ACC staging thresholds simply do not apply to it.
This is why `bp_context` exists as a first-class schema field and why eICU was descoped: a pipeline
that emits 200,000 rows on which the engine must abstain has produced no benchmark items.

MIMIC-IV is retained for Tasks B/C precisely because it has what NHANES lacks — discharge notes — and
its `hosp/omr` table is the one MIMIC BP source with an outpatient context.

---

## 2. Which columns, and **why each one** was chosen

The selection rule is: **a column earns its place only if a guideline decision changes when it
changes.** Nothing is collected "because it might be useful." Each row below names the decision.

### 2.1 Columns that decide the *stage* (the branch point of the entire guideline)

| File | Column | Why it is needed |
|---|---|---|
| `BPXO_J` | `BPXOSY1–3`, `BPXODI1–3` | **The staging input.** Three oscillometric reads, not one, because a single reading is an unreliable estimate of usual BP and the first is systematically high. Everything downstream — normal / elevated / Stage 1 / Stage 2 — is a function of these six numbers |
| `DEMO_J` | `RIDAGEYR` | Enters as an **eGFR input and a PREVENT input**. Note: age is *not* a standalone Stage-1 initiation trigger under the 2025 guideline — it acts only through PREVENT |
| `DEMO_J` | `RIAGENDR` | Sex-specific coefficients in **both** CKD-EPI 2021 (κ, α, the 1.012 female factor) and PREVENT (entirely separate male/female models) |
| `DEMO_J` | `SEQN` | Join key for every file. One respondent = one row = one profile |

### 2.2 Columns that decide *whether to start a drug* at Stage 1

Under the 2025 AHA/ACC guideline, Stage 1 (130–139/80–89) is the hard case: lifestyle alone if
low-risk, medication if high-risk. High-risk means clinical CVD **or** diabetes **or** CKD **or**
PREVENT 10-year risk ≥7.5%. Every column below exists to resolve exactly that fork.

| File | Column | Why it is needed |
|---|---|---|
| `DIQ_J` | `DIQ010` | Self-reported diabetes — **a standalone Stage-1 trigger** |
| `GHB_J` | `LBXGH` | HbA1c ≥6.5% — the **lab limb** of diabetes. Needed because self-report misses undiagnosed diabetes, and an undiagnosed diabetic wrongly labelled low-risk produces an *under-treatment* label, the unsafe error |
| `BIOPRO_J` | `LBXSCR` | Serum creatinine → eGFR. eGFR <60 is a **CKD trigger**, and eGFR is also a **PREVENT input** — this one column feeds two independent paths |
| `ALB_CR_J` | `URDACT` | UACR ≥30 mg/g — the **other limb of CKD**. Without it CKD collapses to the eGFR limb alone and under-fires, since albuminuric CKD with preserved eGFR is common and is exactly the population the guideline wants treated |
| `TCHOL_J` | `LBXTC` | Total cholesterol → PREVENT |
| `HDL_J` | `LBDHDD` | HDL → PREVENT (with total cholesterol it yields the non-HDL term) |
| `SMQ_J` | `SMQ020`, `SMQ040` | Current smoking → PREVENT. Two columns because `SMQ040` is skip-gated behind `SMQ020` (see §5.2) |
| `RXQ_RX_J` + `RXQ_DRUG` | `RXDDRUG`, `RXDDRGID` | Statin use → PREVENT (statins are in the base model). Also the source of `med_classes` |
| `BPQ_J` | `BPQ050A` | Currently on BP medication → PREVENT's **treated-BP** term |
| `MCQ_J` ⚠️ | `MCQ160B–F` | Clinical CVD (heart failure, coronary disease, angina, MI, stroke) — a standalone Stage-1 trigger. **This file is not downloaded**, so `clinical_cvd` is null for every NHANES row and the QA report shows 100% missingness on it. The bias runs toward under-treatment; downloading it is the cheapest available gain in label validity |

### 2.3 Columns that decide *which drug*, and which drug to avoid

| File | Column | Why it is needed |
|---|---|---|
| `BIOPRO_J` | `LBXSKSI` | Serum potassium. K⁺ ≥5.5 mmol/L is a **contraindication** to ACEI/ARB — one of the few hard "do not do this" rules the benchmark tests |
| `BIOPRO_J`/`ALB_CR_J` | (via eGFR + UACR) | CKD **prefers** ACEI/ARB. Note this is the opposite of a contraindication: reduced eGFR is a *reason to choose* these drugs, plus a monitoring requirement |
| `RXQ_RX_J` | `RXDDRUG` | Current antihypertensive **classes** — the difference between "initiate" and "intensify," and the input to whether the next drug is a duplicate of one already on board |
| `DEMO_J` | `RIDEXPRG` | Pregnancy. ACEI/ARB are teratogenic. **Currently read from disk but not wired into the `pregnancy` flag** — pregnant respondents presently carry an empty `contraindications` list. This is a live safety gap, not a cosmetic one |

### 2.4 Columns kept for reasons other than the decision

| File | Column | Why |
|---|---|---|
| `DEMO_J` | `RIDRETH3` | **Subgroup reporting only.** The engine is deliberately race-neutral — CKD-EPI 2021 is the race-free equation and PREVENT has no race term. This column exists so we can *report* performance by subgroup, never so the engine can branch on it |
| `DEMO_J` | `WTMEC2YR`, `SDMVPSU`, `SDMVSTRA` | Survey design. Used **only** for population-level prevalence and Task-D mortality estimates. **Never** for a per-vignette label: a patient's correct treatment does not depend on how many Americans they represent |
| `BMX_J` | `BMXBMI` | Kept for cohort description. **It is not a PREVENT base-model input** — BMI belongs to the heart-failure model, which this project does not use |
| `BPQ_J` | `BPQ020`, `BPQ030`, `BPQ040A` | `BPQ020`/`BPQ040A` are needed to decode the `BPQ050A` skip gate (§5.2); `told_hypertension` is also a useful descriptive contrast against measured stage |

### 2.5 What we deliberately do *not* take

- **NHANES `P_` pre-pandemic pool.** Recommend cycle J for the frozen benchmark, `P_` as a
  pre-registered robustness appendix. The N gain is ~9,254 → ~15,560 respondents (≈1.7×), and J and
  `P_` must never be mixed in one frame — the weight column differs (`WTMEC2YR` vs `WTMECPRP`).
- **Any race-based eGFR equation.** Excluded on principle, not availability.
- **Pooled Cohort Equations.** Superseded by PREVENT. Their ≥10% threshold is on a *different
  endpoint* (ASCVD, not total CVD), so mixing them silently changes what "high risk" means.

---

## 3. Data types — the three-layer contract

Types are checked at three boundaries. This matters because NHANES ships **everything as a float**,
including things that are semantically categorical or boolean, and a silent float is how "refused =
7" becomes a plausible-looking data value.

### Layer 1 — raw `.XPT`

SAS transport format. `pd.read_sas(path, format="xport")` returns **`float64` for every numeric
column**, including `SEQN`, `RIAGENDR`, and every 1/2/7/9 questionnaire code. `io_xpt.read_component`
immediately casts `SEQN` to nullable `Int64` so the join key cannot drift through float arithmetic.

### Layer 2 — pandas, after cleaning

The pipeline uses **pandas nullable dtypes**, not numpy dtypes. This is not stylistic — numpy `bool`
has no NA state, so a nullable `boolean` is the only way to represent "we don't know" without
falling back to `False`.

| Profile column | pandas dtype | Notes |
|---|---|---|
| `SEQN` | `Int64` | nullable integer key |
| `source`, `bp_context` | `object` (str) | constant per source: `"nhanes"`, `"chronic"` |
| `age`, `sbp`, `dbp`, `creatinine`, `egfr`, `potassium`, `uacr`, `hba1c`, `total_chol`, `hdl`, `bmi`, `prevent_10yr` | `float64` | NaN = unknown |
| `sex` | `object` (str) | mapped `1→"male"`, `2→"female"` at clean time, never left as a code |
| `race_eth` | `float64` | code retained as-is; reporting only |
| `bp_stage` | `object` | `"normal"`/`"elevated"`/`"stage1"`/`"stage2"`/`NA` |
| `bp_n_readings` | `Int64` | provenance: how many reads the summary came from |
| `diabetes`, `ckd_albuminuria`, `current_smoker`, `told_hypertension`, `on_bp_meds`, `statin_use`, `clinical_cvd` | **`boolean`** (nullable) | three-valued: `True` / `False` / `pd.NA` |
| `med_classes`, `contraindications` | `object` holding **`list[str]`** | never a comma-string |

### Layer 3 — the JSON Schema contract

`schemas/patient_profile.schema.json` is the enforced boundary; `validate.validate_profiles` runs
inside `build_profiles.build()`, so an invalid row cannot be written. Two things the schema encodes
that a dtype cannot:

- **Nullability is explicit and intentional.** Nearly every field is `["number", "null"]` or
  `["boolean", "null"]`. The schema description states the rule directly: null is allowed wherever a
  value is genuinely unknown so the engine can abstain, and *must never be coerced to a definite
  value*.
- **Enums close the vocabulary.** `bp_stage`, `bp_context`, `sex`, and the item enums of
  `med_classes` and `contraindications` are closed sets. A typo like `"stage_1"` fails validation
  rather than silently becoming an unmatched category downstream.

Required fields (a row cannot exist without them): `source`, `age`, `sex`, `sbp`, `dbp`, `bp_stage`,
`bp_context`, `med_classes`, `contraindications`. Note that the two list fields are required but may
be **empty** — an empty list is a positive assertion ("no contraindications found"), which is
different from null.

### Serialization

`build_profiles.main()` writes both Parquet and CSV. Parquet preserves the list dtype natively; CSV
would flatten a list to the lossy Python repr `"['thiazide']"`, so list columns are **JSON-encoded**
before CSV write and round-trip through `json.loads`. If you read the CSV, parse those two columns.

---

## 4. Cleaning rules, in execution order

The order in `build_profiles.build()` is load-bearing. Two orderings in particular are correctness
requirements, not preferences.

### Step 1 — Read

`io_xpt.try_read(component)` per component. `GHB` is the only **optional** component: if absent the
pipeline runs with a warning and diabetes falls back to self-report alone. Every other missing file
is a hard error — silently producing profiles without potassium would produce profiles without
contraindications.

### Step 2 — Clean each component to one row per `SEQN`

Each `clean_*` function returns a tidy frame keyed by `SEQN` with **engine-facing column names**.
Source-specific names (`LBXSCR`, `BPXOSY1`) die here and never appear downstream. That is what makes
the MIMIC pipeline substitutable: downstream code never branches on source.

Rules applied at this step:

- **Sentinel → NA.** `_na_sentinels` maps questionnaire `7` (refused) and `9` (don't know) to
  `pd.NA`. Applied to every questionnaire column before any comparison, because `DIQ010 == 1` on
  un-sanitized data silently treats "refused" as "not diabetic."
- **Codes → meaning.** `RIAGENDR` becomes `"male"`/`"female"` at clean time. Downstream code compares
  against words, so a coding change in a future cycle fails loudly instead of silently inverting.
- **BP summarization.** Mean of available reads 1–3, requiring ≥1 valid pair; `bp_n_readings`
  records how many contributed.
  > 🚨 **Documented as median, implemented as mean (HC-23).** Every project document states that
  > median was harmonized across sources on 2026-07-18, but `clean.py` computes
  > `df[sys_cols].mean(axis=1)`. **The shipped `nhanes_profiles_J.csv` is a mean-based artifact**,
  > and every stage/label figure quoted anywhere describes the mean pipeline. In NHANES the practical
  > difference is small — 4,783/4,806 rows have all three readings — but switching re-emits the
  > benchmark substrate and moves published numbers, so it is a **benchmark-freeze decision, not a
  > cleanup**. Until HC-23 lands, read "median" in project docs as *intended*, not implemented.
- **Discard-reading-#1 toggle.** `discard_first = False` in `clean_bp`. Still an open decision.
  The first oscillometric reading runs systematically high, so retaining it inflates Stage 1/2 and
  therefore the initiation label; discarding costs almost no sample (only 10 rows have a single
  reading). Settle before the benchmark freeze and report a sensitivity table under both settings.
- **Skip-gate reconstruction** for `on_bp_meds` and `current_smoker` — see §5.2.

### Step 3 — Merge

Left-join every cleaned frame onto `DEMO` on `SEQN`. `DEMO` is the spine because it is the only file
covering all 9,254 respondents; every other component is a subsample (`BPXO` 7,132, `BIOPRO` 6,401,
`BPQ` 6,161 …). **Left-join, not inner-join** — an inner join would silently apply an undocumented
cohort filter, dropping anyone who skipped a lab, and would make the cohort a side effect of join
order rather than an explicit rule.

### Step 4 — Range gate **before** derive ⚠️

`qa.apply_ranges` nulls out-of-range values and logs each violation.

| Column | Accepted range | Unit |
|---|---|---|
| `sbp` | 60–290 | mmHg |
| `dbp` | 30–200 | mmHg |
| `creatinine` | 0.1–20 | mg/dL |
| `potassium` | 1.5–9 | mmol/L |
| `age` | 0–120 | years |
| `bmi` | 10–90 | kg/m² |
| `total_chol` | 50–600 | mg/dL |
| `hdl` | 5–200 | mg/dL |
| `uacr` | 0–30000 | mg/g |

Two properties matter:

- **Reject, never clip.** An out-of-range value becomes `NA`. Clipping 350 mmHg to 290 manufactures a
  plausible-looking measurement that then produces a confident Stage 2 label from data we know is
  corrupt.
- **The gate runs before derivation.** Deriving first would let an implausible creatinine produce an
  eGFR, and an implausible SBP produce a stage, that is then based on a value we delete one line
  later — leaving a derived field with no surviving input. In the current cycle-J run the violation
  log is empty, but the ordering is what makes that verifiable rather than lucky.

### Step 5 — Derive engine fields

Computed here, not per source, so the schema is identical across NHANES/MIMIC/eICU.

- **`egfr`** — CKD-EPI 2021 race-free:
  `142 · min(Scr/κ,1)^α · max(Scr/κ,1)^−1.200 · 0.9938^age · (1.012 if female)`,
  κ = 0.7 ♀ / 0.9 ♂, α = −0.241 ♀ / −0.302 ♂.
- **`bp_stage`** — thresholds from `vocab.BP_THRESHOLDS` (elevated SBP ≥120; Stage 1 ≥130 or ≥80;
  Stage 2 ≥140 or ≥90), OR logic, most severe applied last. Comparisons are **half-open (`>=`)**, not
  `between()`: an earlier `between(130, 139)` voided any non-integer mean BP such as 139.5/79 to NA
  and made the profile column disagree with the engine, which stages independently through
  `vocab.bp_stage_scalar`. `vocab` is the single source of truth for both.
- **`diabetes`** — `diabetes_self` **OR** `hba1c ≥ 6.5` under Kleene logic (§5.3).
- **`ckd_albuminuria`** — `egfr < 60` **OR** `uacr ≥ 30`, Kleene OR. It is an **OR, not an AND**,
  matching KDIGO and the guideline's own phrasing. The field *name* implies a conjunction and should
  be read as plain `ckd`.
- **`contraindications`** — currently `hyperkalemia` only (K⁺ ≥5.5). `angioedema_hx` is genuinely
  unascertainable in NHANES and is left empty rather than guessed. `pregnancy` **is** ascertainable
  via `RIDEXPRG` but is not yet wired in — see §2.3.
- **`prevent_10yr`** — delegated to the pure `prevent` module (coefficients from Khan 2024
  Table S12A, validated against the paper's worked example). Returns NaN when any input is missing or
  age is outside 30–79.

### Step 6 — Cohort filter

`age >= 18` **and** `sbp` not null. Applied **after** the range gate, so a respondent whose only BP
was implausible is correctly excluded rather than carried with a garbage stage. Effect:
**9,254 respondents → 4,806 profiles.**

### Step 7 — Schema validation

`validate.validate_profiles(df)` against `patient_profile.schema.json`, inside the build. Missing
columns are added as `pd.NA` and the frame is reordered to `PROFILE_COLUMNS` first, so the emitted
column set is fixed regardless of which optional components were present.

### Step 8 — QA report

`qa.write_report` emits `data/nhanes/qa/nhanes_qa_J.json`: row counts per source file, the
range-violation log, per-column missingness, and the stage distribution. **Written before any label
run** — this is the artifact you check before trusting a downstream number.

### Step 9 — Write

Parquet + JSON-encoded CSV to `data/nhanes/processed/`.

---

## 5. Missing data — the policy that most distinguishes this pipeline

**Headline: we do not impute clinical values. There is no mean-fill, no median-fill, no MICE, no
LOCF, no k-NN.** A blood pressure, a creatinine, a potassium, or a cholesterol that was not measured
stays missing all the way into the engine, which then abstains.

The reason is that the engine's output is ground truth. An imputed creatinine produces an imputed
eGFR, which produces a *confident* CKD determination, which flips a Stage-1 patient from "lifestyle"
to "start a drug." We would then grade an LLM against a recommendation derived from a number nobody
measured. Imputation is a reasonable tool for estimating a population parameter; it is not admissible
for constructing a per-patient answer key.

What the pipeline does instead falls into four policies. Only the second and fourth put a value where
there was none, and neither is imputation of a clinical measurement.

### 5.1 Policy 1 — Preserve (the default, for every measured value)

Sentinels `7`/`9` → `pd.NA`. Lab/BP blanks stay `NA`. Out-of-range → `NA`. Downstream, `NA`
propagates to the derived field, and the engine emits `ABSTAIN` with a reason rather than a guess.

Current missingness in the emitted cohort, from the QA report:

| Field | Missing | Reading |
|---|---|---|
| `age`, `sex`, `sbp`, `dbp`, `bp_stage` | 0% | guaranteed by the cohort filter |
| `bmi` | 0.7% | |
| `told_hypertension`, `on_bp_meds` | 0.2% / 0.3% | low *because* of skip-gate reconstruction (§5.2) |
| `uacr` | 1.5% | |
| `diabetes` | 3.4% | lower than `DIQ010` alone, because the HbA1c limb rescues some |
| `hba1c` | 3.8% | |
| `total_chol`, `hdl` | 5.2% | |
| `creatinine`, `egfr` | 5.6% | identical, as expected — eGFR is a pure function of creatinine |
| `potassium` | 5.6% | |
| `ckd_albuminuria` | 5.5% | slightly below creatinine: UACR rescues rows without creatinine |
| **`prevent_10yr`** | **29.2%** | **expected and correct** — see below |
| **`clinical_cvd`** | **100%** | **a real gap** — `MCQ_J` not downloaded (§2.2) |

The 29.2% PREVENT missingness is not a data-quality problem. PREVENT is defined only for ages 30–79,
so everyone aged 18–29 and 80+ is legitimately non-computable, and any one missing input (cholesterol,
eGFR, smoking) removes a row. The alternative — extrapolating the model outside its validated range —
would fabricate the exact number that decides Stage-1 initiation.

### 5.2 Policy 2 — Reconstruct skip-gated survey logic (*decoding, not imputation*)

This is the one place the pipeline fills blanks, and it is legitimate because **the blank is not
missing data — it is a recorded answer expressed as a skip.**

NHANES questionnaires are branched. If you say you never smoked, you are never asked "do you smoke
now?" Treating that blank as unknown is wrong: the respondent *did* tell us they are a non-smoker,
just via the gate rather than the follow-up.

**`current_smoker`** (`clean_smq`):

| Condition | Result | Justification |
|---|---|---|
| `SMQ020 == 2` (never smoked ≥100 cigarettes) | `False` | never-smokers are not asked `SMQ040`; they are true non-smokers, not unknowns |
| `SMQ040 == 3` (not at all) | `False` | former smoker |
| `SMQ040 ∈ {1, 2}` (every day / some days) | `True` | current |
| otherwise | `pd.NA` | genuine refusal or missing |

**`on_bp_meds`** (`clean_bpq`) — a three-level gate `BPQ020 → BPQ040A → BPQ050A`:

| Condition | Result | Justification |
|---|---|---|
| `BPQ020 == 2` (never told high BP) | `False` | cannot be on BP medication |
| `BPQ040A == 2` (told, never advised meds) | `False` | |
| `BPQ050A == 2` (advised, not currently taking) | `False` | |
| `BPQ050A == 1` | `True` | on treatment → PREVENT treated-BP term, and "intensify" rather than "initiate" |
| otherwise | `pd.NA` | genuine in-path refusal/don't-know only |

The comment in `clean_bpq` records why: blanket NA-preservation would wrongly abstain on the
untreated and undiagnosed — i.e. on most of the population. Reconstruction takes `on_bp_meds`
missingness down to 0.25%, and every filled value is *derivable from an answer the respondent
actually gave*.

### 5.3 Policy 3 — Kleene three-valued logic for derived booleans

When a derived flag ORs two limbs that can each be unknown, the pipeline uses **Kleene OR** via
pandas nullable `boolean`:

```
True  | NA   = True     (one limb is enough; the other cannot change it)
False | NA   = NA       (unknown — do NOT read as False)
NA    | NA   = NA
```

Applied to `diabetes` (self-report | HbA1c ≥6.5) and `ckd_albuminuria` (eGFR <60 | UACR ≥30).

This corrected a real defect. `ckd_albuminuria` previously ended in `.fillna(False)`, which laundered
"unknown" into "known-negative" and let the engine take the Stage-1 **low-risk** branch for patients
whose kidney status was never measured — under-treatment presented as ground truth. Together with two
related fixes (NaN PREVENT must abstain, not read as low-risk; numpy-bool hardening) this changed
109 of 4,806 labels, all toward fidelity.

The general rule: **`False` must mean "measured and negative," never "not measured."**

### 5.4 Policy 4 — Structural defaults, where absence really is evidence

| Field | Default | Justification |
|---|---|---|
| `med_classes` | `[]` | `RXQ_RX` is a complete prescription inventory. A respondent absent from it, or present with no antihypertensive, genuinely has no antihypertensive class — absence in a complete enumeration is a negative, not a gap |
| `contraindications` | `[]` | same structure — but note this is only sound for the flags actually evaluated. With `pregnancy` unwired, an empty list currently over-claims |
| `statin_use` | `False` via `.fillna(False)` | **the weakest default here.** Justified by the same complete-inventory argument, but unlike `med_classes` it is applied as a blanket `fillna` after the merge, so a respondent missing from `RXQ_RX` for any reason becomes a definite non-statin-user. It shifts PREVENT slightly upward (untreated risk is higher). Worth revisiting for consistency with the Kleene policy elsewhere |

---

## 6. The full processing pipeline at a glance

```
Data/NHANES/*.XPT                    13 SAS transport files, one row per SEQN
   │
   ├─ io_xpt.try_read                float64 everything; SEQN → Int64
   │                                 GHB optional; others hard-fail
   ├─ clean.clean_*                  → one tidy frame per component, keyed by SEQN
   │                                   • 7/9 → NA
   │                                   • codes → words (sex)
   │                                   • BP summary + bp_n_readings
   │                                   • skip-gate reconstruction
   ├─ drug_class                     RXQ_RX (long, 19,643 rows) ⋈ RXQ_DRUG lexicon
   │                                   → med_classes: sorted list per SEQN
   │                                   → statin_use: bool per SEQN
   ├─ _merge                         left-join all onto DEMO (9,254) on SEQN
   ├─ qa.apply_ranges       ⚠️ FIRST  out-of-range → NA + violation log
   ├─ derive.*                       egfr, bp_stage, diabetes, ckd_albuminuria,
   │                                 contraindications, prevent_10yr
   ├─ cohort filter                  age ≥ 18 AND sbp notna   → 9,254 → 4,806
   ├─ validate.validate_profiles     JSON Schema; invalid rows cannot be written
   ├─ qa.write_report                → data/nhanes/qa/nhanes_qa_J.json
   └─ write                          → nhanes_profiles_J.parquet + .csv
                                       (list columns JSON-encoded in CSV)
```

Run it with `python -m pipelines.nhanes.build_profiles` from `htn-concord/`. Switch cycle with
`NHANES_CYCLE=J|P_pre_pandemic`; point at raw files with `NHANES_RAW_DIR`.

**Current output:** 4,806 schema-valid adult profiles. Stage distribution: normal 2,073 /
elevated 674 / Stage 1 975 / Stage 2 1,084 — i.e. Stage 1+2 ≈ 42.8%. *These figures describe the
mean-BP pipeline (§4 step 2); they will move if HC-23 lands.*

---

## 6b. MIMIC-IV — used and unused tables

> ⚠️ **Build status.** Only `pipelines/mimic/feasibility.py` (HC-13, counting only) and
> `pipelines/mimic/omr_bp.py` (HC-14, the BP parser) exist. The cohort builder, labevents loader,
> ICD crosswalk, medrecon join and profile emission are **(NOT BUILT)**.

### Used

| Table | Columns | Why it is needed | Handling |
|---|---|---|---|
| `hosp/omr` | `subject_id`, `chartdate`, `result_name`, `result_value` | **The only outpatient BP in MIMIC** — the only MIMIC source that can drive chronic staging | `result_value` is a `"SYS/DIA"` **string** → regex parse; posture from `result_name`; `bp_context="office"` |
| `hosp/labevents` | `itemid`, `charttime`, `valuenum`, `valueuom` | Creatinine (`50912`) → eGFR; potassium (`50971`) → hyperkalemia contraindication | 2.4 GB — filter by `itemid` **before** loading; use `valuenum` (`value` may be deid `"___"`) |
| `hosp/d_labitems` | `itemid`, `label`, `fluid` | Confirm itemids and units | join only |
| `hosp/diagnoses_icd` | `icd_code`, `icd_version` | HTN anchor + comorbidity flags | mixed ICD-9 and ICD-10 → both crosswalked |
| `hosp/d_icd_diagnoses` | `icd_code`, `long_title` | Human-readable labels | join only |
| `hosp/patients` | `gender`, `anchor_age`, `dod` | Demographics; `dod` for Task D | age 89+ topcoded to 91 |
| `hosp/admissions` | `admittime`, `dischtime`, `hospital_expire_flag`, `race` | Index-encounter selection; in-hospital death | date-shifted per patient; within-patient order valid, absolute dates meaningless |
| `note/discharge` | `note_id`, `hadm_id`, `text` | Task-C input | keep deid `___` as-is; one summary per index `hadm_id`; dedupe on `note_id` |
| `ed/medrecon` | `name`, `etcdescription`, `etccode` | **Home** meds — the only leakage-safe `on_bp_meds` source | `etcdescription` = therapeutic class → engine class; collapse to a class set |
| `ed/edstays` | `subject_id`, `hadm_id`, `stay_id` | ED↔hosp join spine | join only |
| `ed/triage`, `ed/vitalsign` | `sbp`, `dbp`, `chiefcomplaint`, `acuity` | Hypertensive-urgency flag **only** | acute → `bp_context="admission"` → engine abstains on chronic staging |

### Not used, and why

| Table | Why not |
|---|---|
| `hosp/prescriptions` | **Inpatient** orders, not home meds. Using it for `on_bp_meds` leaks the decision being evaluated; `medrecon` supersedes it |
| `hosp/pharmacy`, `hosp/emar`, `hosp/emar_detail` | Administration/dispensing detail — inpatient, same leakage problem |
| `hosp/poe`, `hosp/poe_detail` | Provider order entry: process metadata, not clinical state |
| `hosp/procedures_icd`, `hosp/d_icd_procedures`, `hosp/hcpcsevents`, `hosp/d_hcpcs` | Procedures are out of scope — this is a medication-initiation benchmark |
| `hosp/microbiologyevents` | Infection data; irrelevant to chronic HTN |
| `hosp/drgcodes` | Billing groupers, not clinical state |
| `hosp/services`, `hosp/transfers`, `hosp/provider` | Administrative movement/identity |
| **entire `icu/` module** (`chartevents`, `icustays`, `inputevents`, `outputevents`, `procedureevents`, `datetimeevents`, `ingredientevents`, `d_items`, `caregiver`) | **All ICU BP is acute** → engine abstains on chronic staging. `chartevents` is the largest table in MIMIC and would contribute **zero** decision labels |
| `note/radiology`, `note/radiology_detail`, `note/discharge_detail` | Imaging narrative carries no antihypertensive-decision content; `discharge_detail` is metadata |
| `ed/diagnosis`, `ed/pyxis` | ED-visit coding and dispensing-cabinet data; `medrecon` already supplies home meds |
| `hosp/omr` `eGFR` rows | Present but only ~279 rows — derive eGFR from creatinine instead |

### Cohort rules (design invariant)

> **An HTN ICD code selects the *patient/encounter* (the anchor). It NEVER generates the label.**
> Chronic staging is derived independently from outpatient OMR taken *before* that encounter.

- **Anchor codes:** ICD-9 `4010`/`4011`/`4019` (+`402–404`, anchor only), ICD-10 `I10`, `I11–I13`.
  **Exclude** ICD-9 `405` and ICD-10 `I15*` (secondary HTN, out of scope).
- **Index encounter:** earliest anchor encounter with qualifying prior OMR.
- **PRIMARY BP rule:** ≥2 OMR readings on distinct dates within 365 days before index; take the median.
- **Labs:** most recent value strictly *before* `admittime`, within a pre-registered lookback window.
  "Nearest the index encounter" is bidirectional and would let a lab drawn *during* the admission set
  `egfr` and the hyperkalemia flag — post-index leakage (HC-27).
- **Meds:** pre-encounter home meds from `medrecon`; **never** discharge meds, which are the answer.

### Feasibility waterfall (HC-13, counted)

| Count | Step |
|---:|---|
| 364,627 | All subjects (hosp) |
| 364,627 | Adults ≥18 (MIMIC hosp is adult-only) |
| 110,932 | With an HTN anchor diagnosis |
| 40,980 | …with any OMR BP before earliest anchor encounter |
| **28,530** | **PRIMARY:** ≥2 OMR on distinct dates within 365 d |
| 40,027 | FALLBACK: ≥1 OMR within 730 d |
| 138,038 | OMR-only cohort with ≥2 distinct dates |

> ⚠️ **The decision-capable N is ~8,921, not 28,530** (HC-26). Only 31.3% of PRIMARY index encounters
> have an ED med reconciliation, and `medrecon` is the only leakage-safe source of `on_bp_meds` — the
> variable separating *initiate* from *intensify*.

### MIMIC-specific missing-data handling

- **Deid `___`** — never impute across it; use `valuenum`, not `value`.
- **Date shifts** — per-patient year shift with intervals preserved; never impute across a boundary.
- **Missing `medrecon`** — the 68.7% of PRIMARY encounters without an ED reconciliation must
  **abstain**, not default to "not on meds". Defaulting would systematically mislabel *intensify*
  cases as *initiate*.
- **Missing UACR** — `itemid 51070` is not yet in the itemid set; without it MIMIC `ckd` collapses to
  the eGFR limb and under-fires.
- **Creatinine itemid coverage** — verify `52546` and `52024` alongside `50912`.

---

## 6c. Alternative processing approaches considered and rejected

| Alternative | Why rejected |
|---|---|
| Impute labs (mean / median / MICE / k-NN / LOCF) | The output is an answer key; an imputed value produces a *confident* label from a number nobody measured |
| Clip out-of-range values | Manufactures a plausible-looking measurement; rejection to `NA` is honest |
| `fillna(False)` on unknown flags | Laundered unknown into known-negative — the exact guess the ABSTAIN contract forbids |
| Inner-join components | Would silently impose an undocumented cohort filter and make the cohort a side effect of join order |
| Derive first, gate ranges after | Leaves derived fields whose input is deleted a line later |
| `between(130,139)` for staging | Voided non-integer means to `NA` and made the profile disagree with the engine |
| Race-based eGFR | Excluded on principle; CKD-EPI 2021 is race-free |
| Pooled Cohort Equations | Different endpoint (ASCVD vs total CVD) — the 7.5% cut is only valid against total CVD |
| Extrapolate PREVENT outside 30–79 | Would fabricate the number that decides Stage-1 initiation |
| Use ICD codes to generate the HTN label | ICD selects the *encounter* only; otherwise the benchmark becomes a coding-lookup test |
| `prescriptions` for home meds | Inpatient orders leak the decision being evaluated |
| Discharge meds for `on_bp_meds` | That *is* the answer — maximal leakage |
| Full eICU pipeline | ~200k rows, every one requiring abstention on the headline decision |
| Bidirectional "nearest lab" | Post-index leakage into `egfr` and hyperkalemia (HC-27) |
| Survey weights on per-row labels | A patient's correct treatment does not depend on how many people they represent |
| Pool NHANES J and `P_` in one frame | Different weight columns; produces silently invalid weighted estimates |

---

## 7. Global conventions that apply to every source

These hold for MIMIC-IV and eICU too, and are what let one engine read all three.

1. **One canonical schema.** Every source emits `patient_profile.schema.json`. Source-specific
   columns die at the cleaning boundary; downstream code never branches on source.
2. **Missing ≠ zero.** Preserve `NA`; map every refused/don't-know/unknown sentinel to `NA`; the
   engine abstains rather than guessing.
3. **Units are explicit.** Assert expected units (mmHg, mg/dL creatinine, mmol/L K⁺, mg/g UACR) and
   fail loudly on mismatch. Unit drift is the main silent-error risk in MIMIC and eICU; NHANES is
   comparatively safe because `LBXSKSI` is already SI.
4. **Range gates reject, never clip** — and run before derivation.
5. **Context flag on every BP.** `chronic` (NHANES exam, MIMIC `omr`) vs `admission` (ED/ICU/triage).
   Chronic staging only from chronic BP.
6. **Deid artifacts are never imputed across.** MIMIC `___` and date shifts; use `valuenum` not
   `value`. Age topcodes handled explicitly per source: NHANES 80, MIMIC 91, eICU 90.
7. **Reproducibility.** Deterministic pipeline, pinned versions, checksummed inputs, QA report per
   run. No manual edits to data files, ever.
8. **Leakage discipline.** The cleaned structured row **is the hidden label**. The LLM sees only the
   rendered vignette or the raw note. Keep label columns physically separate from any text served to
   a model.
9. **PHI/credentialing.** MIMIC and eICU are credentialed — keep local, never send raw records to
   external services. NHANES is public and redistributable, which is part of why it is the primary
   substrate.

---

## 8. Known gaps in this pipeline (read before quoting any number)

| # | Gap | Effect | Direction |
|---|---|---|---|
| 1 | `MCQ_J` not downloaded → `clinical_cvd` 100% null | A Stage-1 high-risk trigger never fires | **Under-treatment** (unsafe) |
| 2 | `RIDEXPRG` not wired to the `pregnancy` flag | Pregnant respondents carry an empty contraindication list; engine could emit "initiate ACEI/ARB" as ground truth | **Unsafe recommendation** |
| 3 | HC-23: docs say median BP, code computes mean | Shipped substrate and every quoted stage figure are mean-based | Benchmark-freeze decision |
| 4 | Discard-reading-#1 still open (`discard_first=False`) | First reading runs high → inflates Stage 1/2 → inflates initiation labels | **Over-treatment** |
| 5 | `statin_use` blanket `fillna(False)` | Inconsistent with the Kleene policy used elsewhere | Small upward PREVENT shift |

Gaps 1 and 2 are safety-relevant and should be closed before the benchmark freeze. Gaps 3 and 4 both
move published numbers and should be decided and executed in a single pass, with every downstream
figure re-quoted together.
