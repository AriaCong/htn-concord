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

**Critical path (revised 2026-07-18):** ~~HC-7 (git ✅)~~ → HC-8 (CKD fix ✅) → HC-42 (DecisionBuilder refactor,
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
| HC-5 | `llm_output.schema.json` (ModelRecommendation) | structured fields enabling deterministic trace scoring; validates a hand example. ✅ **Done 2026-07-19**: schema + committed hand example (the Master-Plan Task-B vignette) + drift-guard tests pinning the `decision` enum to `engine.types.Decision`, med-class/contraindication enums to `vocab.py`, extracted field names to `patient_profile.schema.json`, and the trace-step shape to the engine's `TraceStep` — which is how the "design jointly with HC-39" constraint was satisfied: the trace shape is *taken from the engine*, and HC-39's emitter is now contractually bound to it by test | **HC-39** (design jointly) | ~~S~~ **M** | ✅ |
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
| HC-96 | ~~Wire `RIDEXPRG` pregnancy~~ **DUPLICATE of HC-24** | Raised during the HC-92 audit before HC-24 was found; the work is real and done, recorded under **HC-24**. Two corrections: the ticket was redundant (search the backlog by symptom before filing), and an earlier note here claimed the abstain-on-pregnancy scope call was made without clinical input — **wrong**, it was pre-specified in the Master Plan contraindication table and HC-36, both from the 2026-07-18 cardiology review | — | — | ❌ dup |
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
| HC-50 | Vignette renderer (3 levels) | `render(profile, level, seed)`; facts-only; deterministic. ✅ **Done 2026-07-19**: `renderer/` — 3 levels, deterministic (SHA-256 seeding, not process-salted `hash()`), self-checks against `leakage.scan` on every call. **Design invariant: difficulty changes presentation, never information** — all levels carry the same decision-relevant facts, so a per-level drop localizes to extraction rather than to a withheld fact. Never renders `bp_stage`/`prevent_10yr`/`ckd_albuminuria`/contraindication flags, but renders all their raw inputs, so nothing is unanswerable. **BP is floored, not rounded**: NHANES BP is a mean (131.667), and rounding crosses staging thresholds — it would have corrupted **93 of 4,806** profiles by showing a BP one stage above its own hidden label | HC-18/HC-10 | L | ✅ |
| HC-51 | Distractor library | hand-authored, once-validated; family-hx vs patient-fact traps. **Not started — and it is the gap that limits `hard`**: HC-50's `hard` filler is clinically inert (visit logistics), so `hard` is currently *harder to extract from*, not *harder to reason about*. Plugs into the renderer via a `distractors=` hook. Clinician-authored by design (Aria) | HC-50 | M | ⬜ |
| HC-52 | Task A builder | clean profile → engine label | HC-33..38 | S | ⬜ |
| HC-53 | Task B builder + leakage audit | rendered vignette → hidden label; no label tokens in text. ✅ **Done 2026-07-19**: `tasks/` — inputs and labels in **physically separate files** joined only on `case_id` (principle 4); the audit is a **build gate, not a report** (a failing corpus is never written); splits are **patient-level** (a patient's 3 levels cannot straddle train/test) and **growth-stable** (hash-threshold, so adding cycles/MIMIC leaves existing patients in place). Frozen corpus: 4,806 patients → **14,418 cases, audit passes with 0 token hits and 0 label-column hits**; checksums in `benchmarks/task_b_manifest.json`, re-checkable via `tasks.verify()`. ⚠️ **The human half of the gate is still open** — 20-vignette facts-only read by Aria; sheet generated by `tasks/spotcheck.py`. Built against HC-50 only; HC-51 distractors not yet included | HC-50,51 | M | ✅ (mechanical); ⬜ (human spot-check) |
| HC-95 | **Contraindication stress set** | HC-92 audit F2: the co-primary safety outcome is **not estimable on NHANES** — only 9/4,806 patients carry any contraindication and all nine are hyperkalemia (**zero pregnancy, zero angioedema**), leaving single-digit test positives. Build a purpose-designed set covering pregnancy / angioedema / hyperkalemia **at BP stages where treatment IS indicated** (so the safe answer is a different class, not "no drug"), plus near-miss distractors (family hx of angioedema, borderline K⁺) so false-positives are measurable; seed abstention reasons beyond `stage1_risk_indeterminate` (audit F4). Same leakage gate as Task B. **Reported as its own table, never pooled into the NHANES headline** | HC-96 | M | ⬜ |
| HC-57 | ✅ **Human facts-only spot-check** (Aria) | the *other half* of the Phase-4 gate: 20 rendered vignettes read and signed off as facts-only. Sheet from `tasks/spotcheck.py`. **Corrected 2026-09-20:** decision stratification alone left two blind spots — the two rare abstain mechanisms (`pregnancy_management_out_of_scope`, `med_status_unknown`) never appeared in the draw, and contraindication flags are not in the labels file at all, so nothing could sample for them. Now three strata; the sheet is 25 patients / 75 vignettes and covers pregnancy and hyperkalemia. Prepared and handed to Aria 2026-09-20. **✅ SIGNED 2026-09-22: PASS, 75/75 vignettes, no flags** — no vignette states or implies the hidden BP stage, treatment decision, or drug class. Verified at sign-off that the sheet checksum and the corpus manifest were both unchanged, so the signature binds to the build the pilot runs against. The Phase-4 gate is closed on both halves; pilot numbers are no longer provisional on this account. Sign-off form in `docs/signoffs/`. **Filed as its own ticket on purpose** — HC-45 and HC-46 were both acceptance criteria that were never deliverables, and both got lost. A scanner catches only the tokens it was told about; this catches a vignette that leads the reader in wording nobody thought to ban. *Pilot numbers read before this closes are provisional* | HC-53 | S | ⬜ |
| HC-54 | Task C builder | note → extract → silver score → engine error-propagation | HC-19 | M | ⬜ |
| HC-55 | Task D linkage | concordance ↔ NHANES mortality / MIMIC dod | HC-11 | S | ⬜ |

## EPIC E5 — Model harness  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-60 | JSON-mode runner | emits `llm_output.schema.json`; deterministic replay. ✅ **Done 2026-07-19**: `runner/` — `run_case()` + provider seam (scripted/replay/Anthropic), strict local validation against the full HC-5 schema, malformed-JSON retry, transcript with prompt/schema hashes + usage + cost + latency, and `replay()`. ⚠️ `AnthropicProvider` is **authored but not executed** against the live API (no SDK/credential available) — see `runner/README.md`; malformed-JSON rate is **unmeasured** until a real smoke run | HC-5 | M | ✅ |
| HC-61 | Model adapters | ≥1 frontier + ≥1 open-weight. **2026-09-20:** `anthropic==1.7.0` pinned in `requirements.txt` (import stays lazy so CI needs no key); `AnthropicProvider` corrected against the live API reference — adaptive thinking pinned and recorded, `max_tokens` 4096 → 16000 (thinking tokens count against it, so the old ceiling would have charged our own truncation to the model's formatting), refusal and truncation split out as their own outcomes rather than pooled into a malformed-JSON rate, price table refreshed (Sonnet 5 was listed at Sonnet 4.6's price; Opus 5 was missing entirely, so it would have recorded a null cost). **Frontier arm changed to OpenAI (`gpt-6-astra`) 2026-09-20** at Aria's request, before any pilot call; `OpenAIProvider` added, `AnthropicProvider` retained and still tested (`FRONTIER_MODEL` selects). Three shapes differ per vendor and each would have broken a first live call: `max_completion_tokens` (not the deprecated `max_tokens`, which reasoning models reject), `reasoning_effort` in place of `effort`, and **refusals arriving in `message.refusal` with `content` null** — reading only `content` would have scored a declined clinical question as malformed JSON. Reasoning tokens are billed as output and are now recorded. ⚠️ **The frontier arm publishes no dated snapshot, so it cannot be version-pinned**; the id the API reports is recorded per call, making a silent model change detectable but not preventable — a reproducibility limitation for the manuscript. **D3 resolved 2026-09-22:** open-weight arm is `openai/gpt-oss-120b` on Groq, reasoning effort pinned at `high` to match the frontier arm. Three host requirements found in its docs, each of which would have broken the first call: strict structured outputs requires **every** property in `required` (`TraceStep.citation` was optional, so the request copy would have been rejected - fixed generically in `api_safe_schema`, and the full local schema still treats it as optional); `max_completion_tokens` not `max_tokens`; and `reasoning_effort` must be pinned or this arm runs at a host default while the frontier arm runs pinned. ⚠️ **same-lab limitation:** gpt-oss is OpenAI's open-weight model and the frontier arm is also OpenAI, so the design's *replicates across models* bar is **not met by this pair** - a lab-level quirk would replicate across both and read as a mechanism finding. Recorded in the kill-criteria doc section 6.4; a third arm from a different lab is needed before any such RQ2 claim. ⚠️ **No provider has yet run against a live API — no credential exists on the machine.** Malformed-output rate therefore still unmeasured | HC-60 | S | 🟡 |
| HC-62 | Conditions | vanilla / naive-RAG / guideline-graph | HC-60 | M | ⬜ |
| HC-63 | Repro infra | ~~seeds~~, logging, caching, cost/latency capture. **No seeds exist** — see HC-64; cost/latency already captured per call by HC-60 | HC-60 | S | ⬜ |
| HC-64 | **"temperature/seed pinned" is not implementable** | `temperature`/`top_p`/`top_k` are rejected (400) on current frontier models and there is no `seed`. Reproducibility rests on transcript replay, not sampling control. Fix Phase-5 wording (✅ done), decide whether `effort` is frozen for the freeze, and state **archival** vs **sampling** reproducibility once in the methods | HC-60 | S | ⬜ |

## EPIC E6 — Evaluation & failure-mode audit  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-70 | Metrics | all 9 plan metrics; reproduces hand-scored gold set. ✅ **Done 2026-07-20**: `evaluator/` (`metrics.py` pure functions, `score.py` per-case + aggregation). Gold set of 5 hand-scored cases passes. Aggregation **enforces the HC-92 audit findings in code**: `majority_class_baseline` emitted beside every concordance figure (F1), safety kept out of the headline mean, undefined metrics dropped with an `n_` count rather than zeroed (F2). Abstention reported as **two** rates (over/under) over their own denominators, never one score. `trace_concordance` is order-sensitive and symmetric, so padding a trace with filler cannot score 1.0. Extraction compares to the renderer's **displayed** (floored) BP per the HC-50 handoff. Exclusion table lives in `vocab.CONTRAINDICATED_CLASSES` so scoring and HC-36 cannot drift. End-to-end on the real test split: a constant `lifestyle_only` model scores 0.515 against a printed baseline of 0.515. Subgroups = HC-72; failure-mode tags = HC-71; CIs = HC-94 | HC-52..54 | M | ✅ |
| HC-71 | Failure-mode classifier | each miss tagged extraction/reasoning/citation | HC-70 | M | ⬜ |
| HC-72 | Subgroup + difficulty reporting | per sex/age/comorbidity × level | HC-70 | S | ⬜ |

## EPIC E7 — Experiments  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-80 | **Pilot spike + kill-criteria** | C1, 20 patients × **3 levels** × 2 models × **k = 5** = 600 calls; per-failure-mode table with run-to-run SD, malformed/refusal/truncation rates and `majority_class_baseline` beside every concordance figure; go/no-go. **Scope conflict with Experiment Design §11 resolved 2026-09-20 in favour of three levels** — §11 said moderate-only and then stated the kill criterion as *all difficulties near ceiling*, which one level cannot evaluate; both docs and both `_zh` twins corrected. **Criteria pre-registered and signed by Aria 2026-09-20 before any call**, in `docs/HTN-Concord_Pilot_Kill_Criteria.md` and implemented as `experiments/kill_criteria.py`. Harness + criteria built and green; **blocked on credentials** | HC-53,60,70 | M | 🟡 |
| HC-81 | RQ1/RQ2/RQ3 full runs | reproducibility, failure localization, graph-vs-baselines | HC-80 | L | ⬜ |
| HC-82 | Task D plausibility | concordance↔mortality association (never causal) | HC-55,70 | S | ⬜ |
| HC-94 | **Pre-registration freeze + statistical analysis** | version-tag corpus/prompts/schema/engine/metrics *before* the first scored run; paired McNemar, patient-level cluster bootstrap CIs (B=2000), k=5 replicate SD, Holm–Bonferroni within RQ family; reproduces a hand-computed McNemar + bootstrap CI on a fixture. **A retroactive freeze is not a freeze** | HC-70,92 | M | ⬜ |

## EPIC E8 — Writing & release  ⬜
| ID | Ticket | Acceptance criteria | Dep | Size | Status |
|---|---|---|---|---|---|
| HC-90 | Open-source engine + benchmark | reproducible release w/ manifest, checksums, QA | HC-81 | M | ⬜ |
| HC-91 | Paper(s) | 1 flagship vs benchmark+method split (Aria's call) | HC-81 | L | ⬜ |
| HC-92 | **Experiment design (ablation matrix + RQs + TRIPOD-LLM mapping)** | `docs/HTN-Concord_Experiment_Design.md` + `_zh.md` + both Notion pages: study type, C0–C4 ladder with one factor per rung, RQ specification (Master Plan RQ numbering preserved), analysis plan, threats to validity | — | M | ✅ |
| HC-93 | TRIPOD-LLM item-number transcription | numbered checklist w/ per-item evidence location; N/A items carry a reason; DECIDE-AI/CONSORT-AI out-of-scope sentence drafted. **Item numbers transcribed from the paper, never from memory** | HC-92 | S | ⬜ |

---

### Immediate sprint (rewritten 2026-07-18 — the previous list was five completed tickets)
1. ~~**HC-7** `git init` + `.gitignore` + tagged baseline~~ — ✅ **done 2026-07-18.** Baseline `d94b5d9`,
   tag `baseline-2026-07-18`, branch `main`, pushed to private `AriaCong/htn-concord`. Unblocked CI (HC-4 ✅),
   run manifests (HC-9), and release (HC-90).
2. ~~**HC-4** CI workflow~~ — ✅ **done 2026-07-18.** Live and green on `AriaCong/htn-concord` (private);
   two consecutive successful runs, 123/123 on Python 3.12.13.
3. **HC-9** run manifest (git SHA + input/output SHA256 + resolved config) on both pipelines.
4. **HC-42** `DecisionBuilder` refactor — do this **before** HC-34, or the accumulate-then-freeze pattern
   gets duplicated across six rule modules.
5. **HC-5 + HC-39 designed jointly** — they are the contract between the engine and the LLM half; authoring
   HC-5 first means guessing the trace shape and rewriting it later. *(Resolved 2026-07-19: HC-5 ✅ took the
   trace shape from the engine's existing `engine.types.TraceStep` rather than inventing one, and a
   drift-guard test asserts the schema's TraceStep equals the dataclass field-for-field — so HC-39's emitter
   inherits a fixed contract instead of the schema guessing at a future one.)*

### New tickets opened by the 2026-07-18 three-reviewer audit
| ID | Ticket | Why | Priority |
|---|---|---|---|
| HC-7 | `git init` + baseline commit | ✅ **done 2026-07-18** — commit `d94b5d9` on `main`, tagged `baseline-2026-07-18`; 51 files / 408 KB; `Data/` (~60 GB credentialed) and the copyrighted PREVENT paper excluded and verified staged-clean. **Baseline is post-audit-fix**: the HC-8 corrections predate the repo, so no pre-fix referent exists to commit and none was fabricated | P0 |
| HC-8 | Fix `derive.py` correctness bugs — **both** the `ckd_albuminuria` NA-coercion (unknown→False defeated the ABSTAIN contract; unknown 0 → 266) **and** the `bp_stage` `between()` boundary bug (voided 56/4,806 valid non-integer BPs; the profile column silently disagreed with the engine) | ✅ **done** — nulls 56 → 0, profiles re-emitted with `clinical_cvd` (30 → 31 cols), plus a boundary-grid test asserting `derive` and `vocab` staging can never diverge. *(There is no separate "HC-8b" ticket — both bugs live under HC-8 in Linear and Notion.)* | P0 |
| HC-9 | Run-manifest emitter | artifacts had drifted from the code that produced them | P0 |
| HC-23 | Implement the decided **median** BP harmonization | every doc says median was harmonized 2026-07-18; `clean.py` still uses `mean()`, so the shipped substrate is a mean-based artifact and every quoted stage/label figure describes the mean pipeline. Benchmark-freeze action: change, re-run, re-quote in one pass | P1 |
| HC-24 | Wire `DEMO_J.RIDEXPRG` pregnancy flag | ✅ **Done 2026-07-19** (PR #5): `RIDEXPRG` → `pregnant` (three-valued: asked only of women 20–44, so absent must not read as 'not pregnant'); engine treats it as a **scope gate before staging**, abstaining `pregnancy_management_out_of_scope` regardless of BP, per the Master Plan contraindication table. New anchor `HTN-CONCORD:abstain-out-of-scope`. All 45 now abstain; corpus rebuilt (abstain 432→564). Drug-class consequences remain **HC-36**; other out-of-scope guards remain **HC-28** | ✅ |
| HC-25 | Download `MCQ_J`, populate `clinical_cvd` | trigger currently null for every NHANES row → under-treatment bias | P1 |
| HC-26 | MIMIC ED-linkage cohort decision | real decision-cohort N is ~8,921, not 28,530 | P1 |
| HC-27 | Bound MIMIC lab selection to strictly pre-`admittime` | "nearest the index encounter" is bidirectional → post-index leakage | P1 |
| HC-28 | Runtime out-of-scope guards | engine answers confidently on resistant/secondary HTN, pregnancy, ESRD, hypertensive emergency — all declared out of scope but unenforced | P1 |
| HC-29 | Split facts/labels into separate artifacts | leakage principle #4 asserted but not enforced in the data layer | P1 |
| HC-42 | `DecisionBuilder` refactor | composition seam needed before HC-34 | P1 |
| HC-43 | `guideline` field + registry dispatch in `evaluate()` | free now, invasive after HC-41 | P1 |
| HC-44 | Acquire guideline PDF; map anchors → printed sections | hard prerequisite for HC-38 and the `citation_support` metric | P1 |
| HC-45 | Engine integration run over all profiles + abstention report | Phase-3 acceptance gate had no ticket; would have caught HC-8 | P1 |
| HC-46 | Leakage-audit lint (forbidden-token scanner) | ~~referenced in HC-53's acceptance but never a deliverable~~ — **the scanner now exists** as `htn-concord/leakage.py` (2026-07-19), shared by the renderer's per-call self-check and HC-53's build gate. Matching is word-boundary anchored, which is load-bearing: a substring scan would reject every vignette for a patient on **hydrochlorothiazide**, the commonest antihypertensive in the cohort. Residual scope is only the **standalone CLI lint** wrapping `leakage.scan` | P2 |
| HC-47 | Response cache + transcript store | makes analysis reproducible despite non-deterministic inference | P2 |
| HC-48 | Prompt-template versioning + hashing | unversioned prompt edits silently invalidate prior runs | P2 |
| HC-56 | Real MIMIC row in committed test fixture | `tests/test_mimic_omr_bp.py` embeds `10000032,2180-04-27,1,Blood Pressure,110/65`, present **verbatim** in `omr.csv.gz`. PhysioNet's DUA forbids redistribution — contained while the repo is private, **blocks HC-90**. Either license-clear it as ODbL demo data or replace with synthetic values | P1 |
| HC-49 | Clinician face-validity + adjudication of 150–200 cases | "no clinician in the loop" is not survivable at review as currently framed | **P0 for Paper 1** |
