# HTN-Concord — Experiment Design (ablation matrix, research questions, TRIPOD-LLM mapping)

**Status:** design document, not an implementation record. Every condition below is marked with its
build state; conditions gated on unbuilt tickets are labelled as such and must not be described in the
present tense elsewhere.
**Companion:** `HTN-Concord_Master_Plan.md` (phases, tickets), `HTN-Concord_Backlog.md` (HC-n rows).
**Chinese pair:** `HTN-Concord_Experiment_Design_zh.md` — edit both in the same pass.

---

## 0. What kind of study this is

HTN-Concord is **not** a model-comparison study and **not** a prediction-model study. Stating this
precisely matters, because the wrong classification pulls in the wrong reporting checklist and the
wrong statistics.

The design is a **diagnostic-accuracy-shaped evaluation study against a computable reference
standard**:

| Role | Filled by |
|---|---|
| Index test | An LLM, given a task input, emitting `llm_output.schema.json` |
| Reference standard | The Deterministic Guideline Engine (`engine/evaluate.py`), which encodes 2025 AHA/ACC (DOI 10.1161/HYP.0000000000000249) |
| Unit of analysis | One case (`case_id`) = one patient profile rendered at one difficulty level |
| Target condition | Guideline-concordant management decision for adult primary hypertension |

The engine is an **answer key, not a competitor**. It has no error bars of its own in the statistical
sense: it is a formalization of a published guideline, and its correctness is established by rule-level
unit tests and by clinician adjudication (HC-49), not by agreement with the LLM. Any sentence of the
form "the engine outperformed the LLM" is a category error and must not appear in the manuscript.

**Consequence for the technology-stack question.** A deployment stack (Next.js / FastAPI / LangGraph /
pgvector / Postgres checkpointer) contains no experimental variables. Those layers are deterministic
plumbing: they are either correct or defective, and a defect is a bug to fix rather than a finding to
report. Only the layers below appear in this design, because only they can change the decision:
input representation, guideline knowledge access, numeric computation, model identity, and output
contract.

---

## 1. Research questions

The Master Plan already numbers three research questions. **This document does not renumber them.**
It specifies them to the level of a testable contrast and adds the sub-questions the ablation supports.

| RQ | Question | Contrast | Conclusion form (illustrative — numbers are placeholders) |
|---|---|---|---|
| **RQ1** | Is the reference standard itself reproducible and defensible? | Engine vs. clinician adjudication (HC-49); engine vs. its own re-run | "Engine reproduces byte-identical labels across runs; N adjudicated cases show κ = _ against independent clinician review; M disagreements resolved as guideline-ambiguous and routed to `ABSTAIN`." |
| **RQ2** | Where in the decision chain do LLMs depart from the guideline, and by what mechanism? | Model output vs. engine label, decomposed per trace step and per failure mode | "Staging is near-ceiling (_%); errors concentrate in risk stratification and contraindication detection; _% of misses are right-answer/wrong-path." |
| **RQ2a** | How much of the error is reading rather than reasoning? | C0 (structured) → C1 (vignette), same model | "Concordance falls _ points from structured input to rendered vignette; that delta is extraction, not clinical reasoning." |
| **RQ2b** | Does difficulty localize to extraction as designed? | simple → moderate → hard within C1 | "Level effect is carried by `extraction_f1`, with `decision_concordance | correct extraction` flat across levels." |
| **RQ3** | Which intervention repairs which error class? | C1 → C2 (retrieval) → C3 (tool) → C3g (guideline graph) | "Retrieval repairs stale-guideline errors but not arithmetic; the PREVENT tool repairs _% of risk-computation errors and none of the knowledge errors." |
| **RQ4** | Do findings on synthetic vignettes hold on real clinical text? | C1/C3 (Task B) → C4 (Task C, MIMIC discharge notes) | Ecological-validity check; a large drop bounds how far vignette-based conclusions generalize. |

RQ2 is the contribution that existing medical-QA benchmarks cannot make. They report a single score
because they have no reference reasoning path. HTN-Concord's engine emits `TraceStep`s and citation
anchors, so a miss can be attributed to a **step** (staging / risk / contraindication / class
selection) and a **mechanism** (extraction / reasoning / citation), which is what `trace_concordance`
and the HC-71 failure-mode classifier operationalize.

---

## 2. Ablation matrix

**Controlled-ablation principle: exactly one factor changes between adjacent conditions.** Frozen
across every condition: the case corpus and its splits, the prompt template family, the output schema
(`llm_output.schema.json` SHA-256), the evaluator and its metric definitions, and the engine commit.
Any change to a frozen artifact invalidates cross-condition comparison and requires a full re-run of
every condition, not a patch to one.

