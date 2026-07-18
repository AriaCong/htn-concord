# HTN-Concord — Engine Rules HC-32 / HC-33 Design

**Date:** 2026-07-17
**Tickets:** HC-32 (BP-staging rule module), HC-33 (initiation/intensification rule)
**Status:** approved design → to be implemented

## 1. Context & correction

The Master Plan (line 121) and prior memory claimed an
`engine/rules/aha_acc_2025/initiation_intensification.py` with 9 passing tests already
existed. It does **not** — there is no `engine/` package in the repo, and the 37 passing
tests are all for the NHANES pipeline. HC-32/HC-33 therefore **stand up the engine package
from scratch**. Backlog/Master-Plan status lines will be corrected to reflect this.

What already exists and is reused:

- **Input contract:** `schemas/patient_profile.schema.json`. Nulls mean "genuinely unknown →
  the engine must ABSTAIN"; a null is never coerced to a definite value.
- **Staging thresholds:** `vocab.BP_THRESHOLDS` and `vocab.bp_stage_scalar(sbp, dbp)` (scalar);
  `pipelines/nhanes/derive.bp_stage` (vectorized). HC-32 wraps the scalar form as a *cited
  engine rule* — it does not re-derive thresholds.
- **PREVENT:** `profile["prevent_10yr"]` is precomputed (null when not computable → abstain on
  the risk trigger); `vocab.PREVENT_STAGE1_TREAT = 7.5`.

Engine definition (Master Plan Phase 3): a **pure function**
`PatientProfile → {decision, staging, drug classes, contraindications, citations, reasoning
trace, abstain?}`. HC-32/33 deliver the staging + initiation/intensification slice; drug-class
selection (HC-34), comorbidity modifiers (HC-35), and contraindication rules (HC-36) are later
tickets that slot into the same result object.

## 2. Guideline basis (2025 AHA/ACC, DOI 10.1161/HYP.0000000000000249)

BP categories (higher of SBP/DBP wins):

| Category | SBP | | DBP |
|---|---|---|---|
| Normal | <120 | and | <80 |
| Elevated | 120–129 | and | <80 |
| Stage 1 | 130–139 | or | 80–89 |
| Stage 2 | ≥140 | or | ≥90 |

Treatment logic:

- **Stage 2** → initiate pharmacotherapy + lifestyle.
- **Stage 1** → initiate pharmacotherapy **only if high-risk**, else lifestyle only.
  High-risk = **any** of: estimated 10-yr total-CVD risk (PREVENT) ≥ 7.5%, diabetes, CKD (with
  albuminuria), or clinical CVD. **Age is NOT a standalone trigger** — it enters the decision
  only through its weight in the PREVENT risk score (decision 2026-07-18, correcting an earlier
  framing that listed age ≥ 65 as its own trigger). Because PREVENT is defined for ages 30–79, a
  low-risk Stage-1 adult outside that range has `prevent_10yr = None` and therefore ABSTAINS.
- **Elevated / Normal** → lifestyle only, no drug indicated.
- **Intensification:** a patient already on BP medication whose BP is above goal
  (**goal < 130/80**) → intensify (uptitrate/add agent). On meds and at goal → continue.

## 3. Architecture — composable rules + thin orchestrator

New `engine/` package, sibling to `pipelines/` and `vocab.py`:

```
engine/
  __init__.py
  types.py         # Decision enum, Citation, TraceStep, EngineDecision
  citations.py     # anchor-id -> guideline text registry (all tied to the 2025 DOI)
  rules/
    __init__.py
    aha_acc_2025/
      __init__.py
      staging.py                       # HC-32
      initiation_intensification.py    # HC-33
  evaluate.py      # evaluate(profile) -> EngineDecision (staging -> initiation; grows w/ HC-34+)
tests/
  test_engine_staging.py               # HC-32
  test_engine_initiation.py            # HC-33
```

