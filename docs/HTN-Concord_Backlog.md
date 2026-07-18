# HTN-Concord — Epics & Tickets (backlog)

The executable breakdown of `HTN-Concord_Master_Plan.md`: 8 epics (= phases) → tickets with acceptance
criteria, dependencies, and size (S/M/L). Status: ✅ done · 🟡 in progress · ⬜ todo · 🔒 blocked.
IDs are stable (`HC-n`).

> ⚠️ **This file is NOT the source of truth (corrected 2026-07-18).** Live tracking is already in **Linear
> (GAI board, authoritative)** and mirrored in the **Notion Progress Tracker**. This markdown copy is a third
> tracker that has already drifted from both — it said "23 tests", Linear said "28", this warning itself then
> said "113", and the suite was actually at 123. **That is the whole argument against hardcoding counts: even
> the sentence warning about stale counts went stale.** Run `pytest -q`. Treat this file as a snapshot;
> update Linear + Notion on every change, and regenerate or delete it rather than hand-editing.
>
> **Tracker reconciliation (2026-07-18).** All three trackers now carry the same ticket set. Previously:
> HC-9/27/44/45 existed in Notion but not Linear; HC-23/29/43/46/47/48 existed only in this file. HC-8b is
> **not** a separate ticket — both derive.py bugs are folded into HC-8. HC-4a/HC-4b are sub-parts of HC-4,
> not standalone IDs.

**Critical path (revised 2026-07-18):** HC-7 (git) → HC-8 (CKD fix ✅) → HC-42 (DecisionBuilder refactor,
*before* HC-34) → HC-34..39 (engine) + HC-14..19 (MIMIC, parallel) → HC-5/HC-39 (designed jointly) →
HC-50 → HC-53 → HC-60 → HC-70 → **HC-80 (pilot/kill-gate)**.

---

## EPIC E1 — Foundations & canonical contracts  🟡
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-1 | `patient_profile.schema.json` contract | schema exists; covers every data-dictionary §6 field; enums for stage/sex/context | — | S | ✅ |
| HC-2 | In-pipeline schema validation | every emitted row validated before write; fails loudly | HC-1 | S | ✅ |
| HC-3 | **Shared controlled-vocab module** | one importable module for med classes / comorbidity / contraindication / ICD anchor sets; NHANES pipeline + engine both import it (kills drift before MIMIC) | — | M | ✅ |
| HC-4 | Test harness + CI ✅ | `pytest` green locally (run `pytest -q` — **do not hardcode a count here**). ✅ **CI live and verified green 2026-07-18** on `github.com/AriaCong/htn-concord` (**private**). `.github/workflows/ci.yml`: pytest on push/PR, pinned Python 3.12, collection-integrity gate + `--strict-markers --strict-config` + collected-count published to the run summary. Two consecutive green runs; first = `29642244912`, all 8 steps succeeded, 123 collected / 123 passed on Python 3.12.13, matching local. Badge renders for collaborators only while the repo is private. **CI must fail the build on pytest *collection* errors** — a committed test importing a not-yet-written module aborts the whole suite, making "tests pass" unverifiable everywhere else | — | S | ✅ |
| HC-5 | `llm_output.schema.json` (ModelRecommendation) | structured fields enabling deterministic trace scoring; validates a hand example | **HC-39** (design jointly) | ~~S~~ **M** | ⬜ |
| HC-6 | Repo hygiene | pinned deps (✅), lockfile, `pyproject`, raw-input SHA256 manifest | — | S | 🟡 |
| HC-7 | **`git init` + `.gitignore` + tagged baseline** | repo under version control; `Data/` and credentialed sources gitignored | — | S | ✅ (`d94b5d9`, tag `baseline-2026-07-18`) |
| HC-9 | Run-manifest emitter | git SHA + input/output SHA256 + resolved config + row counts per pipeline run | HC-7 | S | ⬜ |
| HC-29 | Split facts/labels into separate artifacts | model-facing facts and hidden labels emitted as physically separate artifacts | HC-1 | M | ⬜ |
| HC-56 | **Real MIMIC row in a committed test fixture** | fixture contains no verbatim credentialed data; determination recorded in the README. **Blocks HC-90** | — | S | ⬜ |