| Cond. | Input | Guideline access | Computation | Sole delta vs. predecessor | Isolates | Build state |
|---|---|---|---|---|---|---|
| **C0** | Task A — structured `PatientProfile` JSON | parametric memory only | model does its own arithmetic | — (baseline) | Ceiling: reasoning with perfect extraction | ⬜ Task A = HC-52 |
| **C1** | Task B — rendered vignette (simple/moderate/hard) | parametric memory only | model's own arithmetic | input representation | **Extraction** burden (C0−C1) | ✅ corpus built (HC-50/HC-53); ⬜ runs |
| **C2** | Task B | + retrieved 2025 AHA/ACC passages | model's own arithmetic | retrieval on | **Knowledge** deficit repaired (C2−C1) | ⬜ gated on HC-44 anchors |
| **C3** | Task B | + retrieval | + deterministic PREVENT / staging tool calls | tool access on | **Computation** error repaired (C3−C2) | ⬜ gated on HC-61 tool-call adapter |
| **C3g** | Task B | + guideline **graph** traversal | + tools | retrieval mechanism (flat RAG → graph) | Graph's marginal value (RQ3 headline) | ⬜ Paper 2 / Phase 7 |
| **C4** | Task C — MIMIC-IV discharge note | as C3 | as C3 | input provenance (synthetic → real EHR text) | **Ecological validity** | ⬜ gated on HC-54 + MIMIC cohort |

**Crossed factors.** Each condition is run across (a) ≥1 frontier and ≥1 open-weight model (HC-61) and
(b) all three difficulty levels within Task B. Model identity is a crossed factor, not a ladder rung:
**a failure mode is reported as a finding only if it replicates across models.** Single-model quirks
are reported as such and excluded from mechanism claims.

**Read the ladder as differences, not as levels.** The scientific content is in C0−C1, C2−C1, C3−C2,
C3g−C3, and C4−C3. An absolute concordance number depends on corpus difficulty, which is a design
choice; a difference between two conditions sharing a corpus does not.

**Ablation ordering caveat.** The ladder is cumulative, so each delta is estimated *in the context of
the preceding conditions* — it is not a main effect in a factorial sense. If a reviewer requires
main effects (e.g. tool access without retrieval), the honest options are a factorial extension
(retrieval × tools = 4 cells) or an explicit statement of the interpretive limit. **Decision: report
the cumulative ladder as primary and add the 2×2 retrieval×tool cell block on Task B `moderate` only,
as a secondary analysis** — this bounds cost while answering the interaction question. (Open item —
see §7.)

---

## 3. Outcomes

**Primary outcome.** `decision_concordance` — exact match between the model's `decision` and the
engine's `Decision` on the hidden row.

**Co-primary safety outcome.** `unsafe_recommendation` — a recommendation contraindicated for the
patient (e.g. ACEi/ARB with pregnancy; K⁺-raising agent with hyperkalemia). Reported separately and
never averaged into the concordance headline. **⚠️ Not estimable on the NHANES cohort — see §10 F2;
this outcome must be measured on a purpose-built contraindication stress set (HC-95).** **Rationale: error types are not exchangeable.** A
missed pregnancy contraindication and an over-cautious lifestyle-only recommendation are both "one
error" to an accuracy metric and are not clinically equivalent. The engine's contraindication rules
supply this severity tag automatically, so weighting is rule-derived rather than a post-hoc judgement.

**Secondary outcomes** (all defined in Phase 6, implemented by HC-70): `staging_correct`,
`extraction_f1`, `contraindication_recall`, `contraindication_false_positive`, `citation_support`,
`trace_concordance`, `abstention_appropriateness`.

**Abstention is scored, not excluded.** A model that abstains when the determinant is genuinely
unknown is behaving correctly and scores as such; a model that abstains to avoid committing on a
resolvable case is penalized. Both directions are reported (`abstention_appropriateness`), because a
benchmark that drops abstentions rewards guessing.

**Reporting granularity.** Every outcome is reported per difficulty level and per subgroup (sex, age
band, comorbidity) per HC-72. Subgroup analyses are **descriptive and pre-specified**; they are not
powered for significance testing and will be labelled accordingly rather than significance-starred.

---

## 4. Statistical analysis plan

1. **Paired, not independent.** Every case appears in every condition, so condition contrasts are
   paired. Use **McNemar's test** for binary concordance between two conditions and its generalization
   for the multi-condition ladder; never a two-sample test of independent proportions, which
   overstates variance and discards the pairing.
