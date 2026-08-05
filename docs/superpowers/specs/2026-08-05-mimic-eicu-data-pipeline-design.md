# MIMIC-IV + eICU data pipelines — design spec

**Date:** 2026-08-05
**Tickets:** HC-15..HC-19 (MIMIC cohort), HC-21 (eICU probe), HC-26 (ED linkage), HC-27 (lab
time-bounding), HC-54 (Task-C silver labels)
**Status:** design. No code in this spec exists yet unless explicitly marked ✅.
**Companions:** `HTN-Concord_Master_Plan.md` §2.2–2.4, `HTN-Concord_DataProcessing_Walkthrough.md`
§6b, `HTN-Concord_Experiment_Design.md` §10 (corpus feasibility audit).

---

## 0. What this spec covers, and what it does not

**Covers.** Turning MIMIC-IV 3.1 (+ ED 2.2, + Note 2.2) and eICU-CRD 2.0 into schema-valid
`PatientProfile` rows, across all three MIMIC sub-cohorts (Primary decision, OMR-only, Task-C text)
plus the descoped eICU abstention probe; and the shared-core refactor that makes one derivation
serve all three sources.

**Does not cover.** Engine rules (HC-34..39), the Task-B renderer, the runner, or the pilot. This
spec produces *profiles*, not labels or scores. It also does not modify NHANES behaviour: the
refactor in Stage B1 is required to leave NHANES output byte-identical.

---

## 1. Two findings from the data that shape the design

Both were established by reading the files, not by reasoning from the documentation.

### 1.1 PREVENT is un-computable in MIMIC from labs alone — and must be rescued via ICD

The PREVENT base model requires smoking status. **MIMIC-IV has no structured smoking field.**
`hosp/omr`, the only outpatient-observation table, carries exactly five result families:

| `result_name` | rows (first 400k sample) |
|---|---:|
| Blood Pressure | 145,506 |
| Weight (Lbs) | 111,172 |
| BMI (kg/m2) | 98,187 |
| Height (Inches) | 41,995 |
| Blood Pressure Sitting / Standing / Lying | 830 combined |
| eGFR | 15 |

Left unhandled this is not a cosmetic gap. `prevent_10yr` would be null for **every** MIMIC row, so
every Stage-1 patient lacking diabetes, CKD or clinical CVD resolves to
`stage1_risk_indeterminate` → `ABSTAIN`. The real-EHR arm would consist mostly of abstentions and
could not support the Task-C concordance claim it exists to support.

**Resolution.** Derive smoking from ICD codes (`F17.2*` nicotine dependence, `Z87.891` personal
history of nicotine dependence, ICD-9 `305.1`) through the same crosswalk that handles the other
comorbidity flags.

**Rejected alternative — extracting smoking from the discharge note.** The discharge note is
Task-C *model-facing input*. Deriving a hidden-label component from the same text the model is
asked to read makes the Task-C label circular and violates Principle 4 (leakage discipline). It is
rejected for all three sub-cohorts, not merely for Task C, because the sub-cohorts overlap at the
patient level.

### 1.2 MIMIC closes two NHANES gaps, one of them a blocking audit finding

| Field | NHANES | MIMIC |
|---|---|---|
| `clinical_cvd` | **100% null** (`MCQ_J` not downloaded) — a Stage-1 high-risk trigger that never fires | Codeable from `diagnoses_icd` |
| `angioedema_hx` | **Zero** — genuinely unascertainable | Codeable (ICD-10 `T78.3`, ICD-9 `995.1`) |
| `bmi` | `BMX_J` | `omr` BMI rows |

Experiment Design §10 finding **F2** records that `unsafe_recommendation` is not estimable on
NHANES: only 9 of 4,806 patients carry any contraindication and all nine are hyperkalemia, with
zero pregnancy and zero angioedema. MIMIC does not fully solve this — the HC-95 stress set remains
necessary — but it is the only real-data arm that exercises the angioedema rule at all.

