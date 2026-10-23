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
| **Primary** | Earliest anchor admission that **both** carries an index-stay ED medication reconciliation **and** has ≥2 prior OMR BP on distinct dates within 365 d strictly before `admittime` | Task-B real-EHR concordance — the only cohort that can receive an initiate-vs-intensify label | **8,919** (measured) |
| **OMR-only** | ≥2 OMR BP on distinct dates, regardless of HTN ICD | Captures undiagnosed / undertreated patients — the highest-value concordance gaps | ~138,038 |
| **Text-robustness** | Discharge notes from anchor patients, no OMR requirement | Task C extraction + error propagation | ≤110,932 — the anchor-patient ceiling; the realised N is those with a usable discharge summary and is counted in B2a |

The reconciliation requirement on Primary is HC-26's resolution, **as refined and signed off
2026-09-20: the rule binds on the medrecon, not on ED linkage.** `medrecon` is the only
leakage-safe source of `on_bp_meds`. Of the 28,530 PRIMARY-by-BP subjects, 9,492 (33.3%) are
ED-linked but only 8,921 (31.3%) have a reconciliation at that stay — and the 571 in between
cannot be labelled, so counting them would overstate the arm. `on_bp_meds` is the variable separating *initiate* from
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
| `creatinine` | `labevents` `50912` (+ `52546`, `52024`, both verified but rare) | → `egfr` |
| `potassium` | `labevents` `50971` | → hyperkalemia contraindication |
| `uacr` | `labevents` `51070` | ✅ **verified present** 2026-09-20, units `mg/g`. MIMIC CKD keeps BOTH limbs |
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

#### 4.3.1 Itemid verification result (closes O1)

Run 2026-09-20 by `scripts/verify_mimic_itemids.py`, which reads `d_labitems` whole and
samples the first chunk of `labevents` for units. Full output in
`data/mimic/qa/itemid_verification.json`.

| Analyte | itemid | In `d_labitems` | Label | Units observed | Rows in sample |
|---|---|---|---|---|---:|
| creatinine | `50912` | yes | Creatinine | `mg/dL` | 136,466 |
| creatinine | `52546` | yes | Creatinine | `mg/dL` | 42 |
| creatinine | `52024` | yes | Creatinine, Whole Blood | `mg/dL` | 482 |
| potassium | `50971` | yes | Potassium | `mEq/L` | 131,096 |
| uacr | `51070` | yes | Albumin/Creatinine, Urine | `mg/g` | 2,338 |
| hba1c | `50852` | yes | % Hemoglobin A1c | `%` | 9,609 |
| total_chol | `50907` | yes | Cholesterol, Total | `mg/dL` | 10,697 |
| hdl | `50904` | yes | Cholesterol, HDL | `mg/dL` | 10,496 |

**Every itemid exists and every unit matches.** Three consequences:

1. **UACR is available.** Earlier drafts — and the 2026-09-20 handoff — recorded `51070` as
   *missing*, and concluded MIMIC's `ckd_albuminuria` would collapse to the eGFR limb and
   under-fire. That is now known to be wrong: MIMIC keeps both limbs of the
   `eGFR < 60 OR UACR ≥ 30` rule, the same as NHANES. The under-treatment bias that finding
   implied does not apply, and §8's risk row is closed.
2. **Potassium reads `mEq/L`, not `mmol/L`.** Numerically identical for a monovalent ion, so
   no conversion is needed, but the loader must accept `mEq/L` rather than assert `mmol/L` —
   a naive unit assertion copied from the NHANES wording would reject every MIMIC potassium.
   Recorded here because it is a silent-failure shape, not a cosmetic difference.
3. **The two secondary creatinine itemids are real but rare** — 42 and 482 rows against
   136,466 for `50912` in the same sample. Including them is close to free and slightly
   raises coverage; they must not be treated as interchangeable with `50912` in a way that
   lets a whole-blood creatinine silently outrank a more recent serum one. Prefer by
   recency, as §4.3 already specifies, not by itemid.

The sample is the first chunk, not the full table, so these are existence-and-unit findings
rather than a coverage audit. Per-subject coverage is counted in B2a proper.

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

