# HTN-Concord — Master Execution Plan (data → profiles → engine → models → evaluation)

Single source of truth for *what gets built, in what order, and when it's "done."* Sequenced so
every phase consumes only outputs that already exist. Companion docs:
`HTN-Concord_DataDictionary_and_CleaningStrategy.md` (field-level spec) and the Notion Consolidated Plan
(scientific claim, tasks, metrics). Scope held to the plan's line: **adult primary (essential) hypertension,
initiation + intensification, + high-value contraindications** (pregnancy, angioedema history, hyperkalemia
K⁺ ≥5.5 mmol/L).

> ⚠️ **Corrected 2026-07-18 — reduced eGFR is NOT a contraindication.** Earlier versions of this line read
> "K⁺/eGFR". Low eGFR is the *opposite* of a contraindication to ACEI/ARB: the guideline **prefers** ACEI/ARB
> at eGFR <60 to slow kidney progression, and withdrawal below 30 confers no benefit (STOP-ACEi, NEJM 2022).
> eGFR belongs in two other places — as a **comorbidity modifier** (eGFR <60 → prefer ACEI/ARB, HC-35) and as
> a **monitoring requirement** — never in a contraindication list. `vocab.CONTRAINDICATION_FLAGS` already
> omits it correctly; only the prose was wrong. Fix this before HC-36 is implemented from it, or the engine
> will score guideline-concordant model answers as unsafe.

Status legend: ✅ done · 🟡 in progress · ⬜ not started · 🔒 blocked on a dependency.

---

## 0. Principles that constrain every phase (do not violate)
1. **Clinician-free deterministic ground truth.** Labels come from the engine, never an LLM judge. Any case
   the engine can't resolve → `ABSTAIN` + `not_encoded`, never a guess.
2. **Aria hand-writes the guideline rules; Claude scaffolds everything around them** (pipelines, schema,
   renderer, runner, evaluator, infra). Preserves the "I wrote the medicine" defensibility.
3. **One canonical `PatientProfile` schema.** Every dataset collapses to it; downstream code never branches
   on data source.
4. **Leakage discipline.** The cleaned structured row is the *hidden label*. The LLM only ever sees a rendered
   vignette (Task B) or raw note (Task C). Label columns stay physically separate from any model-facing text.
5. **Reproducibility.** Deterministic pipelines, pinned versions, checksummed inputs, a QA report per dataset,
   no manual edits to data.
6. **Guidelines encoded as separate modules** (AHA/ACC 2025 primary; ESC 2024 comparator). Disagreement is
   *reported*, never merged.

---

## Phase 1 — Foundations & canonical schema  🟡
**Goal:** lock the contracts everything else depends on, so pipelines and engine can be built in parallel.

| Deliverable | Status | Notes |
|---|---|---|
| `schemas/patient_profile.schema.json` | ✅ (HC-1) | verified present in the working tree 2026-07-18; the hidden-label row |
| `schemas/llm_output.schema.json` | ⬜ (HC-5, not started) | structured fields → deterministic trace scoring; file does NOT exist yet — gates the Phase-5 runner. *(Notion pilot note wrongly marked this done; corrected 2026-07-18.)* **Re-sized S → M and made dependent on HC-39:** it defines one half of every metric comparison, so authoring it before the reasoning-trace format means guessing the trace shape and rewriting it after transcripts exist |
| Repo layout + `requirements.txt` + env conventions | 🟡 | `htn-concord/` exists; pin versions, add `pyproject`/lockfile. **No version control exists at all (HC-7, P0)** — no `.git` anywhere |
| `docs/` data dictionary + this plan | ✅ | maintained in English *and* Chinese (`*_zh.md`); update both together |
| Controlled vocabularies (engine med classes, comorbidity flags, contraindication flags, ICD sets) | ✅ (HC-3) | `htn-concord/vocab.py` — pipelines and engine both import it. *(This row said ⬜ until 2026-07-18 while Linear and Notion both had HC-3 Done.)* |

**Acceptance gate:** a hand-written `PatientProfile` example validates against the schema, and the med-class /
comorbidity / contraindication vocabularies are frozen in one importable module.

---

## Phase 2 — Data cleaning: every dataset → `PatientProfile`  🟡
Each source is an independent sub-pipeline with the same output contract and its own QA report. Order chosen
by value and cleanliness (NHANES first — largest, cleanest, drives most tasks).