## EPIC E2 — Data cleaning: all sources → PatientProfile  🟡
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-10 | NHANES pipeline | 4,806 profiles, schema-valid, QA report (✅ built + review fixes applied) | HC-1 | L | ✅ |
| HC-11 | NHANES NCHS linked-mortality parser (Task D) | fixed-width `.dat` parsed; MORTSTAT/PERMTH joined on SEQN | HC-10 | M | ⬜ |
| HC-12 | NHANES `P_` pooled-cycle run | `NHANES_CYCLE=P_pre_pandemic` produces valid profiles w/ WTMECPRP | HC-10 | S | ⬜ |
| HC-13 | **MIMIC feasibility / attrition gate (counting only)** | yield query + attrition waterfall for anchor→≥2 prior OMR; decide v1 vs 730d/≥1 fallback | HC-3 | M | ✅ (BP rules viable: 28,530 — **but the real *decision* cohort is ~8,921 (31.3%)**, the subset with `ed/medrecon`, the only leakage-safe `on_bp_meds` source; see HC-26) |
| HC-14 | MIMIC OMR BP parser + context flag | parse `"SBP/DBP"`; posture handling; chronic/office/admission flag on every row | HC-13 | M | ✅ (`pipelines/mimic/omr_bp.py`, 30 tests) |
| HC-15 | MIMIC labevents loader + eGFR | itemid-filtered load (Cr=50912,K=50971); `valuenum`; nearest-to-index; eGFR derived | HC-13 | M | ⬜ |
| HC-16 | MIMIC ICD-9/10 comorbidity+contraindication crosswalk | one crosswalk → diabetes/CKD/angioedema/pregnancy flags; time-bounded before admittime | HC-3 | M | ⬜ |
| HC-17 | MIMIC pre-index med reconciliation | home meds from `ed/medrecon` (never discharge); `etcdescription`→class | HC-3,HC-20 | M | ⬜ |
| HC-18 | MIMIC cohort builder (3 sub-cohorts) | Primary / OMR-only / Text-robustness emitted; earliest-anchor; schema-valid | HC-14..17 | L | ⬜ |
| HC-19 | MIMIC Task-C notes + silver labels | discharge-note selection; silver labels from dx+labs+medrecon; hand-validate a sample | HC-18 | M | ⬜ |
| HC-20 | MIMIC-ED pipeline | medrecon class sets; triage/vitals acute-context; edstays join | HC-1 | M | ⬜ |
| HC-21 | eICU pipeline — **descope** | ~~full pipeline~~ → **~500-stay abstention-calibration probe** only (does a model correctly refuse to stage ICU BP?). Every eICU BP is acute, so a full build emits ~200k rows with no decision label. NB: eICU *does* ship `note.csv` (306 MB), but it is path/value fragments, not narrative — still no Task C | HC-3 | S | ⬜ |
| HC-22 | Zigong HF light clean — **recommended DROP** | 2,008 Chinese CHF inpatients; no antihypertensive-decision framing, no notes, not primary HTN. The China-guideline disagreement check is better served by the ESC-2024 comparator (HC-41) on real cohort data | — | S | ⬜ |