### 6.3 Gate result — **PASS**, recorded 2026-09-20

Produced by `scripts/mimic_label_yield_gate.py`; full output in
`data/mimic/qa/label_yield_projection.json`. Counting only — no profiles, no labels.

**Decision cohort: 8,919 subjects.** HC-26's rule as implemented: the earliest HTN-anchor
admission that both carries a medication reconciliation at its own ED stay and has ≥2 OMR BP
readings on distinct dates within 365 d strictly before `admittime`; then adults only.

The attrition reproduces the recorded figures exactly: 110,932 anchor subjects → 28,530 after
the BP rules → **9,492 ED-linked** → **8,921 whose ED stay actually carries a reconciliation**
→ 8,919 adults. Note the last step: §3.2 described the constraint as *ED linkage*, but 571 of
the ED-linked encounters have no reconciliation, and a stay without one cannot establish
`on_bp_meds` — which is the only reason the linkage is required at all. **The rule is
index-stay medrecon, not ED linkage.** Stated as ED linkage it overstates the cohort by 571.

#### Projected label yield, both absence readings (§4.2's mandatory sensitivity)

| | `prior_only` | `prior_plus_index` |
|---|---:|---:|
| n | 8,919 | 8,919 |
| **Resolvable (non-ABSTAIN)** | **6,372 (71.4%)** | **8,041 (90.2%)** |
| Abstain share | 0.286 | 0.098 |
| …med status unknown | 0 | 0 |
| …staging indeterminate | 0 | 0 |
| …**Stage-1 risk indeterminate** | **2,547** | **878** |
| PREVENT computable | 860 | 3,525 |

`prior_only` counts diagnoses from admissions strictly before the index `admittime`;
`prior_plus_index` also counts the index encounter's own codes, which is what §4.2 describes.
The first two abstention gates are zero **by construction** — the cohort rule already requires
a reconciliation and ≥2 readings — so Stage-1 risk indeterminacy is the only live gate.

**The gap between the two readings is large and is itself the finding.** 6,688 of 8,919
subjects (75%) have *no prior admission at all*, so under `prior_only` their comorbidity
enumeration does not exist and every flag is `NA` — which correctly refuses to resolve a
Stage-1 case. The 19-point difference in abstention is not a rounding choice between two
defensible conventions; it is the cost of a cohort in which three of four patients are first
seen at the index encounter. **Carry both numbers into the manuscript. Do not pick one.**
Flagged for HC-49.

#### Contraindication prevalence — audit finding F2 is answered

| Flag | MIMIC decision cohort | NHANES (F2) |
|---|---:|---|
| hyperkalemia (K⁺ ≥5.5) | **575** of 8,709 measured | 9 of 4,806 |
| angioedema history | **47** | **0** |
| pregnancy | **52** | **0** |

This is the headline result of the gate. On NHANES, `unsafe_recommendation` is not estimable:
9 patients carry any contraindication, all hyperkalemia. The MIMIC decision cohort carries
roughly 674, **including 47 angioedema and 52 pregnancy — the two flags NHANES cannot supply
at all.** §1.2's claim that MIMIC is the only real-data condition exercising two encoded engine
rules is therefore **confirmed with numbers, not withdrawn**, and the co-primary safety outcome
becomes estimable on real data for the first time. The HC-95 stress set remains necessary for
power, but it is no longer the only source.

#### Supporting distributions

- **BP stage:** stage1 2,986 · stage2 2,945 · elevated 1,741 · normal 1,247. No `NA`.
  Summarised by **mean**, per HC-23 as resolved 2026-08-08 — not median. See §6.4.
- **`on_bp_meds`:** true 6,996 · false 1,923 · unknown 0. Both arms of the initiate-versus-
  intensify distinction are well populated; this is what the ED-linkage requirement bought.
- **Lab coverage (strictly pre-`admittime`, ≤365 d):** creatinine 8,773 · potassium 8,709 ·
  hba1c 3,593 · total_chol 4,502 · hdl 4,427 · **uacr 1,409**.