**Consequence for the manuscript:** the MIMIC arm is not only an ecological-validity check
(RQ4). It is the only real-data condition under which two encoded engine rules are exercised. State
this rather than presenting MIMIC purely as a robustness arm.

---

## 2. Architecture

### 2.1 Shared-core extraction (the one refactor this spec requires)

`derive.py`, `qa.py` and `validate.py` are source-agnostic by design — the walkthrough states
derivation is "computed here, not per source, so the schema is identical across
NHANES/MIMIC/eICU" — but they physically live in `pipelines/nhanes/`.

**Decision: extract `pipelines/common/{derive,qa,validate}.py`.** NHANES and MIMIC both import it;
eICU inherits it for free.

Alternatives rejected:

| Alternative | Why rejected |
|---|---|
| Duplicate derivation into `pipelines/mimic/` | This repository has already been burned by exactly this failure. `derive.bp_stage` used `Series.between(130,139)` while the engine staged through `vocab.bp_stage_scalar`; the two disagreed and silently mis-staged 56 of 4,806 rows (HC-8). A second eGFR and a second staging implementation would reintroduce that hazard deliberately |
| `pipelines.mimic` imports `pipelines.nhanes.derive` | Permanent wrong-direction dependency; MIMIC would break when NHANES changes, and eICU would inherit the same inversion |

**Acceptance gate for the refactor:** `nhanes_profiles_J.parquet` and `.csv` are byte-identical
before and after, enforced by a checksum test, and the full suite stays green. The refactor is a
move, not a rewrite; any behavioural change is a bug.

### 2.2 Module layout

```
pipelines/common/
  derive.py           egfr, bp_stage, diabetes, ckd_albuminuria, contraindications, prevent_10yr
  qa.py               range gates (reject, never clip), missingness, QA report writer
  validate.py         patient_profile.schema.json enforcement

pipelines/mimic/
  config.py           ✅ exists — EXTEND: ED + NOTE paths, lab itemids, lookback windows
  omr_bp.py           ✅ exists — per-reading BP parser, posture, bp_context="office"
  feasibility.py      ✅ exists — EXTEND: ED-linkage row + label-yield projection
  cohort.py           NEW  index-encounter selection; the three sub-cohort definitions
  labs.py             NEW  chunked itemid-filtered labevents; strict pre-admittime binding
  icd.py              NEW  ICD-9/10 -> comorbidity + contraindication + smoking crosswalk
  meds.py             NEW  ed/medrecon -> med_classes, on_bp_meds, statin_use
  notes.py            NEW  discharge-note selection + Task-C silver labels
  build_profiles.py   NEW  orchestrator -> PatientProfile + QA report

pipelines/eicu/
  config.py           NEW
  probe.py            NEW  ~500-stay abstention probe; every BP bp_context="admission"
  build_profiles.py   NEW
```

### 2.3 Heavy-table read strategy

`labevents.csv.gz` is 2.4 GB compressed (~158M rows); `note/discharge.csv.gz` is 1.1 GB. Every
other consumed table is ≤45 MB and reads with plain `read_csv(usecols=...)`, matching
`feasibility.py`.

**Decision: chunked pandas, no new dependencies.** `read_csv(chunksize=..., usecols=[...])`,
filtering by `itemid` (labs) or `hadm_id` (notes) inside the chunk loop and concatenating only
survivors. Results cache to Parquet under `data/mimic/interim/` so the slow pass runs once.

Rationale: keeps `requirements.txt` at pandas / numpy / jsonschema, keeps one idiom across the
codebase, and keeps the filter legible to a reviewer without a second query engine. The cost is one
slow single-threaded pass per heavy table, which is acceptable for a pipeline that runs rarely and
caches.

DuckDB was considered and rejected for this cycle: it would be faster, but it adds a dependency and
a second data-access idiom for a cost that the Parquet cache already absorbs. Revisit only if the
chunked pass proves unworkable in practice.

---

## 3. Cohort definitions

### 3.1 Design invariant (carry this sentence into the paper)

> **An HTN ICD code selects the patient/encounter (the anchor). It NEVER generates the label.**
> Chronic staging is derived independently from outpatient OMR taken *before* that encounter.