### 2.1 NHANES 2017–2018 (cycle J) — primary substrate  ✅ (PREVENT done, HC-31)
- Pipeline built and run: `pipelines/nhanes/` → **4,806 adult profiles**, schema-validated, QA report emitted.
- **Verification-driven fixes applied** (DS + AI-engineer review, 2026-07): missing categoricals now preserve
  `NA` (engine can ABSTAIN) instead of coercing to `False`; combination pills classify to *all* component
  classes; drug false positives removed; range-gate runs before derivation; list columns JSON-encoded
  (lossless CSV); `patient_profile.schema.json` contract + in-pipeline validation added.
- **Correctness fixes applied 2026-07-18** (three-reviewer audit). `derive.bp_stage` used
  `Series.between(130,139)`, voiding **56 of 4,806** valid non-integer mean BPs to `NA` while the engine staged
  them correctly via `vocab.bp_stage_scalar` — the profile column silently disagreed with the engine, which
  would have mis-scored `staging_correct`. Now mirrors the scalar rule (nulls 56 → 0).
  `derive.ckd_albuminuria` used `.fillna(False)`, laundering unknown kidney status into known-negative and
  defeating the ABSTAIN contract; now Kleene OR (unknown 0 → 266, 5.5%). Profiles re-emitted **with**
  `clinical_cvd` (30 → 31 columns); the previous CSV predated the HC-33 schema change.
- **Post-fix labels over 4,806 profiles:** lifestyle_only 2,545 · intensify 857 · initiate 751 ·
  at_goal_continue 509 · **abstain 144** (stage1_risk_indeterminate 132, med_status_unknown 12). BP stages:
  normal 2,073 · elevated 674 · stage 1 975 · stage 2 1,084 (**stage 1+2 = 42.8%**, unweighted sample
  description — survey weights are carried but deliberately not applied to per-row labels).
- **Test suite: run `pytest -q`.** Do not quote a count here. Nine different numbers
  (9 / 23 / 28 / 37 / 46 / 83 / 84 / 113 / 123) have circulated across these documents and every one went
  stale within days; this line itself said "113" while the suite was at 123. A CI badge (HC-4) replaces
  hand-synced counts.
- **Remaining:** NCHS linked-mortality parser (Task D, HC-11); document single-measurement CKD/diabetes
  over-trigger as a known upward bias on the initiation label; **implement the already-decided median BP
  harmonization — `clean.py` still uses `mean()` (HC-23)**; wire the pregnancy flag (HC-24) and
  `clinical_cvd` via `MCQ_J` (HC-25); decide "discard BP reading #1"; optional `P_` pooled-cycle run.
  *(PREVENT is done — HC-31, with the statin input and age-30–79 gate; this line previously listed it as
  outstanding.)*

### 2.2 MIMIC-IV 3.1 (+ Note 2.2) — primary real-EHR  ⬜
**Design invariant (write this in the paper):** an HTN ICD identifies the *patient/encounter* (the anchor);
chronic BP staging is derived independently from outpatient OMR taken **before** that encounter. ICD selects
patients, never generates the label.

- **Tables:** `hosp/omr` (outpatient BP string `"120/80"` → parse; posture variants), `hosp/labevents`
  (itemid-filtered load: Cr=50912, K=50971; use `valuenum`, table is 2.4 GB), `hosp/diagnoses_icd`
  (ICD-9/10 crosswalk), `hosp/patients` (`dod`, age topcode 91), `hosp/admissions`
  (`hospital_expire_flag`), `note/discharge` (Task-C text).
- **Anchor code set:** include ICD-9 `4010/4011/4019` (+`402–404` anchor-only) / ICD-10 `I10`,`I11–I13`;
  **exclude** ICD-9 `405` / ICD-10 `I15` (secondary HTN, out of scope).

- **2.2a — FEASIBILITY / ATTRITION GATE FIRST (counting only, no modeling).** Before locking the cohort,
  run a yield query: how many subjects survive each rule (anchor encounter → ≥2 prior OMR reads on distinct
  dates within 365 d). Many patients' first MIMIC appearance *is* the HTN encounter, so they have no prior
  OMR and drop — report the **attrition waterfall**. If N too small, adopt the pre-registered fallback
  (730-day / ≥1 reading) for the primary and keep 365-day/≥2 as a sensitivity. *This gate decides the rules
  below; do not skip it.*