2. **Clustering.** One patient contributes three cases (three difficulty levels). Cases within a
   patient are not independent. Use **patient-level clustering** — cluster-robust standard errors, or
   a **patient-level cluster bootstrap** (resample patients, not cases) for CIs on all headline
   numbers. Splits are already patient-level (`tasks/splits.py`), so the analysis unit matches the
   split unit.
3. **Uncertainty.** Report 95% CIs on every headline metric. Bootstrap over patients, B = 2000.
4. **Model stochasticity.** Sampling parameters are **not pinnable** on current frontier models
   (HC-64: `temperature`/`top_p`/`top_k` are rejected; no `seed` exists). Therefore run each case
   **k = 5** times per condition and report the mean with the across-replicate SD, so run-to-run
   variance is measured and visible rather than assumed away. Replicate variance is a reported
   quantity, not a nuisance to hide.
5. **Multiplicity.** The ladder yields many contrasts. Pre-specify the primary contrasts (C0−C1 for
   RQ2a; C3−C2 and C2−C1 for RQ3) and apply **Holm–Bonferroni within each RQ family**. All other
   contrasts are exploratory and labelled so.
6. **Effect sizes over p-values.** Lead with the concordance difference in percentage points with CI;
   p-values are secondary.
7. **Analysis freeze.** Corpus, prompts, schema, metric code, and this analysis plan are **git-tagged
   before the first scored run**. Post-hoc changes are recorded in a changelog with the reason. This
   is the specific defence against the most common reviewer objection to LLM papers — that prompts
   were tuned until the numbers improved.

---

## 5. Reproducibility posture (state this exactly once, precisely)

Two different claims get conflated; the manuscript must separate them.

- **Archivally reproducible — yes.** Every reported number re-derives from stored transcripts with no
  network call. `runner.replay()` re-parses and re-validates archived raw text and ignores the stored
  `parsed` block, so a post-hoc-edited transcript fails rather than round-trips. `ReplayProvider`
  refuses to serve a stored response when the prompt hash changed.
- **Sampling reproducible — no, and not achievable.** Re-calling a model is not guaranteed to return
  the same text, and no current API parameter makes it so (HC-64). This is a property of the
  provider, not a shortcoming of the harness.

The engine half **is** deterministic and fully reproducible, which is why the reference standard is
the reproducible component of the study even though the index test is not.

---

## 6. TRIPOD-LLM checklist mapping

Primary reporting framework: **TRIPOD-LLM** (Gallifant et al., *Nature Medicine*, 2025) — the LLM
extension of TRIPOD, written for studies that evaluate LLMs on health tasks. Supporting:
**MI-CLAIM-GEN** for reproducibility disclosure, and **STARD**'s index-test/reference-standard
vocabulary for the accuracy framing in §0. **DECIDE-AI and CONSORT-AI do not apply** and the
manuscript should say so in one sentence: this study has no human participants and no clinician in
the loop, so it sits upstream of DECIDE-AI's early-live-evaluation scope. Claiming an inapplicable
framework is a credibility cost, not a credential.

> **Verify item numbering against the published checklist before submission.** The mapping below is
> organized by TRIPOD-LLM's item *topics*; item numbers must be transcribed from the paper itself
> (HC-93). Do not cite item numbers from memory.

| TRIPOD-LLM topic | Where HTN-Concord satisfies it | State |
|---|---|---|
| Title / abstract identify LLM evaluation + task | Manuscript | ⬜ |
| Background: why guideline concordance, why hypertension | Master Plan §0; manuscript intro | ⬜ |
| **Data source and provenance** | `HTN-Concord_DataDictionary_and_CleaningStrategy.md`; NHANES cycle J primary, MIMIC-IV for Task C | ✅ documented |
| **Eligibility / cohort construction** | `pipelines/nhanes/` — 9,254 respondents → 4,806 adult profiles; inclusion rules coded, not prose | ✅ |
| **Outcome / reference standard definition** | `engine/` + `engine/citations.py`; every label carries guideline anchors and a trace | ✅ |
| Reference-standard validation | Rule-level unit tests + clinician adjudication | 🟡 tests ✅ / HC-49 ⬜ |
| **Data leakage / contamination control** | `leakage.py` forbidden-token scanner; labels physically separated from model-facing files; build gated on audit; patient-level splits | ✅ |
| **Model identity and version** | Recorded per call: model ID, prompt SHA-256, schema SHA-256, effort, max_tokens | ✅ (`runner/`) |
| **Prompt disclosure** | Prompt templates versioned; full text published in appendix | 🟡 versioned ✅ / appendix ⬜ |
| **Inference parameters** | Recorded; non-pinnable parameters explicitly declared (§5, HC-64) | ✅ |
| **Stochasticity handling** | k = 5 replicates, across-replicate SD reported (§4.4) | ⬜ |
| **Performance measures, pre-specified** | Nine metrics, Phase 6; primary + co-primary safety outcome named in §3 | ✅ HC-70 done 2026-07-20 (`evaluator/`) |
| **Uncertainty quantification** | Patient-clustered bootstrap CIs (§4.2–4.3) | ⬜ |
| **Subgroup / fairness reporting** | HC-72: sex, age band, comorbidity × difficulty | ⬜ |
| **Error / failure analysis** | HC-71 failure-mode classifier; trace-step attribution | ⬜ |
| **Abstention & uncertainty behaviour** | `abstention_appropriateness`; engine three-valued abstention | ✅ engine + metric (HC-70: two rates, over/under) |
| **Human oversight / intended use** | Explicit non-deployment statement (§8) | ⬜ |
| **Reproducibility & availability** | Open-source engine + benchmark; manifest, checksums, environment lock; archival-vs-sampling distinction stated once | 🟡 |
| **Limitations** | §7 | ✅ this doc |
| Funding / conflicts / ethics | Manuscript; NHANES public, MIMIC credentialed under DUA | ⬜ |

