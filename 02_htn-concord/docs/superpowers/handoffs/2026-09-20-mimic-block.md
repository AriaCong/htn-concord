# Handoff — the MIMIC-IV block (14 tickets)

**Written 2026-09-20.** Operational handoff for an agent taking over the real-EHR arm.
Not a bilingual project doc: the five project docs (Master Plan, Backlog, DataDictionary,
Walkthrough, Experiment Design) are EN/CN pairs; this is internal tooling and stays English.

---

## 0. Your mission

Build the MIMIC-IV arm of HTN-Concord: 14 tickets, the largest unbuilt block in the project.
Everything downstream of it — the ecological-validity rung of the experiment, and one of the
four claimed research gaps — depends on it and on nothing else.

**Stop and get sign-off at the kill gate in §9 before building anything expensive.**

---

## 1. What the project is

HTN-Concord measures whether large language models follow the 2025 AHA/ACC hypertension
guideline when deciding **whether to start or intensify antihypertensive therapy** for one
patient.

Three things make it different from every adjacent benchmark, and all three are load-bearing:

- **The answer key is a hand-written deterministic rule engine.** Not LLM-generated, not
  expert-annotated per case, not copied from what physicians actually did (physician behaviour
  carries treatment inertia and indication confounding).
- **Scoring is deterministic pure functions.** No LLM-as-judge anywhere.
- **The same patient is rendered two ways carrying provably identical decision-relevant
  information**, so the score difference isolates "failed to read the chart" from "failed to
  reason clinically". A test enforces the information invariance on every corpus build.

Study type: a **diagnostic-accuracy-style evaluation against a computable reference standard**.
The LLM is the index test; the engine is the reference standard. The engine is an *answer key,
not a competitor* — it has no error bars, and any sentence of the form "the engine outperformed
the LLM" is a category error.

The synthetic arm is built: NHANES 2017–2018, 4,806 patients → 14,418 frozen, audited cases.
**The real-EHR arm is not. That is your job.**

---

## 2. Six principles you may not violate

From Master Plan §0. These are not style preferences.

1. **Deterministic gold standard without clinicians.** Labels come from the engine, never from
   an LLM judge. A case the engine cannot decide gets `ABSTAIN` + a `not_encoded` reason —
   never a guess.
2. **Aria hand-writes the guideline rules; you build everything around them** — pipelines,
   schemas, renderer, runner, evaluator, infrastructure. This preserves "the medical logic is
   mine" as a defensible claim in review. **You do not write or modify anything under
   `engine/rules/`.** If a MIMIC field forces a rules question, raise it; do not patch the rules.
3. **One `PatientProfile` schema.** Every dataset normalizes to it. Downstream code — engine,
   renderer, scorer — never branches on data source. If you find yourself writing
   `if source == "mimic"` below the cleaning boundary, you have broken this.
4. **Anti-leakage discipline.** The cleaned structured row is the *hidden label*. Models see
   only rendered text. Label columns and model-facing text live in physically separate files
   joined only by `case_id`.
5. **Reproducible.** Deterministic pipelines, pinned versions, input checksums, one QA report
   per dataset, never hand-edit data.
6. **Each guideline is a separate module.** Disagreements are reported, never merged.

---

## 3. Who you are working with

**Aria has no clinical background.**

This is the single most important operational fact in this document. When you hit a question
that needs clinical judgement — which ICD codes constitute angioedema history, whether a
particular lab window is clinically defensible, whether a cohort rule excludes the wrong people —
**do not ask Aria to settle it.** She cannot, and asking pushes an unqualified judgement into
the reference standard.

Instead, every time:

1. Make the **conservative** call (the one that abstains, excludes, or under-claims).
2. Implement it, with the reasoning written into the code as a comment.
3. **Flag it explicitly for HC-49** (clinician face validity + adjudication) — in the ticket, in
   the DataDictionary, and in a running list so the clinician review has an agenda.
4. Keep going. Do not block.

---

## 4. What already exists — read before you build

Work in `htn-concord/`. Run the test suite before you touch anything; it should be green on
Python 3.12.