Anchor codes: ICD-9 `4010`/`4011`/`4019` (+ `402–404`, anchor only), ICD-10 `I10`, `I11–I13`.
**Exclude** ICD-9 `405` and ICD-10 `I15*` (secondary HTN, out of scope).

### 3.2 The three sub-cohorts

| Sub-cohort | Selection rule | Purpose | Expected N |
|---|---|---|---|
| **Primary** | Earliest anchor admission that is **both** ED-linked **and** has ≥2 prior OMR BP on distinct dates within 365 d before `admittime` | Task-B real-EHR concordance — the only cohort that can receive an initiate-vs-intensify label | ~8,921 |
| **OMR-only** | ≥2 OMR BP on distinct dates, regardless of HTN ICD | Captures undiagnosed / undertreated patients — the highest-value concordance gaps | ~138,038 |
| **Text-robustness** | Discharge notes from anchor patients, no OMR requirement | Task C extraction + error propagation | ≤110,932 — the anchor-patient ceiling; the realised N is those with a usable discharge summary and is counted in B2a |

The ED-linkage requirement on Primary is HC-26's resolution. `medrecon` is the only leakage-safe
source of `on_bp_meds`, and only 31.3% of the 28,530 PRIMARY-by-BP subjects have an ED medication
reconciliation at their index encounter. `on_bp_meds` is the variable separating *initiate* from
*intensify*; without it the engine must abstain. **28,530 is reported as a staging/Task-C cohort,
never as the decision cohort.** Relieving the N pressure with discharge meds is forbidden — those
are the answer.

A `hosp/prescriptions` fallback is acceptable **only** if restricted to orders started within 24 h
of `admittime` and pre-registered as a sensitivity analysis. It is not part of the primary
definition.

---

## 4. Field-level derivation

### 4.1 Availability matrix

| Profile field | MIMIC source | Notes |
|---|---|---|
| `source` | constant `"mimic_iv"` | |
| `age` | `patients.anchor_age + (index_year − anchor_year)` | **Not raw `anchor_age`.** Topcode 91 = ≥89; those rows fall outside PREVENT's 30–79 range anyway |
| `sex` | `patients.gender` | mapped to `"male"`/`"female"` at clean time |
| `sbp`, `dbp` | `omr` via `omr_bp.load_omr_bp` | **median** of qualifying readings |
| `bp_stage` | `common.derive` | from `vocab.BP_THRESHOLDS`; never computed locally |
| `bp_context` | constant `"office"` | OMR is outpatient; engine stages office/chronic, abstains on `admission` |
| `bp_n_readings` | count of qualifying OMR dates | provenance |
| `creatinine` | `labevents` `50912` (verify `52546`, `52024`) | → `egfr` |
| `potassium` | `labevents` `50971` | → hyperkalemia contraindication |
| `uacr` | `labevents` `51070` | **currently absent from the itemid set — CKD under-fires without it** |
| `hba1c` | `labevents` `50852` | |
| `total_chol` | `labevents` `50907` | PREVENT |
| `hdl` | `labevents` `50904` | PREVENT |
| `bmi` | `omr` BMI rows | cohort description only; not a PREVENT base-model input |
| `diabetes` | `icd.py` crosswalk **OR** HbA1c ≥6.5 (Kleene OR) | |
| `clinical_cvd` | `icd.py` crosswalk | **populated here, unlike NHANES** |
| `current_smoker` | `icd.py` crosswalk (`F17.2*`, `Z87.891`, ICD-9 `305.1`) | §1.1 |
| `told_hypertension` | anchor ICD present | trivially `True` on Primary/Text cohorts |
| `on_bp_meds` | `ed/medrecon` | **`NA` when medrecon absent — never `False`** |
| `statin_use` | `ed/medrecon` | |
| `med_classes` | `ed/medrecon.etcdescription` → engine class | `[]` only when a reconciliation exists and contains no antihypertensive |
| `prevent_10yr` | `common.derive.prevent` | computable once §1.1 supplies smoking |
| `contraindications` | hyperkalemia (K⁺ ≥5.5), angioedema_hx (`T78.3`/`995.1`), pregnancy (ICD O-codes) | |