---

## 7. Threats to validity and limitations (write these; do not let a reviewer find them first)

1. **The reference standard is one guideline's formalization.** Concordance with HTN-Concord is not
   the same as clinical correctness. Where the guideline is silent or ambiguous the engine abstains
   rather than inventing a rule, and those cases are reported as a category rather than scored.
   The planned ESC 2024 comparator module (Principle 6) reports disagreement rather than merging it.
2. **Formalization is an interpretive act.** Aria hand-writes the rules; a different competent
   encoder could differ at the margins. Clinician adjudication (HC-49) bounds this, and the rule set
   is published so the encoding is inspectable rather than asserted.
3. **Vignettes are synthetic.** Rendered NHANES vignettes are cleaner than clinical text. C4 (Task C,
   MIMIC discharge notes) exists specifically to bound this, and vignette-only findings must be
   stated as vignette-only until C4 runs.
4. **Training-data contamination is unbounded, not merely uncontrolled.** NHANES is public and the
   2025 AHA/ACC guideline is public; both may sit in model pretraining data. Leakage control governs
   *our* corpus construction and cannot govern pretraining. This limits absolute-score interpretation
   and is a further reason the ladder deltas — where contamination affects both arms — carry the
   argument.
5. **No sampling reproducibility** (§5) — mitigated by replicates and transcripts, not solved.
6. **Cumulative ladder ≠ factorial design** (§2) — partially addressed by the planned 2×2 secondary
   block; the remainder is an interpretive limit to state.
7. **Subgroup analyses are underpowered** and reported descriptively (§3).
8. **Single clinical domain.** Adult primary hypertension, initiation/intensification only. No claim
   is made about other guidelines or specialties.
9. **`clinical_cvd` is null in NHANES**, so it acts as a positive-only trigger and the cohort's
   high-risk group is under-identified relative to a real clinic population.

---

## 8. Intended-use statement (required for the manuscript)

HTN-Concord is a **measurement instrument for research**, not a clinical decision support system. No
condition in this design is deployed, no output reaches a patient, and no clinician acts on a model
recommendation within this study. The deployment stack (Next.js / FastAPI / LangGraph / pgvector)
belongs to a **subsequent** phase whose evaluation would fall under DECIDE-AI and require prospective,
clinician-in-the-loop study design — explicitly out of scope here.

---

## 9. Open decisions

| # | Decision | Why it must be resolved before the run |
|---|---|---|
| D1 | Confirm the 2×2 retrieval×tool secondary block (§2) — cost vs. reviewer-proofing | Changes the run budget and the freeze contents |
| D2 | Fix k (replicates) at 5 — or raise it if pilot SD is large | Multiplies total call cost by k |
| D3 | Which open-weight model is the second arm (HC-61) | Determines whether the "replicates across models" bar can be met |
| D4 | Whether ESC 2024 comparator lands in Paper 1 or Paper 2 | Scope of the reference-standard section |
| D5 | Transcribe TRIPOD-LLM item numbers from the published checklist (HC-93) | The mapping in §6 is topic-level until this is done |

---

## 10. Corpus feasibility audit (run 2026-07-19 against the built Task B corpus)

The design above was checked against the corpus that actually exists (14,418 cases / 4,806 patients,
`benchmarks/task_b_manifest.json`), not against the corpus it assumes. **Four findings; the second
invalidates a choice made in §3 and is corrected here.**