| Path | What it is | State |
|---|---|---|
| `schemas/patient_profile.schema.json` | 31 fields. **The contract.** Your output must validate against it unchanged. | Done |
| `schemas/llm_output.schema.json` | Model answer contract | Done |
| `vocab.py` | Thresholds, drug classes, contraindication flags, **HTN ICD anchor sets**. Single source of truth — import it, never re-type a code list. | Done |
| `engine/` | Staging + initiation/intensification rules, citation registry, `TraceStep`. Drug-class selection, comorbidity modifiers, contraindication rules, out-of-scope guards are **not built**. | Partial |
| `renderer/`, `leakage.py`, `tasks/` | Vignette renderer, forbidden-token scanner, corpus builder + patient-level splits | Done |
| `runner/`, `evaluator/` | Model call harness, nine metrics | Done |
| **`pipelines/nhanes/`** | **Read this first.** Your MIMIC package mirrors its structure: `download → io → clean → derive → validate → qa → build_profiles`. | Done, 4,806 profiles |
| `pipelines/mimic/config.py` | Path/constant config | Exists |
| `pipelines/mimic/feasibility.py` | HC-13, counting only, 139 lines | Done |
| `pipelines/mimic/omr_bp.py` | HC-14 BP parser + context flag, 112 lines, 30 tests | Done |

### One trap already sitting in the tree

`pipelines/common/` **exists, is untracked by git, and contains only stale `.pyc` files dated
2026-08-07** (`__init__` and `prevent`). Someone started HC-97 — moving the shared derivation
core out of the NHANES package — and abandoned it. **HC-97 is not done.** Delete the stale
`__pycache__` before you start so it cannot confuse anyone, and do the extraction properly.

---

## 5. Your 14 tickets, in dependency order

Statuses as of 2026-09-20. Sizes from the backlog.

```
GROUND ALREADY LAID
  HC-1  PatientProfile schema  DONE ──────────────────────→ HC-20
  HC-3  shared vocab           DONE ──→ HC-13 DONE ──┬────→ HC-14 DONE
                                                     ├────→ HC-26
                                                     └────→ HC-27

WAVE 0 — six tickets, no unmet dependencies, all startable today
  HC-56  purge licensed rows from test fixtures    S   blocks HC-90 (open-sourcing)
  HC-97  extract pipelines/common                  ?   blocks HC-15..19
  HC-98  label-yield gate (counting only)          ?   blocks HC-15..19
  HC-26  index-visit rule decision                 M   blocks HC-17
  HC-27  bound labs to strictly pre-admittime      S   blocks HC-15
  HC-20  MIMIC-ED pipeline                         M   blocks HC-17

WAVE 1 — three parallel branches
  HC-15  labevents loader + eGFR      M   needs HC-27, HC-97, HC-98
  HC-16  ICD-9/10 crosswalk           M   needs HC-98
  HC-17  pre-index med reconciliation M   needs HC-20, HC-26, HC-97, HC-98

WAVE 2 — convergence
  HC-18  cohort builder, 3 sub-cohorts  L   needs HC-14 DONE, HC-15, HC-16, HC-17

WAVE 3
  HC-19  discharge-note selection + silver labels  M   needs HC-18

WAVE 4 — lives in the task epic, not the data epic
  HC-54  Task C builder  M   needs HC-19
```

**Critical path: HC-20 → HC-17 → HC-18 → HC-19 → HC-54.**

Counter-intuitive but correct: **do HC-20 before HC-15.** Labs feel like the core data, but
HC-20's only dependency is already done, and it unblocks HC-17 — and HC-17 is the bottleneck of
the entire arm, because medication reconciliation is the only non-leaking source of
`on_bp_meds`. A finished HC-15 builds no cohort without HC-17.

---

## 6. Data specifications

These are the conditions. Getting one wrong does not produce a bug — it produces a **wrong
label**, silently, and a wrong label invalidates the benchmark.

### HC-26 — index-visit rule (decide first, it sets N)

- Candidate v1 rule: **earliest HTN anchor encounter + ≥2 outpatient OMR BP readings within
  365 days + mandatory ED linkage**. Fallback under consideration: 730 days / ≥1 reading.
- One row per `subject_id`.
- HC-13 already established: the BP rule alone yields **28,530** subjects, but the genuinely
  *decidable* cohort is about **8,921 (31.3%)** — the subset with `ed/medrecon`.
- Deliverable: the rule, in code, with the attrition waterfall that justifies it.

### HC-27 — lab time window

- Take the **most recent value strictly earlier than `admittime`**, within a **pre-registered
  lookback window**.
- The old wording — "closest to the index visit" — is **bidirectional** and lets a creatinine or
  potassium drawn *during* the index admission set `egfr` and the hyperkalemia flag. That value
  is post-decision and very likely reflects the therapy being evaluated. It is post-index
  leakage and it contradicts the plan's own rule that comorbidities are time-bounded before
  `admittime`.

### HC-15 — labs + eGFR

