# HC-95 — Contraindication & Multi-Constraint Stress Set (design)

**Status:** design document, approved 2026-07-23. Not an implementation record. Companion:
`HTN-Concord_Experiment_Design.md` §3 (co-primary safety outcome), §10/F1–F2 (the gaps this closes),
`HTN-Concord_Master_Plan.md` Phase 4 (task construction).

**Convention note.** This file follows the existing `docs/superpowers/specs/` convention (English, single
file), not the bilingual EN/CN pairing used for the `HTN-Concord_*` doc set. If a Chinese pair is wanted
later, add `_zh.md` — deferred by author's request ("后面再改").

---

## 1. Why HC-95 exists (the two binding constraints it removes)

The built Task-B corpus (14,418 cases / 4,806 NHANES patients) has two structural defects that no amount of
*additional* NHANES data can fix, because both are **composition**, not volume:

- **F2 — the co-primary safety outcome is not estimable.** Only 9 of 4,806 patients carry any
  contraindication, all hyperkalemia; **zero pregnancy, zero angioedema**. `unsafe_recommendation`,
  `contraindication_recall` and `contraindication_false_positive` cannot be measured, and the engine's
  pregnancy/angioedema rules are never exercised by real data.
- **F1 — the headline metric has a 51.5% floor.** Test-split majority class (`lifestyle_only`) is 51.5%;
  absolute `decision_concordance` is nearly uninterpretable and the multi-constraint thesis
  (`BP × comorbidity × contraindication × meds`) is barely exercised because those constraints almost never
  co-occur or conflict in a general-population survey.

**Scope (approved):** HC-95 addresses *both* — safety **and** discriminative power. It is a designed
companion corpus, **not** a replacement for NHANES. NHANES keeps the representative-population role and the
contamination-delta argument (both public → contamination affects both arms → the ladder deltas carry the
claim). Absolute numbers on HC-95 are read as "on a constructed, constraint-dense distribution."

**Key methodological insight.** For RQ2 (failure-mechanism localization) a *designed* corpus with controlled
factor manipulation is scientifically **superior** to more observational data: mechanism attribution needs
factorial coverage that isolates one factor at a time, not a representative sample. Real observational data
is for ecological validity (RQ4 / Task C / MIMIC), not for mechanism.

---

## 2. Invariant reused from Task B

Same contracts as Task B; the **only** difference is profile provenance:

```
synthetic hidden PatientProfile row  →  engine label (ground truth)  →  renderer (3 levels)  →  vignette
                                         + leakage audit + schema validation + frozen manifest/checksums
```

This preserves the clinician-free, deterministic-answer-key invariant and lets HC-95 flow through the
existing `renderer/` and `tasks/` machinery unchanged. Labels come from the engine, never an LLM judge;
any cell the engine cannot resolve → the *specified* abstain reason, never a guess.

---

## 3. Generation method: programmatic factorial + two gates

Chosen over pure hand-authoring (cannot reach 600–1000) and pure combinatorial generation (produces
clinically absurd profiles). Generate structured `PatientProfile`s across a controlled field grid, then
pass every candidate through two gates before rendering:

1. **Engine-labelability gate.** Every profile must produce a definite engine label OR a *specified* abstain
   reason. Cells whose only outcome is an unintended abstain are dropped or re-parameterized.
2. **Plausibility gate — every rule flagged for HC-49.** A hand-authored allowlist of clinically-coherent
   field combinations filters implausible profiles (e.g. age 25 + ESRD + 4 comorbidities; pregnancy + male).
   **The author has no clinical background and does not settle plausibility.** Every plausibility rule is a
   clinical claim carried to HC-49 blind adjudication; the conservative default (exclude the combination) is
   taken until HC-49 confirms.

Rendered through `renderer/` (simple / moderate / hard) and audited by `tasks/` leakage scanner exactly as
Task B.

---

## 4. Structure: two subcorpora

### 4.1 HC-95-SAFETY — closes F2

| Factor | Values |
|---|---|
| Contraindication type | pregnancy · angioedema history · hyperkalemia K⁺ ≥ 5.5 |
| Abstain / negative-control axis | K⁺ ≥ 6.0 → must **abstain**; **K⁺ 5.0–5.4 → negative control, must NOT be flagged** (catches false positives) |
| **Danger axis (core mechanism)** | each contraindication × a BP/decision context where the *naive* guideline decision would name the contraindicated drug |
| **Matched distractor pairing** (reuses Task B distractor concept) | each positive paired with a near-miss negative that must NOT set the flag |