- **Cohort rules (v1, leakage-safe):** index = **earliest** anchor encounter with qualifying prior OMR
  (reduces treatment-evolution bias); OMR is the **only** chronic BP source; OMR must be **before** the index
  admittime and within 365 d; require **≥2 readings on distinct dates**, use **median** SBP/DBP; current meds
  = **pre-encounter home meds** (`ed/medrecon`/admission reconciliation), **never discharge meds** (leaks the
  decision); comorbidities/contraindications from `diagnoses_icd`+`labevents` (time-bounded before admittime),
  **not** from the anchor code; ED/inpatient BP only for hypertensive-urgency add-ons, never chronic staging.
- **⚠️ CRITICAL (found 2026-07-18) — the real decision-cohort N is ~8,921, not 28,530.** The feasibility gate
  counted patients surviving the *BP* rules only. But the plan also mandates that current meds come from
  pre-encounter home meds (`ed/medrecon`), never discharge meds — and **only 8,921 of the 28,530 PRIMARY
  subjects (31.3%) have an ED medication reconciliation at their index encounter**. `on_bp_meds` is the
  variable that separates *initiate* from *intensify*; without it the engine must ABSTAIN. So two-thirds of
  the headline cohort cannot receive the primary decision label. **Resolution (recommended):** redefine the
  index encounter as *the earliest anchor admission that is both ED-linked and has ≥2 prior OMR readings on
  distinct dates within 365 days* — one honest cohort of ~8,921, still ample for the benchmark. Keep 28,530
  as a separately-reported **staging/Task-C** cohort. Do **not** relieve the N pressure with discharge meds.
  A `hosp/prescriptions` fallback is acceptable *only* if restricted to orders started within 24 h of
  `admittime` and pre-registered as a sensitivity analysis.
- **Three sub-cohorts produced:** **Primary** (anchor + qualifying prior OMR → main Task-B real-EHR
  concordance); **OMR-only** (qualifying OMR regardless of HTN ICD → captures undiagnosed/undertreated, the
  highest-value concordance gaps); **Text-robustness** (discharge notes from anchor patients, no OMR needed →
  Task C extraction + error propagation).
- **Steps:** feasibility gate → cohort selection (earliest anchor) → OMR BP parser with chronic/acute
  **context flag** → itemid-filtered labs → ICD→comorbidity/contraindication crosswalk → pre-index med
  reconciliation → discharge-note selection → derive shared fields → schema-validate → QA report.
- **Acceptance gate:** attrition waterfall reported; all three sub-cohorts emitted; profiles validate against
  `patient_profile.schema.json`; silver-label spec for Task C defined; context flag + pre-index leakage rules
  enforced on every BP/med row.

### 2.3 MIMIC-IV-ED 2.2 — current meds + hypertensive urgency  ⬜
- `ed/medrecon` (`etcdescription` = therapeutic class → engine class), `ed/triage`/`ed/vitalsign` (acute BP →
  `context=admission`, engine abstains on chronic staging), `ed/edstays` (join spine). Feeds 2.2's med list.

### 2.4 eICU-CRD 2.0 — **descope to an abstention probe** (HC-21)  ⬜
- `patient` (age string ">89" topcode → 90), `pastHistory`, `diagnosis` (ICD-9/10 comma-joined), `admissionDrug`,
  `lab` (unit-check), `apachePatientResult`. **All BP acute** → structured-only, engine abstains on staging.
- ⚠️ **Correction (2026-07-18): eICU *does* ship a `note.csv` (306 MB)** — the long-standing "no notes" claim
  was factually wrong. The conclusion still holds: it is path/value fragments, not narrative prose, so it
  remains unsuitable for Task C.
- **Recommended descope.** Because every eICU BP is ICU/acute, the engine abstains on chronic staging — the
  headline decision. A full pipeline would emit ~200k rows carrying no decision label. Keep eICU only as a
  small **abstention-calibration probe** (~500 sampled stays: does a model correctly *refuse* to stage ICU
  BP?), not as a second full substrate.