### 4.2 ICD absence semantics — **the label-validity call for the whole MIMIC arm**

**Decision (approved 2026-08-05):**

- A billed code present → `True`.
- Code absent → `False` **only when the patient has ≥1 billed diagnosis row at the index
  encounter** (i.e. the enumeration exists).
- Patient has zero diagnosis rows → `NA`.

**Rationale.** This mirrors the complete-inventory argument already used and documented for NHANES
`med_classes`: absence within a complete enumeration is a negative, not a gap. Billing captures
active comorbidities at an admission reasonably well, and it is the standard EHR-phenotyping
reading.

**Known bias and its direction.** Where coding is incomplete, this reads unknown as negative and
biases toward **under-treatment** — the unsafe direction. That is the cost of the alternative being
unusable: absence → `NA` always would abstain nearly the whole Stage-1 cohort and yield no
benchmark items.

**Required mitigations, both mandatory, neither optional:**
1. A **sensitivity analysis under both readings** (absence→`False` vs absence→`NA`), reported in
   the QA output and in the manuscript.
2. **Flagged for HC-49 clinician adjudication** as a named assumption, not buried as an
   implementation detail.

This decision is recorded here because it is not derivable from the code and a reader must not have
to infer it.

### 4.3 Lab time-bounding (HC-27)

- Labs bound **strictly before `admittime`** — never bidirectional "nearest". A bidirectional
  nearest-lab rule would let a value drawn *during* the admission set `egfr` and the hyperkalemia
  flag, which is post-index leakage.
- **Lookback window: 365 days**, matching the BP window. A two-year-old potassium must not set a
  contraindication.
- Take the **most recent** qualifying value.
- No qualifying value → `NA` → engine abstains. Never carried forward.
- **730 d pre-registered as a sensitivity analysis.**

### 4.4 MIMIC-specific missing-data handling

- **Deid `___`** — use `valuenum`, never `value`. Never impute across a deid token.
- **Date shifts** — per-patient year shift with intervals preserved. Within-patient ordering is
  valid; absolute dates are meaningless. Never impute across a shift boundary.
- **Missing `medrecon`** → `on_bp_meds` = `NA`. Defaulting to `False` would systematically mislabel
  *intensify* cases as *initiate*.
- All global conventions in walkthrough §7 apply unchanged.

---

## 5. eICU probe (HC-21)

Descoped, deliberately, to an **abstention-calibration probe of ~500 sampled stays**. Every eICU BP
is ICU/acute, so `bp_context="admission"` and the engine abstains on chronic staging. A full
pipeline would emit ~200,000 rows carrying no decision label.

The probe's research question is narrow and worth answering: **does a model correctly refuse to
stage ICU BP?** That is a real abstention-calibration result and it needs only a small sample.

Sampling is deterministic (seeded, recorded in the manifest) so the probe is reproducible.

Note for the record: eICU *does* ship a `note.csv` (306 MB). The long-standing "eICU has no notes"
claim was factually wrong. The conclusion is unchanged — it is path/value fragments rather than
narrative prose, so it remains unsuitable for Task C.

---

## 6. Staging and gates

| Stage | Content | Acceptance gate |
|---|---|---|
| **B1** | Shared-core extraction; MIMIC config extension | NHANES Parquet + CSV byte-identical (checksum test); full suite green |
| **B2a** | **Label-yield gate** — extend `feasibility.py` with the ED-linkage row and a projection of the decision-label distribution | Counting only. Waterfall + projected label mix reported before any profile is built |
| **B2b** | Primary cohort: `cohort` → `labs` → `icd` → `meds` → `build_profiles` | Attrition waterfall reported; profiles schema-valid; QA report emitted |
| **B3** | OMR-only cohort | Same code path, different selection rule; QA report |
| **B4** | Task-C text cohort + silver-label spec (HC-54) | Note selection deduped on `note_id`, one summary per index `hadm_id`; silver-label spec written |
| **B5** | eICU abstention probe | ~500 stays, all `bp_context="admission"`, engine abstains on staging |
| **B6** | MIMIC + eICU walkthrough docs (EN/CN pair) | Written by reading the built code |