**Verified sound:** splits are patient-level and disjoint (train 2,914 / dev 940 / test 952 patients;
zero patient overlap train↔test and dev↔test), the leakage audit passes on all 14,418 cases with zero
token hits and zero label-key hits, and 277 tests pass including
`test_every_level_carries_every_decision_relevant_value` — which is what licenses reading a
level-over-level drop as extraction (RQ2b).

**F1 — Majority class is 52.2%; a headline concordance number is uninterpretable without a baseline.**
Test-split majority class is `lifestyle_only` at **51.5%** (post-HC-96 rebuild; 52.2% before). A model
that answers `lifestyle_only` unconditionally scores 51.5%.
**Required:** report the majority-class baseline alongside every concordance figure, and prefer
balanced accuracy or per-class recall as the reported headline. This does not threaten the ladder
deltas (all conditions share the corpus) but it does threaten any absolute claim.

**F2 — `unsafe_recommendation` is NOT estimable on this corpus, so it cannot stand as a co-primary
outcome as §3 currently specifies.** Only **9 of 4,806 patients** carry any contraindication, and all
nine are hyperkalemia: **zero pregnancy flags, zero angioedema flags.** The engine's pregnancy and
angioedema rules are never exercised by NHANES. In the test split this leaves single-digit positive
cases — no CI worth reporting, and `contraindication_recall` is in the same position.
**Correction:** the safety outcome is retained as co-primary *in the design* but must be estimated on
a **purpose-built contraindication stress set**, not on the NHANES cohort. Reporting a safety rate
from ~2 test patients would be worse than reporting none. Filed as HC-95.

**F3 — Latent label-corruption hazard on pregnancy. ✅ FIXED 2026-07-19 (HC-96).**
`pipelines/nhanes/derive.py` documented that `RIDEXPRG` was ascertainable but never wired in, so
**45 pregnant respondents sat in the cohort with empty contraindication lists.** Their 135 Task B
cases labelled as `lifestyle_only` (129), `at_goal_continue` (3) and `abstain` (3) — zero
pharmacotherapy labels, but only because that subgroup's BP happened to run low (systolic 90–128).
A pregnant patient with stage-2 BP would have received an `initiate` label **as ground truth**, and
once HC-36 landed it would have named an ACEi/ARB.

*Resolution.* Pregnancy is now derived from `RIDEXPRG` (positive-only: "not ascertained" never reads
as "not pregnant") and the engine treats it as a **scope gate that precedes staging** — the encoded
module covers adult primary hypertension in the *non-pregnant* adult, so a pregnant profile abstains
with reason `pregnancy_management_out_of_scope` regardless of BP. Scope deliberately does not depend on BP;
otherwise the corpus's safety would still rest on its BP distribution. All 45 now abstain (verified on
the rebuilt cohort). New anchor `HTN-CONCORD:abstain-out-of-scope` distinguishes this from
insufficient data: more data would not make the encoded rules applicable.

*Provenance of the scope call — corrected 2026-07-19.* An earlier draft of this section claimed the
abstain-on-pregnancy decision was a judgement made without clinical input. **That was wrong.** It was
already specified in the Master Plan contraindication table ("since hypertensive pregnancy management
is out of scope the engine should ABSTAIN, emitting flags for scoring only") and in the HC-36 ticket,
both written from a **cardiology review on 2026-07-18**. The implementation follows existing spec
rather than inventing policy. HC-49 still confirms it, as it confirms every rule — but it is not an
unreviewed call.

*Ticket provenance.* This work was already filed as **HC-24** (P0, "Wire NHANES pregnancy flag") from
that same review. HC-96 was raised in duplicate during the audit and has been closed against HC-24.

**F4 — Abstention was thin and near-single-mechanism; partly improved by the F3 fix.** Before HC-96,
92% of corpus abstentions were one reason. The corpus now carries three mechanisms —
`stage1_risk_indeterminate` (393), `pregnancy_management_out_of_scope` (135), `med_status_unknown` (36) — and the
test split has 117 abstain cases. Still dominated by one reason and still not a general claim about
calibrated uncertainty; report per-reason rather than pooled, and seed further triggers in the stress
set (HC-95).

---

## 11. Order of execution

The pilot (HC-80) runs **C1 only, moderate level, 20 patients × 2 models** and exists to kill the
benchmark early if it lacks discriminative power (all levels near ceiling, or frontier ≈ open-weight
everywhere). **No ladder condition beyond C1 is worth building until the pilot shows the corpus can
separate models.** After the pilot: freeze (§4.7), then C0/C1 full, then C2/C3 as their gating tickets
land, then C3g and C4.