Each rule is a small, independently-testable function returning a partial result; `evaluate()`
composes them. Later rules (HC-34–37) are added as new modules without editing existing ones.
Tests stay flat in `tests/` to match the existing convention.

## 4. Decision object (`engine/types.py`)

```python
class Decision(str, Enum):
    INITIATE_PHARMACOTHERAPY  = "initiate_pharmacotherapy"
    INTENSIFY_PHARMACOTHERAPY = "intensify_pharmacotherapy"
    LIFESTYLE_ONLY            = "lifestyle_only"
    AT_GOAL_CONTINUE          = "at_goal_continue"
    ABSTAIN                   = "abstain"

@dataclass(frozen=True)
class Citation:
    anchor: str   # e.g. "AHA-ACC-2025:stage1-high-risk-initiate"
    text: str     # short human-readable guideline statement

@dataclass(frozen=True)
class TraceStep:
    rule: str            # which rule fired, e.g. "bp_staging"
    detail: str          # human-readable reasoning
    citation: str | None # anchor id backing this step

@dataclass(frozen=True)
class EngineDecision:
    decision: Decision
    bp_stage: str | None
    triggers: tuple[str, ...]        # e.g. ("prevent_ge_7.5", "diabetes")
    abstain_reason: str | None       # not_encoded reason when decision == ABSTAIN
    citations: tuple[Citation, ...]  # guideline anchors backing the decision
    trace: tuple[TraceStep, ...]     # ordered reasoning steps (feeds HC-39)
```

Extensible additively: HC-34 adds a `drug_classes` field, HC-36 adds contraindication flags —
no change to the fields above, so no churn to earlier rules or their tests.

## 5. HC-32 — staging rule (`staging.py`)

`stage_bp(profile) -> tuple[str | None, Citation, TraceStep]`

- Delegates the threshold logic to `vocab.bp_stage_scalar` (single source of truth).
- If `bp_context == "admission"` (ED/ICU acute BP) **or** sbp/dbp is null → returns
  `stage = None`, signalling the caller to abstain on chronic staging.
- Otherwise returns the stage plus the staging-threshold citation and one trace step.

## 6. HC-33 — initiation / intensification (`initiation_intensification.py`)

`recommend(profile) -> EngineDecision`. BP goal = **< 130/80**. Decision table:

| Condition | Decision | Abstain reason / triggers |
|---|---|---|
| `bp_context == admission`, or sbp/dbp/stage null | ABSTAIN | `acute_context` / `unknown_bp` |
| `on_bp_meds` null (BP known) | ABSTAIN | `med_status_unknown` |
| On meds + stage normal/elevated (BP < 130/80) | AT_GOAL_CONTINUE | — |
| On meds + stage1/stage2 (BP ≥ 130/80) | INTENSIFY | — |
| Not on meds + stage2 | INITIATE | trigger `stage2` |
| Not on meds + stage1 + **any** high-risk known-True | INITIATE | triggers = the ones that fired |
| Not on meds + stage1 + all high-risk known-False + PREVENT < 7.5% | LIFESTYLE_ONLY | — |
| Not on meds + stage1 + high-risk indeterminate | ABSTAIN | `stage1_risk_indeterminate` |
| Not on meds + normal/elevated | LIFESTYLE_ONLY | — |

High-risk set: `prevent_10yr ≥ 7.5`, `diabetes`, `ckd_albuminuria`, `clinical_cvd`. Age is not a
trigger (it is a PREVENT input only). The indeterminacy judgment covers
`{diabetes, ckd_albuminuria, prevent_ge_7.5}`.

**Input robustness (decision 2026-07-18):** the engine consumes real pandas-derived profiles, so
it reads inputs defensively: a numpy-bool (from a pandas bool column) is read as its boolean value,
and a numeric field that is `NaN` (how a missing PREVENT arrives in a pandas row) resolves to
"unknown" rather than being compared as a number. Helpers `_tri` (booleans) and `_num` (numbers)
enforce this so a missing determinant never masquerades as a definite value.