### 6.1 Why B2a exists

B2a is the MIMIC analogue of the HC-13 attrition gate and of Experiment Design finding F2. F2 was
caught *after* the NHANES corpus was built, and it invalidated a co-primary outcome. The same class
of failure is available here: if Stage-1 abstention dominates the projected label mix, the Primary
cohort cannot carry the Task-B real-EHR concordance claim, and that must be known before B2b–B4 are
built rather than after.

**B2a is counting only. It produces no profiles and no labels.**

### 6.2 Why B6 is last

The README records that a document describing an *intended* repository in the present tense
produced a phantom "1 worked rule + 9 tests" claim that cost a full spec cycle to disprove. The
NHANES walkthrough is trustworthy precisely because it was written by reading
`pipelines/nhanes/` directly. The MIMIC walkthrough gets the same treatment.

---

## 7. Testing

Per repo convention — a branch without a test does not ship.

| Module | Test focus |
|---|---|
| `common/derive` | Byte-identical NHANES output post-refactor; existing derive tests move unchanged |
| `cohort` | Index-encounter selection on a synthetic fixture; ED-linkage requirement; the ≥2-distinct-dates rule; boundary at exactly 365 d |
| `labs` | Chunked reader returns the same rows as a whole-file read on a small fixture; strict pre-`admittime` bound; no post-index value can bind |
| `icd` | ICD-9/10 crosswalk; anchor inclusion/exclusion (`405`/`I15*` excluded); **both** absence readings from §4.2 |
| `meds` | `etcdescription` → engine class; missing medrecon → `NA` not `False` |
| `notes` | Dedupe on `note_id`; one summary per index `hadm_id`; deid `___` preserved |
| `build_profiles` | Schema validation; QA report shape |

**Fixtures must be synthetic.** README's open HC-56 blocker records that
`tests/test_mimic_omr_bp.py` contains a verbatim credentialed MIMIC row, which blocks HC-90. Every
fixture written under this spec is synthetic, so this spec adds no new instance of that problem.

---

## 8. Risks

| Risk | Direction | Mitigation |
|---|---|---|
| Stage-1 abstention dominates the MIMIC label mix | Cohort cannot carry the RQ4 claim | **B2a gate before B2b** |
| ICD absence→`False` reads incomplete coding as negative | **Under-treatment (unsafe)** | Both-ways sensitivity + HC-49 adjudication (§4.2) |
| `uacr` itemid `51070` unverified | CKD under-fires | Verify in B2a; if absent, document CKD as eGFR-limb-only |
| Chunked labevents pass is slow | Developer friction only | Parquet cache under `data/mimic/interim/` |
| Silver-label noise on Task C | Overstated concordance | Frame Task C as extraction fidelity, not concordance (Master Plan risk register) |
| ICD-derived smoking is coarser than self-report | PREVENT input noise | Document as a MIMIC-vs-NHANES measurement difference; do not pool the two cohorts' PREVENT values |

---

## 9. Open items carried forward

| # | Item | Needed by |
|---|---|---|
| O1 | Verify itemids `51070` (UACR), `52546`/`52024` (creatinine) exist and carry expected units | B2a |
| O2 | Task-C silver-label spec (HC-54) — which structured fields define the silver standard | B4 |
| O3 | Whether the OMR-only cohort's undiagnosed patients need a distinct `told_hypertension` treatment | B3 |
| O4 | HC-56 — the credentialed fixture row in `test_mimic_omr_bp.py` still blocks HC-90 | Before repo goes public |

---

## 10. What this spec does not decide

- Engine rule content (HC-34..39). This spec emits profiles; the engine labels them.
- Whether MIMIC profiles enter the frozen Paper-1 benchmark or a separate release.
- The Task-C prompt design.
- Pilot / kill-criteria sequencing (HC-80), which the user has sequenced after this work.