- **Filter by `itemid` before loading.** `labevents` is 2.4 GB. Creatinine `50912`, potassium `50971`.
- Use `valuenum`, never `value` — the text column may be `___` after de-identification.
- Drop rows with null `valuenum`. Assert `valueuom` matches expectation (K in mmol/L,
  creatinine in mg/dL).
- eGFR: **CKD-EPI 2021 race-free**, identical to NHANES. Never a race-coefficient equation.
- **Two open items:** creatinine has other itemids (`52546`, `52024`) whose coverage must be
  checked; **UACR (`51070`) is missing**, and without it MIMIC's CKD has only the eGFR leg, so
  the comorbidity modifier will under-trigger. Quantify the impact; do not silently proceed.

### HC-16 — ICD crosswalk

- `diagnoses_icd` mixes **ICD-9 and ICD-10 in the same column**. Map both; check `icd_version`.
- One crosswalk → diabetes / CKD / angioedema history / pregnancy flags.
- All comorbidity determination **time-bounded before `admittime`**.
- Angioedema history (ICD-10 `T78.3*`, `D84.1`) sets the avoid-ACEI flag. This is the key
  contraindication the benchmark exists to test, and **NHANES contains zero cases of it** — so
  MIMIC is the only place it can be measured on real data.

### HC-17 — home medications (the bottleneck)

- Home meds come **only** from `ed/medrecon`.
- **Never use discharge medications. Do not prefer inpatient `prescriptions`.**
- Why: inpatient orders are written *after* the decision; discharge meds are literally the
  label. Neither can establish whether the patient arrived already on antihypertensives.
- Map `etcdescription` (therapeutic class) → engine drug classes. Deduplicate on
  `(subject_id, name, gsn)`. Collapse to one **class set** per visit.

### HC-18 — cohort

- **Include:** adult, with an HTN anchor ICD — ICD-9 `4010`/`4011`/`4019` (`402`–`404` as anchor
  only) or ICD-10 `I10`, `I11`–`I13` — **and/or** at least one OMR BP reading.
- **Exclude: ICD-9 `405` and ICD-10 `I15*` (secondary hypertension, out of scope).** An earlier
  draft of the DataDictionary wrongly listed `I15*` as *included*; the shipped code was always
  right. Import the sets from `vocab.py` rather than retyping them.
- Produce three sub-cohorts: **Primary**, **OMR-only**, **Text-robustness**.
- Output must validate against the same `patient_profile.schema.json` as NHANES.

### HC-19 / HC-20

- **HC-19 notes:** one discharge summary per index `hadm_id`, deduplicated by `note_id`; median
  roughly 10k characters. Preserve `___` placeholders **verbatim — never fabricate**. Never
  alter anything that changes clinical meaning.
- **HC-19 silver labels:** derived from `diagnoses_icd` + `labevents` + `medrecon` — **not from
  the note text**. Hand-validate a sample. This measures *extraction fidelity*, not concordance.
- **HC-20 ED:** `ed/medrecon`, `ed/triage`, `ed/vitalsign`, `ed/edstays`. Vital signs arrive as
  zero-padded float strings (`71.0000`) and need numeric conversion. **All ED blood pressures
  are acute context**, full stop.

### Cross-source derived fields — compute identically to NHANES

`sbp`/`dbp` (median of valid readings), `bp_stage`, `egfr`, `ckd` (eGFR <60 **OR** UACR ≥30 —
it is OR, not AND), `potassium` (flag at ≥5.5), `diabetes`, `on_bp_meds`, `med_classes`,
`contraindications`. **This is exactly what HC-97 exists to guarantee.**

One live inconsistency you will trip over: **every document says BP is summarized by median;
`pipelines/nhanes/clean.py` still computes the mean** (ticket HC-23). Implement **median** for
MIMIC as specified, and note in your QA report that the two arms currently disagree until HC-23
lands. Do not "fix" NHANES as a side effect — that is a benchmark-freeze-level decision that
moves every published number.

---

## 7. Traps — each of these has already caught someone

1. **Post-index leakage** — labs must be strictly pre-`admittime` (HC-27).
2. **Discharge meds are the answer** — home meds only from `ed/medrecon` (HC-17).
3. **OMR BP is a string** — `result_value` is `"SYS/DIA"`; positional variants exist; split on `/`.
4. **ICD-9 and ICD-10 are mixed** in one column.
5. **Secondary HTN must be excluded** — `405` / `I15*`. A doc once said the opposite.
6. **Age topcoding differs per source** — MIMIC 91, eICU 90, NHANES 80.
7. **`___` is a de-identification artifact** — use `valuenum`; never impute across it or across
   the date shift.
8. **Every BP row carries a context flag** — `chronic` (OMR) vs `admission` (ED/ICU/triage).
   Chronic staging uses chronic BP only; acute BP makes the engine abstain.