**Three-valued logic (the core safety behavior):**

- A **known-True** high-risk condition short-circuits to INITIATE — PREVENT may be null and the
  decision still fires (we don't need the risk score once a hard high-risk condition is present).
- ABSTAIN fires **only** when nothing is known-True *and* a needed determinant is genuinely
  unknown (a high-risk flag is NA, or PREVENT is null and the known flags don't settle it). We
  abstain rather than guess low-risk. This is the "any case the engine can't resolve → ABSTAIN,
  never a guess" principle.
- `on_bp_meds` being null: if BP determinants are known, treat unknown medication status
  conservatively — cannot distinguish initiate vs intensify → ABSTAIN (`med_status_unknown`).

## 7. Schema change

`clinical_cvd` is used by the high-risk trigger but is not currently a PatientProfile field
(vocab lists it among `COMORBIDITY_FLAGS`, but the profile schema does not carry it). HC-33 adds:

```json
"clinical_cvd": {"type": ["boolean", "null"],
                 "description": "established atherosclerotic CVD; high-risk trigger for Stage-1 initiation"}
```

NHANES cannot ascertain this reliably, so the NHANES pipeline emits it as null. **`clinical_cvd`
is a positive-only trigger** (decision 2026-07-18): known-True fires INITIATE, but null/False is
**ignored** — it does NOT contribute to abstention. Otherwise every untreated Stage-1 NHANES row
(all null here) would abstain, emptying the cohort. Abstention is judged only over
`{diabetes, ckd_albuminuria, prevent_ge_7.5}`. MIMIC can populate `clinical_cvd` later from ICD
(HC-16), where known-True will then fire correctly.

## 8. Citations (`engine/citations.py`)

A registry mapping stable symbolic anchor ids → short guideline text, all tied to DOI
10.1161/HYP.0000000000000249. Anchors needed for HC-32/33:

- `AHA-ACC-2025:bp-categories` — staging thresholds
- `AHA-ACC-2025:stage2-initiate`
- `AHA-ACC-2025:stage1-high-risk-initiate` (+ the high-risk condition set, incl. PREVENT ≥ 7.5%)
- `AHA-ACC-2025:stage1-lowrisk-lifestyle`, `:elevated-lifestyle`, `:normal-lifestyle`
- `AHA-ACC-2025:bp-goal-130-80` (intensification / at-goal)
- `AHA-ACC-2025:acute-context-not-encoded` (abstention)

**Assumption (approved):** the 2025 guideline PDF is not in the repo, so anchors are stable
symbolic ids with paraphrased text; exact printed section numbers are verified against the
source document when HC-38 (citation linker) formalizes them.

## 9. Testing (TDD — tests written first)

- **`test_engine_staging.py`:** boundary matrix reusing the known BP boundaries
  (118/78→normal, 120/79→elevated, 130/79→stage1, 140/85→stage2, isolated-diastolic cases);
  `admission` context → None; null sbp/dbp → None.
- **`test_engine_initiation.py`:** case matrix over stage × on_meds × each high-risk condition ×
  PREVENT (present / null) × NA-unknown. Every case asserts the `decision`, the exact `triggers`
  set, and — for the indeterminate cases — that ABSTAIN fires with the right reason. Every
  non-abstain decision asserts ≥ 1 citation and a non-empty trace.

## 10. Error handling

Pure function; never raises on missing/None data — missing determinants resolve to ABSTAIN.
Values outside the schema enums (should not occur post-validation) are treated as unknown → ABSTAIN.

## 11. Out of scope (later tickets)

Drug-class selection (HC-34), comorbidity drug modifiers (HC-35), contraindication avoid-logic
(HC-36), the standalone abstention module refactor (HC-37), the citation linker's exact section
strings (HC-38), and the trace formatter for `trace_concordance` (HC-39). HC-32/33 provide the
result object and the two rules those tickets build on.