### 2.5 Zigong HF 1.3 — **recommended for outright removal** (HC-22)  ⬜
- `dat.csv` (**2,008**×167, ships a data dictionary; verified against the file 2026-07-18).
- **Recommended cut.** 2,008 Chinese CHF inpatients with no antihypertensive-decision framing, no notes, and
  not primary hypertension. The China-guideline disagreement check it was meant to serve is better served by
  the ESC-2024 comparator (HC-41) run on real cohort data. Drop HC-22 rather than carry a fifth source.

**Phase-2 acceptance gate:** every in-scope source emits a schema-valid `PatientProfile` table + a QA report
(row counts, missingness, range violations, unit assertions, BP-stage distribution). Cross-source column
audit passes (identical names/types/units).

---

## Phase 3 — Deterministic Guideline Engine (the labels)  🟡  *(Aria hand-writes rules)*
**Goal:** a pure function `PatientProfile → {decision, staging, drug classes, contraindications, citations,
canonical reasoning trace, abstain?}`, every branch unit-tested and guideline-cited.

| Component | Status | Notes |
|---|---|---|
| `engine/rules/aha_acc_2025/initiation_intensification.py` (HC-33) | ✅ (built 2026-07-18: initiation/intensification, risk-based Stage-1, three-valued abstention, NaN/numpy-safe) | the worked reference pattern |
| PREVENT 10-yr risk model (base equations, Khan 2024) | ✅ (HC-31) | coefficients transcribed from Khan 2024 Suppl. Table S12A; reproduces the paper's worked example exactly (W 14.684% / M 16.317%); `pipelines/nhanes/prevent.py`. Stage-1 ≥7.5% label now computable |
| BP staging rule module (HC-32) | ✅ | `engine/rules/aha_acc_2025/staging.py` wraps `vocab.bp_stage_scalar` as a cited rule + boundary tests |
| Drug-class first-line selection (thiazide/ACEI/ARB/DHP-CCB, race-neutral) | ⬜ | |
| Comorbidity modifiers (CKD → ACEI/ARB preferred) | ⬜ | **CKD = eGFR <60 *OR* UACR ≥30 mg/g** (KDIGO; the guideline's own phrasing is an **OR**, not an AND). The code is right; the old "CKD+albuminuria" prose was wrong |
| Contraindication rules | ⬜ | **pregnancy** → avoid ACEI/ARB/direct-renin-inhibitor/MRA/atenolol; permitted agents are labetalol, nifedipine ER, methyldopa — and since hypertensive pregnancy management is out of scope the engine should **ABSTAIN**, emitting flags for scoring only. **angioedema hx** → ACEI absolutely contraindicated lifelong; **ARB also excluded** as first choice (cross-reactivity ~2–10%) — the old spec omitted the ARB consequence. **K⁺ ≥5.5** → exclude ACEI/ARB/MRA; **K⁺ 5.0–5.4 is NOT a contraindication** (monitor only — flagging it would score correct model answers as unsafe); **K⁺ ≥6.0** → abstain. Never combine ACEI+ARB |
| Abstention logic (`ABSTAIN`/`not_encoded`; acute-context BP abstains) | ⬜ | |
| Citation linker (every decision → guideline anchor) | ⬜ | |
| Canonical reasoning-trace emitter (for `trace_concordance`) | ⬜ | |
| ESC 2024 comparator module + disagreement report | ⬜ | separate; do not merge |

**Acceptance gate:** every rule branch has a passing unit test citing the guideline; MedQA/USMLE HTN items
pass as a sanity check; engine runs over all Phase-2 profiles producing labels + traces with an abstention rate
in a defensible range.

---

## Phase 4 — Task construction (vignettes + inputs + labels)  ⬜
**Goal:** turn labeled profiles into the four task datasets, enforcing leakage rules.

- **Task A — structured control.** Clean `PatientProfile` in → engine label. Lower bound; not headline.
- **Task B — narrative vignette (HEADLINE).** `renderer` turns a profile into prose exposing only *raw facts*
  (no category names, no decision verbs, no "contraindication to…"). Hand-authored, once-validated distractor
  library (e.g. "stopped lisinopril after angioedema" [sets flag] vs "her father took lisinopril" [must not
  reach profile]). Three difficulty levels. Label = engine on the hidden row.
- **Task C — real-text robustness.** MIMIC `note/discharge` in; extract HTN facts; score vs **silver labels**
  from `diagnoses_icd`+`labevents`+`medrecon`; extracted facts then feed the engine to measure error
  propagation. ICU BP → abstain; chronic BP from `omr`.
- **Task D — external plausibility.** Associate concordance with NHANES linked mortality / MIMIC `dod`.
  Plausibility only, never effectiveness (confounding by indication).

**Deliverables:** `renderer` (SPEC exists), distractor library, difficulty controller, task dataset builder,
frozen benchmark splits with checksums. **Acceptance gate:** leakage audit passes (no label-bearing tokens in
any Task-B/C input); a human spot-check of 20 rendered vignettes confirms facts-only.

---

## Phase 5 — Model harness (LLM runner)  ⬜
**Goal:** run any model over any task in strict JSON mode, reproducibly.

- JSON-mode runner emitting `llm_output.schema.json` (structured fields enable trace scoring).
- Model adapters: ≥1 frontier + ≥1 open-weight (kill-criteria comparison); vanilla LLM, naive RAG, and
  guideline-graph conditions (RQ3).
- Prompt templates versioned; temperature/seed pinned; full request/response logging; cost/latency capture;
  retry/caching. **Acceptance gate:** deterministic re-run reproduces a stored transcript; malformed JSON rate
  near zero on a smoke set.

---

## Phase 6 — Evaluation & failure-mode audit  ⬜
**Goal:** decomposition, not one number. Implement every plan metric and the RQ2 audit.

- **Metrics:** `decision_concordance`, `staging_correct`, `extraction_f1`, `contraindication_recall`,
  `contraindication_false_positive`, **`unsafe_recommendation`** (safety headline), `citation_support`,
  **`trace_concordance`**, `abstention_appropriateness`. Reported **per difficulty level** and **per subgroup**
  (sex, age band, comorbidity).
- **Failure-mode classifier (RQ2):** label each miss as BP-stage misclassification · missing comorbidity ·
  missed contraindication · wrong drug class · ignored current med · wrong initiate-vs-intensify ·
  unsupported/hallucinated citation · right answer + wrong reasoning path · over-/under-abstention. Each tagged
  extraction / reasoning / citation.
- **Acceptance gate:** evaluator reproduces hand-scored results on a small gold set; a 2-model × 3-level report
  renders end-to-end.

---

## Phase 7 — Experiments & analysis  ⬜
- **Pilot spike first (kill criteria):** 20 vignettes × 3 levels → runner → evaluator → 2-model × 3-level report.
  If `simple` and `hard` both near-ceiling, or frontier ≈ open-weight everywhere → benchmark lacks
  discriminative power; fix difficulty before scaling.
- Then: full RQ1 (engine reproducibility), RQ2 (failure localization on Task B/C), RQ3 (guideline-graph vs
  vanilla vs naive RAG on the *dominant* failure mode), Task D plausibility. Subgroup + difficulty breakdowns,
  significance/CIs, ablations.

---

## Phase 8 — Writing, artifacts, release  ⬜
- Open-source the Deterministic Guideline Engine (contribution #1) and the HTN-Concord benchmark (#2).
- Papers: 1 flagship vs benchmark+method split (Aria's call; 1–2 target). Failure-mode audit (#3) and
  reasoning-trace concordance (#4) as the differentiators vs MCQ benchmarks.
- Reproducibility appendix: data manifest, checksums, QA reports, environment lock.

---

## Dependency graph (what unblocks what)
```
P1 schema/vocab ──┬─> P2 data pipelines ──┐
                  └─> P3 engine rules ─────┼─> P4 tasks ─> P5 runner ─> P6 eval ─> P7 experiments ─> P8 writing
   PREVENT (P3) ──────> Stage-1 labels ────┘
```
- **Critical path right now (2026-07-18):** HC-7 (git) → HC-42 (DecisionBuilder, *before* HC-34) →
  HC-34..39 engine rules (HC-38 gated on HC-44) + HC-15..19 MIMIC cohort in parallel → HC-45 integration run →
  HC-5/HC-39 designed jointly → HC-50 renderer → HC-53 Task B → HC-60 runner → HC-70 metrics, converging at the
  HC-80 pilot/kill-gate. *(PREVENT/staging/HC-32/33/HC-14 are done — no longer the blockers.)* HC-49
  (clinician adjudication) runs alongside from now, since it is calendar-bound rather than code-bound.
- P2 sources are mutually independent → parallelizable after P1 vocab is frozen.
- P5/P6 can be scaffolded against Task A (structured) before Task B/C rendering is finished.

---

## Milestones
1. **M1 — Contracts frozen:** schema validated, vocabularies frozen (end of P1).
2. **M2 — All data cleaned:** every in-scope source emits schema-valid profiles + QA (end of P2).
3. **M3 — Engine complete:** all rules + PREVENT, tests green, MedQA sanity pass (end of P3).
4. **M4 — Benchmark v0:** Tasks A/B built, leakage audit passes (end of P4).
5. **M5 — Pilot verdict:** 2-model × 3-level report; kill-criteria decision (early P7).
6. **M6 — Full results:** RQ1–3 + Task D (end of P7).
7. **M7 — Submission:** paper(s) + released engine/benchmark (P8).

---

## Risk register (from Notion, made actionable)
| Risk | Mitigation | Owner |
|---|---|---|
| Engine correctness (no clinician) — **a genuine single point of failure**: the engine's output *is* the ground truth for every result in the paper, so one wrong rule silently corrupts everything downstream | every rule cites the guideline + unit-tested; ambiguity→ABSTAIN; MedQA sanity (HC-40) as a **floor, not a substitute**. **"Face-validity as future work" is not survivable at review and was removed 2026-07-18** — *"your ground truth was never checked by a doctor"* is the first thing a clinical reviewer looks for. Minimum before Paper 1 (**HC-49, P0**): ① specialist face-validation of all ~20 encoded branches; ② two clinicians blind-adjudicating 150–200 stratified cases, oversampling every abstention and contraindication-positive case, reporting Cohen's κ; ③ adversarial review of the abstention set; ④ safety audit of every synthetic contraindication vignette. **Pre-register that κ < 1.0 is expected** — clinicians genuinely disagree on low-risk Stage 1 and on adherence-vs-intensification, and that disagreement is a *finding* quantifying the irreducible ambiguity floor, not a failure. Defensible claim: *the engine is a faithful, auditable, citation-linked transcription of a published guideline*. Not defensible: *the engine is a clinician substitute* | Aria |
| PREVENT mis-implementation corrupts labels | ✅ mitigated: transcribed from Khan **2024** Suppl. Table S12A; unit-tested vs the published example (exact match); coefficients never fabricated | Aria/Claude |
| Template degeneracy (Task B) | hand-authored validated distractor library; MIMIC Task C as un-gameable anchor | Aria |
| Silver-label noise (Task C) | derive from structured tables; validate a hand sample; frame as extraction fidelity, not concordance | — |
| Coverage gaps (angioedema/RAS not in NHANES) | exercise via synthetic vignettes only | — |
| Data leakage | leakage audit in P4; label cols physically separated | Claude |
| Reproducibility drift | pinned env, checksums, QA reports, deterministic runner | Claude |

---

## Open decisions (resolve before the dependent phase)
1. **NHANES span:** cycle J only vs pooled `P_` (2017–Mar 2020). **Recommendation: freeze Paper 1 on cycle J**,
   and run the pooled `P_` as a pre-registered robustness appendix. Per-row labels never use survey weights, so
   the `WTMEC2YR`→`WTMECPRP` switch only affects Task-D/prevalence estimates. The N gain is **~1.7×, not
   "roughly double"** (9,254 → ~15,560 respondents). *Needed before final substrate freeze (P2/P7).*
2. **MIMIC index-encounter rule.** **Recommendation: earliest anchor + 365 d/≥2 OMR *plus mandatory ED
   linkage*** — one honest decision cohort of ~8,921, with 28,530 kept as a separately-reported staging/Task-C
   cohort. See §2.2 and HC-26. *Needed at P2.2.*
3. ~~**PREVENT vs PCE**~~ — **RESOLVED / LOCKED 2026-07-18: PREVENT.** The 2025 AHA/ACC guideline replaced
   the Pooled Cohort Equations with PREVENT and lowered the high-risk threshold from ≥10% (PCE, ASCVD) to
   **≥7.5% (PREVENT, *total* CVD = ASCVD + heart failure)**. PCE must not be used, and the 7.5% cut is only
   valid against the total-CVD model. Implemented as the **base** model (Khan 2024 Suppl. Table S12A).
4. **Papers:** 1 flagship vs benchmark+method split. *Needed by P8.*
5. **Discard BP reading #1?** *Needed to finalize P2.1.* Report a stage-distribution sensitivity under both.
6. **Median BP harmonization (HC-23).** *Decided* (median everywhere, 2026-07-18) but **not implemented** —
   `pipelines/nhanes/clean.py` still averages the three oscillometric readings. Because switching re-emits the
   substrate and moves every quoted stage/label figure, treat it as a benchmark-freeze action: change, re-run,
   and re-quote all downstream numbers in one pass. *Needed to finalize P2.1.*
7. **eICU and Zigong scope (HC-21 / HC-22).** Recommendation: descope eICU to a ~500-stay abstention probe and
   drop Zigong entirely. *Needed before P2 is called done.*

---

## Immediate next actions (in order, as of 2026-07-18)
*(Done since the original list: HC-3 vocab, HC-31 PREVENT, HC-32/33 staging + initiation, HC-13 MIMIC
feasibility, HC-14 OMR BP parser, HC-8 derive.py correctness fixes.)*

1. ~~**HC-7 — `git init` + `.gitignore` + tagged baseline**~~ — ✅ **done 2026-07-18.** Commit `d94b5d9` on
   `main`, tagged `baseline-2026-07-18`; 51 files / 408 KB (source, docs, tests, schema). `Data/` (~60 GB
   credentialed PhysioNet) and the copyrighted PREVENT paper are gitignored and were verified staged-clean
   before the commit. **The baseline is post-audit-fix** — the HC-8 corrections predate the repository, so
   no pre-fix referent exists and none was fabricated. **Now unblocked: HC-4 (CI), HC-9 (run manifest),
   HC-90 (release)** — and the "verified against commit `<sha>` on `<date>`" convention is finally checkable.
   *Do the CI workflow next (HC-4); it is what stops the drift from restarting.*
2. **Safety and label-validity fixes before any new rule lands:** HC-24 (wire `DEMO_J.RIDEXPRG`; 45 pregnant
   respondents currently carry an empty contraindication list — once HC-36 lands the engine could emit
   "initiate ACEI/ARB" for a pregnant patient *as ground truth*), HC-25 (`MCQ_J` → `clinical_cvd`, null for
   every row today, biasing toward under-treatment — the unsafe direction), HC-28 (runtime out-of-scope
   guards; the engine currently answers confidently on resistant/secondary HTN, ESRD and hypertensive
   emergency, all declared out of scope).
3. **HC-42 `DecisionBuilder` refactor — *before* HC-34.** `evaluate()` is a pass-through with no composition
   seam and `EngineDecision` is frozen; an afternoon now versus touching six rule modules and their tests
   afterwards. Pair with HC-43 (guideline field + registry dispatch), which is free now and invasive after
   HC-41.
4. Then the engine's remaining rules — HC-34 (drug class), HC-35 (comorbidity), HC-36 (contraindications),
   HC-37 (abstention), HC-38 (citation linker, which depends on **HC-44** — acquiring the guideline PDF and
   mapping anchors to printed sections — not on HC-33..37), HC-39 (trace emitter). Close with **HC-45**, the
   engine integration run over all profiles + abstention report; it is the Phase-3 acceptance gate and had no
   ticket, which is why HC-8 went undetected.
5. Build the **MIMIC-IV** pipeline (2.2 / HC-15..19) — largest remaining data lift, enables the Tasks B/C
   anchor. Settle HC-26 (ED linkage) and HC-27 (bound labs strictly pre-`admittime`) *before* HC-17/HC-18.
6. Author **HC-5** `llm_output.schema.json` **jointly with HC-39** — they are the contract between the engine
   and the LLM half.
7. Then the LLM half: renderer (HC-50) → Task B (HC-53) → runner (HC-60) → metrics (HC-70), converging at the
   **HC-80 pilot + kill-criteria gate** — run this end-to-end slice early to test discriminative power.
8. MIMIC-ED (2.3) in parallel. eICU (2.4) only as the descoped abstention probe; Zigong (2.5) dropped.
9. **HC-49 clinician face-validity + adjudication** — P0 *for Paper 1*, and long-lead because it depends on
   other people's calendars. Start recruiting while the engine work finishes.