**The binding constraint on PREVENT is lipids, not smoking.** §1.1 identified the missing
smoking field as the threat to `prevent_10yr`; the ICD limb fixed that, but total cholesterol
and HDL are present for only about half the cohort, so PREVENT is computable for 3,525 at
best. Widening the smoking code set would not move this. If Stage-1 yield ever needs to rise,
the lever is lipid coverage — a longer lookback for lipids specifically, pre-registered — not
the smoking crosswalk.

#### Proposed kill criteria — **for Aria's sign-off before B2b (HC-15..19) begins**

These are proposals, not decisions. Whether a given yield is *clinically* adequate is an HC-49
question, not one Aria should be asked to settle.

1. **Decision-cohort size ≥ 2,000 resolvable cases under the conservative (`prior_only`)
   reading.** Observed 6,372 — passes with 3.2× headroom. Rationale: below roughly 2,000 the
   real-EHR arm stops supporting subgroup reporting (HC-72) and becomes an anecdote.
2. **Abstain share ≤ 50% under the conservative reading.** Observed 28.6% — passes. Above
   half, the arm measures abstention behaviour rather than concordance, and RQ4 would need
   rewriting rather than running.
3. **Both `initiate` and `intensify` arms ≥ 500.** `on_bp_meds` false 1,923 / true 6,996 —
   passes. A cohort that is nearly all already-treated cannot test initiation at all.
4. **At least one contraindication flag with ≥ 30 cases.** All three clear it (575 / 47 / 52) —
   passes. This is the criterion F2 failed on NHANES, and it is the reason the MIMIC arm exists.

**Verdict: PASS on all four. Proceed to B2b.**

> ⚠️ **Read §6.5 with this.** B2b has since been built, and two figures below
> are superseded by the realised numbers — the treatment split, and the
> angioedema count, which is 6 rather than 47 under the conservative reading.

> ✅ **Signed off by Aria, 2026-09-20.** The four criteria above are approved as written and
> B2b (HC-15..19) is cleared to begin. Also decided at the same time:
> **HC-26's index rule requires an index-stay medication reconciliation, not merely ED
> linkage** — the decision cohort is 8,919, not 9,492 — and **HC-23 stands: BP is summarized
> by the mean**, with median retained as a pre-registered sensitivity analysis.

Two caveats to carry forward rather than bury:

- `age` here is `anchor_age`, not the age offset to the index admission (§4.1), so the 30–79
  PREVENT window is approximate at gate time. It moves `prevent_computable` by a small amount
  in either direction and does not affect the verdict.
- The abstention model reproduces three gates, not the engine. Once the engine's Stage-1 rules
  land, re-run against the real engine before quoting any of these numbers in the manuscript.

### 6.4 Note on the BP summary statistic

The gate summarises MIMIC OMR blood pressure by the **mean**, not the median. HC-23 was
resolved on 2026-08-08 against the guideline source: the 2025 AHA/ACC text specifies the
average of ≥2 readings throughout and never specifies a median. NHANES already computed the
mean, so this keeps both arms identical, which is the property HC-97 exists to guarantee.

Recorded here because the 2026-09-20 MIMIC handoff instructs the opposite — implement median
for MIMIC and note that the arms disagree until HC-23 lands. That instruction rests on a
premise that is no longer true: HC-23 has landed, in the other direction, on the
`ariacongdev/notion-doc-restructure` branch. `HTN-Concord_DataDictionary_and_CleaningStrategy.md`
and its `_zh` twin have now been corrected to match, which the HC-23 resolution listed as
outstanding.

### 6.5 Realised build, 2026-09-20 — and a correction to §6.3's headline

B2b is built. **8,919 profiles, schema-valid, under both absence readings**
(`data/mimic/processed/mimic_profiles_primary_{prior_only,prior_plus_index}.csv`).
Two findings supersede numbers reported at the gate.

#### Correction 1 — `on_bp_meds` and the treatment split

The gate projected 6,996 treated / 1,923 untreated. The realised figures are
**7,715 treated / 1,204 untreated / 0 unknown**. Two causes, both improvements:

* The gate classified medications by ingredient name only. The pipeline also uses
  the therapeutic-class route, which recognises antihypertensives whose names match
  no keyword rule — so more patients are correctly identified as treated.