9. **`labevents` is 2.4 GB** — filter by itemid before loading.
10. **Missing is not False.** Three-valued logic throughout. A stray `1` must not read as `True`;
    a `NaN` must not read as low-risk. This is what makes abstention meaningful and it is the
    engine's whole defence against guessing.
11. **Never hardcode test counts in documentation.** Write "run the suite", not "277 tests pass".
12. **MIMIC is credentialed.** Raw records stay local and are never sent to an external service;
    cases are *derived and rendered*, not raw rows. Test fixtures must contain no verbatim
    licensed data — that is HC-56, and it currently blocks open-sourcing.

---

## 8. Working rules

- **Git:** never commit to `main`. Branch off the latest `main`, and **re-check which branch you
  are on immediately before committing**. The repo is currently on
  `ariacongdev/notion-doc-restructure` with untracked files present.
- **Docs are bilingual pairs.** Master Plan, Backlog, DataDictionary, Walkthrough and Experiment
  Design each have a `_zh.md` twin plus two Notion trees. **Edit both in the same commit.**
  On conflict, English wins.
- **Two synced trackers.** Linear board `Generative AI in Medical` (primary, `GAI-n` carrying
  `HC-n` in the title) and the Notion database `HTN-Concord — Progress Tracker`.
  **Update both on every piece of progress.**
- Notion writes containing shell-command-looking strings get blocked by Cloudflare. Reword the
  text; do not retry verbatim and do not wait it out.
- **Tests before implementation.** Every pipeline stage emits a QA report. Every rule-adjacent
  decision gets a test that pins it.
- Search the backlog by symptom before filing a new ticket — HC-96 was filed as a duplicate of
  HC-24 precisely because this step was skipped.

---

## 9. The kill gate — stop here for sign-off

**HC-26 + HC-98 together are a go/no-go for the whole block, and they are not currently marked
as one.** Treat them as one.

Why: HC-13 already cut 28,530 → 8,921. HC-26's index-visit rule removes another layer, and only
then does HC-98 count how many cases carry each decision label, each abstention reason, and each
contraindication.

The precedent is exact and recent. On NHANES, the corpus was built *first* and only afterwards
did the audit find that **9 of 4,806 patients carry any contraindication — all hyperkalemia,
zero pregnancy, zero angioedema** — which invalidated a co-primary safety outcome. The same
failure is fully available on MIMIC.

**Deliverable at the gate:** a counting-only report giving, for the post-HC-26 cohort, the
distribution of decision labels, abstention reasons, and contraindication flags — plus your
proposed kill criteria. **Aria signs off on the criteria before HC-15..19 begin.** Note that
whether a given yield is *clinically* adequate is an HC-49 question, not an Aria question —
propose, flag, proceed.

---

## 10. Start here

1. Run the test suite. Confirm green. Note the count for yourself; do not write it into docs.
2. Read `pipelines/nhanes/` end to end. Your package mirrors it.
3. Read `docs/HTN-Concord_DataDictionary_and_CleaningStrategy.md` §2, §3, §6, §7.
4. Delete the abandoned `pipelines/common/__pycache__`.
5. **HC-56** — small, independent, and it blocks open-sourcing. Two tickets in this backlog
   (HC-45, HC-46) were once written only into acceptance criteria and were both forgotten; do
   not let this become the third.
6. **HC-97** — extract the shared derivation core. Pure refactoring with no new science, but
   skipping it forces MIMIC to either depend on the NHANES package or duplicate derivation
   logic — and duplication lets the two arms' eGFR, CKD and PREVENT drift apart, which destroys
   the one thing the fourth research gap claims: that both arms share one schema and one engine.
7. **HC-26 + HC-98** — the kill gate. Stop for sign-off.
8. Then HC-20 and HC-27 in parallel, then HC-15 / HC-16 / HC-17, then HC-18 → HC-19 → HC-54.

Open a ticket for anything you find that is not already tracked, and mirror it to both trackers.

---

## 11. Definition of done for the block

A Task C corpus exists that:

- validates against the unmodified `patient_profile.schema.json`;
- passes the same leakage gate as Task B — forbidden-token hits zero, label-column hits zero,
  enforced as a **build gate**, not an after-the-fact report;
- is split at **patient** level, disjoint, using the same stable hash-threshold method, so
  adding MIMIC does not move any existing NHANES patient between splits;
- carries silver labels derived from structured tables and hand-validated on a sample;
- ships a QA report and an input checksum manifest;
- comes with a documented list of every conservative call you made, addressed to HC-49.