## EPIC E3 — Deterministic Guideline Engine (Aria hand-writes rules)  🟡
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-30 | **PREVENT scaffold** | pure module: input assembly (+statin), age 30–79 gate, unit conversion, documented functional form, coefficients placeholder, tests; returns None until coeffs filled | HC-10 | M | ✅ (this) |
| HC-31 | **PREVENT coefficients + validation** | transcribe Khan 2024 sex-specific coeffs; reproduce a published check-case risk; enable | HC-30 | M | ✅ (reproduces Table S12A exactly) |
| HC-32 | BP staging rule module + tests | cited engine rule wrapping staging; boundary tests | HC-3 | S | ✅ (`engine/rules/aha_acc_2025/staging.py`) |
| HC-33 | Initiation/intensification rule | consumes PREVENT ≥7.5% gate + three-valued abstention; Stage-1 risk-based (age via PREVENT, not standalone); NaN/numpy-safe | HC-31 | M | ✅ (built 2026-07-18 from scratch; the prior "exists (9 tests)" note was inaccurate) |
| HC-34 | First-line class selection (race-neutral) | thiazide/ACEI/ARB/DHP-CCB; single-pill combo preference; tests | HC-3 | M | ⬜ |
| HC-35 | Comorbidity modifiers | **CKD = eGFR <60 *OR* UACR ≥30 mg/g** (an OR, not an AND — KDIGO and the guideline's own wording) → ACEI/ARB preferred; tested/cited. Rename `ckd_albuminuria` → `ckd`. Contraindications outrank this preference. MIMIC needs `labevents` itemid 51070 for UACR | HC-34 | S | ⬜ |
| HC-36 | Contraindication rules | pregnancy/angioedema/K≥5.5 avoid logic; tested/cited | HC-3 | M | ⬜ |
| HC-37 | Abstention logic | NA input or admission-context BP → ABSTAIN/not_encoded; tests | HC-32,36 | S | ⬜ |
| HC-38 | Citation linker | every decision → guideline anchor id | **HC-44** (not HC-33..37 — the anchors must be mapped to printed sections first; the old dependency was wrong) | S | ⬜ |
| HC-39 | Reasoning-trace emitter | canonical trace for `trace_concordance` | HC-33..37 | M | ⬜ |
| HC-40 | MedQA/USMLE HTN sanity set | curated HTN items pass | HC-33..37 | S | ⬜ |
| HC-41 | ESC 2024 module + disagreement report | separate `evaluate()`; AHA-vs-ESC divergence quantified | HC-33..38 | L | ⬜ |

## EPIC E4 — Task construction (Aria hand-writes renderer)  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-50 | Vignette renderer (3 levels) | `render(profile, level, seed)`; facts-only; deterministic | HC-18/HC-10 | L | ⬜ |
| HC-51 | Distractor library | hand-authored, once-validated; family-hx vs patient-fact traps | HC-50 | M | ⬜ |
| HC-52 | Task A builder | clean profile → engine label | HC-33..38 | S | ⬜ |
| HC-53 | Task B builder + leakage audit | rendered vignette → hidden label; no label tokens in text | HC-50,51 | M | ⬜ |
| HC-54 | Task C builder | note → extract → silver score → engine error-propagation | HC-19 | M | ⬜ |
| HC-55 | Task D linkage | concordance ↔ NHANES mortality / MIMIC dod | HC-11 | S | ⬜ |

## EPIC E5 — Model harness  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-60 | JSON-mode runner | emits `llm_output.schema.json`; deterministic replay | HC-5 | M | ⬜ |
| HC-61 | Model adapters | ≥1 frontier + ≥1 open-weight | HC-60 | S | ⬜ |
| HC-62 | Conditions | vanilla / naive-RAG / guideline-graph | HC-60 | M | ⬜ |
| HC-63 | Repro infra | seeds, logging, caching, cost/latency capture | HC-60 | S | ⬜ |

## EPIC E6 — Evaluation & failure-mode audit  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-70 | Metrics | all 9 plan metrics; reproduces hand-scored gold set | HC-52..54 | M | ⬜ |
| HC-71 | Failure-mode classifier | each miss tagged extraction/reasoning/citation | HC-70 | M | ⬜ |
| HC-72 | Subgroup + difficulty reporting | per sex/age/comorbidity × level | HC-70 | S | ⬜ |

## EPIC E7 — Experiments  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-80 | **Pilot spike + kill-criteria** | 20 vignettes × 3 levels; 2 models; per-failure-mode table; go/no-go | HC-53,60,70 | M | ⬜ |
| HC-81 | RQ1/RQ2/RQ3 full runs | reproducibility, failure localization, graph-vs-baselines | HC-80 | L | ⬜ |
| HC-82 | Task D plausibility | concordance↔mortality association (never causal) | HC-55,70 | S | ⬜ |

## EPIC E8 — Writing & release  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-90 | Open-source engine + benchmark | reproducible release w/ manifest, checksums, QA | HC-81 | M | ⬜ |
| HC-91 | Paper(s) | 1 flagship vs benchmark+method split (Aria's call) | HC-81 | L | ⬜ |

---

### Immediate sprint (rewritten 2026-07-18 — the previous list was five completed tickets)
1. **HC-7** `git init` + `.gitignore` + tagged baseline. No VCS exists; this blocks CI, manifests, release,
   and every stale-claim audit.
2. ~~**HC-4** CI workflow~~ — ✅ **done 2026-07-18.** Live and green on `AriaCong/htn-concord` (private);
   two consecutive successful runs, 123/123 on Python 3.12.13.
3. **HC-9** run manifest (git SHA + input/output SHA256 + resolved config) on both pipelines.
4. **HC-42** `DecisionBuilder` refactor — do this **before** HC-34, or the accumulate-then-freeze pattern
   gets duplicated across six rule modules.
5. **HC-5 + HC-39 designed jointly** — they are the contract between the engine and the LLM half; authoring
   HC-5 first means guessing the trace shape and rewriting it later.

### New tickets opened by the 2026-07-18 three-reviewer audit
| ID | Ticket | Why | Priority |
|---|---|---|---|
| HC-7 | `git init` + baseline commit | ✅ **done 2026-07-18** — commit `d94b5d9` on `main`, tagged `baseline-2026-07-18`; 51 files / 408 KB; `Data/` (~60 GB credentialed) and the copyrighted PREVENT paper excluded and verified staged-clean. **Baseline is post-audit-fix**: the HC-8 corrections predate the repo, so no pre-fix referent exists to commit and none was fabricated | P0 |
| HC-8 | Fix `derive.py` correctness bugs — **both** the `ckd_albuminuria` NA-coercion (unknown→False defeated the ABSTAIN contract; unknown 0 → 266) **and** the `bp_stage` `between()` boundary bug (voided 56/4,806 valid non-integer BPs; the profile column silently disagreed with the engine) | ✅ **done** — nulls 56 → 0, profiles re-emitted with `clinical_cvd` (30 → 31 cols), plus a boundary-grid test asserting `derive` and `vocab` staging can never diverge. *(There is no separate "HC-8b" ticket — both bugs live under HC-8 in Linear and Notion.)* | P0 |
| HC-9 | Run-manifest emitter | artifacts had drifted from the code that produced them | P0 |
| HC-23 | Implement the decided **median** BP harmonization | every doc says median was harmonized 2026-07-18; `clean.py` still uses `mean()`, so the shipped substrate is a mean-based artifact and every quoted stage/label figure describes the mean pipeline. Benchmark-freeze action: change, re-run, re-quote in one pass | P1 |
| HC-24 | Wire `DEMO_J.RIDEXPRG` pregnancy flag | 45 pregnant rows carry no contraindication → unsafe ground-truth label once HC-36 lands | P0 |
| HC-25 | Download `MCQ_J`, populate `clinical_cvd` | trigger currently null for every NHANES row → under-treatment bias | P1 |
| HC-26 | MIMIC ED-linkage cohort decision | real decision-cohort N is ~8,921, not 28,530 | P1 |
| HC-27 | Bound MIMIC lab selection to strictly pre-`admittime` | "nearest the index encounter" is bidirectional → post-index leakage | P1 |
| HC-28 | Runtime out-of-scope guards | engine answers confidently on resistant/secondary HTN, pregnancy, ESRD, hypertensive emergency — all declared out of scope but unenforced | P1 |
| HC-29 | Split facts/labels into separate artifacts | leakage principle #4 asserted but not enforced in the data layer | P1 |
| HC-42 | `DecisionBuilder` refactor | composition seam needed before HC-34 | P1 |
| HC-43 | `guideline` field + registry dispatch in `evaluate()` | free now, invasive after HC-41 | P1 |
| HC-44 | Acquire guideline PDF; map anchors → printed sections | hard prerequisite for HC-38 and the `citation_support` metric | P1 |
| HC-45 | Engine integration run over all profiles + abstention report | Phase-3 acceptance gate had no ticket; would have caught HC-8 | P1 |
| HC-46 | Leakage-audit lint (forbidden-token scanner) | referenced in HC-53's acceptance but never a deliverable | P2 |
| HC-47 | Response cache + transcript store | makes analysis reproducible despite non-deterministic inference | P2 |
| HC-48 | Prompt-template versioning + hashing | unversioned prompt edits silently invalidate prior runs | P2 |
| HC-56 | Real MIMIC row in committed test fixture | `tests/test_mimic_omr_bp.py` embeds `10000032,2180-04-27,1,Blood Pressure,110/65`, present **verbatim** in `omr.csv.gz`. PhysioNet's DUA forbids redistribution — contained while the repo is private, **blocks HC-90**. Either license-clear it as ODbL demo data or replace with synthetic values | P1 |
| HC-49 | Clinician face-validity + adjudication of 150–200 cases | "no clinician in the loop" is not survivable at review as currently framed | **P0 for Paper 1** |