* A reconciliation de-duplication defect was dropping real medications (see the
  HC-17 record). Fixing it moved patients from *untreated* to *treated*.

Kill criterion 3 (both arms ≥500) still passes, with 1,204 in the smaller arm.

#### Correction 2 — the angioedema claim is much weaker under the safe reading

This one matters, and §6.3 overstated it by quoting only the permissive reading.

| Contraindication | `prior_only` | `prior_plus_index` |
|---|---:|---:|
| hyperkalemia (lab-derived) | **568** | **568** |
| pregnancy | 46 | 52 |
| **angioedema history** | **6** | **47** |

Angioedema is **8× more common when index-encounter codes are counted**. Under the
leakage-safe reading only **6** patients carry a *previously documented* angioedema
history — close to NHANES's zero, and below the ≥30 threshold of kill criterion 4.

**What this means for the manuscript.** §1.2's claim that MIMIC is the only
real-data condition exercising the angioedema rule survives, but it must be stated
with the reading attached. On a strict pre-index reading the MIMIC angioedema
sample is 6, not 47, and **that is too small to estimate anything.** Kill criterion
4 passes on hyperkalemia alone under either reading; it does not pass on angioedema
under the conservative one.

This is not an argument for adopting the permissive reading. An angioedema history
coded at the index encounter is a real clinical fact about the patient — histories
do not begin at admission — so counting it is defensible in a way that counting a
new diabetes diagnosis is not. But the two cannot be waved through together, and
**whether a history code billed at the index encounter may be treated as
pre-existing is now the sharpest question on the HC-49 agenda** (§2.1 there).

The HC-95 contraindication stress set therefore remains necessary for angioedema
power, exactly as §1.2 said, and cannot be retired on the strength of the 47.

#### Other realised figures

* **BP stage:** stage1 2,986 · stage2 2,945 · elevated 1,741 · normal 1,247. No nulls.
* **Range gate:** 13 values rejected across creatinine (2), potassium (7),
  total cholesterol (3) and HDL (1). Rejected to null, never clipped.
* **Risk score computable:** 26.6% (`prior_plus_index`) / 6.5% (`prior_only`) —
  materially worse than the gate's projection, because the gate used the raw coded
  diabetes flag whereas the pipeline resolves diabetes through the Kleene OR with
  HbA1c, which returns *unknown* for a coded-negative patient with no HbA1c. See
  the HC-49 agenda §2.5; it needs a ruling rather than a code change.
* **Input provenance:** all eleven consumed files match the checksums PhysioNet
  ships with the datasets (`data/mimic/qa/input_manifest.json`).

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
| ~~`uacr` itemid `51070` unverified~~ | ~~CKD under-fires~~ | **Closed 2026-09-20: `51070` exists and carries `mg/g`.** MIMIC CKD retains the albuminuria limb, so it does not under-fire relative to NHANES |
| Chunked labevents pass is slow | Developer friction only | Parquet cache under `data/mimic/interim/` |
| Silver-label noise on Task C | Overstated concordance | Frame Task C as extraction fidelity, not concordance (Master Plan risk register) |
| ICD-derived smoking is coarser than self-report | PREVENT input noise | Document as a MIMIC-vs-NHANES measurement difference; do not pool the two cohorts' PREVENT values |

---

## 9. Open items carried forward

| # | Item | Needed by |
|---|---|---|
| ~~O1~~ | ✅ **Closed 2026-09-20.** All eight configured itemids exist in `d_labitems` and every observed unit matches expectation — see §4.3.1 | ~~B2a~~ |
| O2 | Task-C silver-label spec (HC-54) — which structured fields define the silver standard | B4 |
| O3 | Whether the OMR-only cohort's undiagnosed patients need a distinct `told_hypertension` treatment | B3 |
| O4 | HC-56 — the credentialed fixture row in `test_mimic_omr_bp.py` still blocks HC-90 | Before repo goes public |

---

## 10. What this spec does not decide

- Engine rule content (HC-34..39). This spec emits profiles; the engine labels them.
- Whether MIMIC profiles enter the frozen Paper-1 benchmark or a separate release.
- The Task-C prompt design.
- Pilot / kill-criteria sequencing (HC-80), which the user has sequenced after this work.