**Danger axis rationale.** A contraindication on a lifestyle-only patient tests nothing. The cell must be
constructed so a scope-blind engine would recommend the contraindicated agent — e.g. **pregnancy + stage-2
BP**: a scope-blind engine says INITIATE, HC-36 names an ACEi/ARB → that is the `unsafe_recommendation`
the model is tested against. This is what actually exercises the safety outcome.

**Distractor rationale.** Matched near-miss negatives (e.g. "stopped lisinopril after her lips swelled"
[sets angioedema] vs "her father had angioedema from lisinopril" [must not]) are what make
`contraindication_false_positive` estimable, not just recall.

**Sizing.** ~50–80 positives per real contraindication type × matched negatives, + K≥6 abstain cell +
K 5.0–5.4 negative-control cell ≈ **a few hundred cases**.

### 4.2 HC-95-GRID — closes F1

Grid over the factors the engine's decision actually depends on, parameterized so the resulting **engine-label
distribution is near class-balanced**, over-sampling the decisions NHANES starves (`initiate`, `intensify`,
the abstain mechanisms):

| Factor | Values |
|---|---|
| BP stage | normal · elevated · stage 1 · stage 2 |
| Risk (stage-1 only) | PREVENT < 7.5% vs ≥ 7.5% (the risk-based stage-1 branch — flagged error-concentrated) |
| Comorbidity modifier | none · CKD (eGFR < 60 **OR** UACR ≥ 30) · diabetes → drives ACEI/ARB preference |
| Med status | `on_bp_meds` true / false / unknown → drives initiate vs intensify vs abstain (`med_status_unknown`) |

**Sizing.** ~400–600 cases, engineered for balance. Combined with SAFETY ≈ **600–1000** total (the approved
Standard tier).

---

## 5. Splits, freeze, provenance

- **Pure held-out evaluation set — NOT split into train/dev/test.** A stress set is for measuring, not
  tuning; splitting wastes scarce positives and invites tuning-to-the-stress-set. HC-95 gets its own frozen
  manifest with checksums, test-only, re-checkable via `tasks.verify()`.
- Reported **separately** from the NHANES headline, never averaged in.
- Not real text (that is Task C / MIMIC, RQ4). Not a headline replacement for NHANES.

---

## 6. Metrics unlocked

- `unsafe_recommendation` (co-primary safety) — now estimable, via the danger axis
- `contraindication_recall` + `contraindication_false_positive` — via matched distractors
- `abstention_appropriateness` — via K≥6 abstain cells, pregnancy/angioedema out-of-scope cells, and
  negative controls
- **balanced `decision_concordance`** — via the near-balanced GRID; report majority-class baseline alongside

---

## 7. Dependencies and sequencing (HC-95 cannot be built first)

Ground truth = engine on the hidden row, identical to Task B. Therefore:

- **HC-95-SAFETY is blocked on HC-36 (contraindication rules) + HC-37 (abstention).** The engine cannot
  label a contraindication case until it can process contraindications.
- **HC-95-GRID is blocked on HC-34 (drug class) + HC-35 (comorbidity modifiers)** for full decision coverage;
  it can be *partially* built on the current engine (staging + initiation/intensification already exist).

**Consequence:** HC-95 turns "finish the engine's reasoning chain" into a hard prerequisite, and gives the
engine work a concrete acceptance exit. It is not the next thing to build — the engine rules it depends on
are.

---

## 8. Validation hook (HC-49)

Every plausibility rule and every "this danger cell is genuinely dangerous" assertion is a clinical claim.
A decision-stratified sample of HC-95 goes to HC-49 blind adjudication, over-sampling contraindication-positive
and abstain cells (already mandated by the Experiment Design). The author authors conservatively and flags;
Aria (no clinical background) is never asked to settle these.

---

## 9. What HC-95 deliberately is NOT

- Not split (pure evaluation set)
- Not a replacement for NHANES (scope B, not full-replacement) — a designed companion
- Not real clinical text (that is Task C)
- Not labeled by an LLM judge — engine only, abstain over guess

---

## 10. Open items to resolve in the implementation plan

1. Exact per-cell counts that hit both the ~50–80 safety positives and the near-balance GRID target within
   the 600–1000 envelope.
2. Whether HC-95-SAFETY is run only at ladder condition C1, or also C3 (does tool access repair
   contraindication misses?) — an Experiment-Design question (§2 ablation matrix) to settle before the run.
3. The plausibility allowlist's concrete rules (authored conservatively → HC-49).
4. Whether the Experiment Design's ablation matrix and §3 outcomes text need an explicit "HC-95 corpus"
   column / paragraph (likely yes — see the "research tasks change?" note).
