# HTN-Concord Engine Rules HC-32 / HC-33 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `engine/` package and implement the first two 2025 AHA/ACC guideline rules — BP staging (HC-32) and initiation/intensification (HC-33) — as pure, cited, unit-tested functions producing a canonical `EngineDecision`.

**Architecture:** A new top-level `engine/` package (sibling to `pipelines/` and `vocab.py`). Each guideline rule is a small independently-testable function; a thin `evaluate()` composes them. Every decision carries guideline citations and an ordered reasoning trace. Missing/unknown determinants resolve to `ABSTAIN` (never a guess) via three-valued logic.

**Tech Stack:** Python 3.12, dataclasses + `enum`, `pytest`, `jsonschema` (already a dependency). Reuses `vocab.bp_stage_scalar`, `vocab.BP_THRESHOLDS`, `vocab.PREVENT_STAGE1_TREAT`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-17-htn-engine-rules-design.md` (approved).
- **Input contract:** a `PatientProfile` is a plain `dict` / `Mapping[str, Any]` matching `schemas/patient_profile.schema.json`. A value of `None` (or a missing key) means "genuinely unknown"; it is **never** coerced to a definite value.
- **BP goal (2025 AHA/ACC):** `< 130/80` mmHg for treated patients.
- **Stage-1 high-risk set:** any of `prevent_10yr >= 7.5`, `diabetes`, `ckd_albuminuria`, `clinical_cvd`. **Age is NOT a standalone trigger** — it enters the decision only through its weight in the PREVENT score (PREVENT is defined for ages 30–79, so a low-risk Stage-1 adult outside that range has `prevent_10yr = None` and abstains rather than being initiated). Do **not** re-add an `age >= 65` rule.
- **`clinical_cvd` modelling decision (refines spec §6):** `clinical_cvd` is a **positive-only** trigger — it fires INITIATE when known-`True`, but its absence/`None` does **not** contribute to the "indeterminate → abstain" check. Rationale: NHANES cannot ascertain it, so treating its `None` as indeterminate would force blanket abstention across the primary cohort. The indeterminacy check therefore covers only `{diabetes, ckd_albuminuria, prevent_ge_7.5}`.
- **Staging return type (refines spec §5):** `stage_bp` returns a small `StagingResult` dataclass (not a bare 3-tuple) so the abstention reason propagates to the caller.
- **Thresholds:** never hard-code BP numbers in the engine — always go through `vocab`.
- **Git:** this project is **not** a git repository yet. The "commit" step in each task is written for convenience; run `git init` first if you want history, otherwise treat commit steps as no-ops and rely on the full-suite run as the checkpoint.
- **Run tests from** `htn-concord/` (that dir is pytest's rootdir; `import vocab` / `import engine` resolve there).

---

## File Structure

- Create `engine/__init__.py` — package marker.
- Create `engine/types.py` — `Decision`, `Citation`, `TraceStep`, `StagingResult`, `EngineDecision`.
- Create `engine/citations.py` — the guideline citation registry + `cite()`.
- Create `engine/rules/__init__.py`, `engine/rules/aha_acc_2025/__init__.py` — package markers.
- Create `engine/rules/aha_acc_2025/staging.py` — HC-32 `stage_bp`.
- Create `engine/rules/aha_acc_2025/initiation_intensification.py` — HC-33 `recommend`.
- Create `engine/evaluate.py` — `evaluate(profile)` orchestrator.
- Modify `schemas/patient_profile.schema.json` — add `clinical_cvd`.
- Modify `pipelines/nhanes/build_profiles.py:18` — add `clinical_cvd` to `PROFILE_COLUMNS`.
- Create tests: `tests/test_engine_types.py`, `tests/test_engine_citations.py`, `tests/test_engine_staging.py`, `tests/test_engine_schema_clinical_cvd.py`, `tests/test_engine_initiation.py`, `tests/test_engine_stage1.py`, `tests/test_engine_evaluate.py`.

---

### Task 1: Engine package + result types

**Files:**
- Create: `engine/__init__.py`, `engine/rules/__init__.py`, `engine/rules/aha_acc_2025/__init__.py`
- Create: `engine/types.py`
- Test: `tests/test_engine_types.py`

**Interfaces:**
- Produces: `Decision` (str enum: `INITIATE_PHARMACOTHERAPY`, `INTENSIFY_PHARMACOTHERAPY`, `LIFESTYLE_ONLY`, `AT_GOAL_CONTINUE`, `ABSTAIN`); `Citation(anchor: str, text: str)`; `TraceStep(rule: str, detail: str, citation: str | None = None)`; `StagingResult(stage: str | None, abstain_reason: str | None, citation: Citation, trace: TraceStep)`; `EngineDecision(decision: Decision, bp_stage: str | None, triggers: tuple[str, ...], abstain_reason: str | None, citations: tuple[Citation, ...], trace: tuple[TraceStep, ...])`. All dataclasses are `frozen=True`.

- [ ] **Step 1: Create the three empty package markers**

```bash
mkdir -p "engine/rules/aha_acc_2025"
printf '"""HTN-Concord deterministic guideline engine."""\n' > engine/__init__.py
printf '"""Guideline rule packages."""\n' > engine/rules/__init__.py
printf '"""2025 AHA/ACC hypertension guideline rules."""\n' > engine/rules/aha_acc_2025/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_engine_types.py`:

```python
"""Tests for the engine result types (HC-32/33 shared contract)."""
import dataclasses

import pytest

from engine.types import Citation, Decision, EngineDecision, StagingResult, TraceStep


def test_decision_enum_values():
    assert Decision.ABSTAIN.value == "abstain"
    assert Decision.INITIATE_PHARMACOTHERAPY.value == "initiate_pharmacotherapy"
    assert Decision.INTENSIFY_PHARMACOTHERAPY.value == "intensify_pharmacotherapy"
    assert Decision.LIFESTYLE_ONLY.value == "lifestyle_only"
    assert Decision.AT_GOAL_CONTINUE.value == "at_goal_continue"


def test_engine_decision_is_frozen():
    d = EngineDecision(Decision.ABSTAIN, None, (), "unknown_bp", (), ())
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.decision = Decision.LIFESTYLE_ONLY


def test_supporting_types_construct():
    c = Citation("A:x", "text")
    t = TraceStep("bp_staging", "detail", c.anchor)
    s = StagingResult(stage="stage1", abstain_reason=None, citation=c, trace=t)
    assert s.stage == "stage1" and t.citation == "A:x" and c.anchor == "A:x"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.types'`

- [ ] **Step 4: Write `engine/types.py`**

```python
"""Result types shared by every guideline rule (HC-32/33 and later rules).

Pure data. A rule returns an EngineDecision; staging returns a StagingResult so its
abstention reason can propagate to the caller. All frozen so decisions are immutable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    INITIATE_PHARMACOTHERAPY = "initiate_pharmacotherapy"    # untreated: Stage 2, or high-risk Stage 1
    INTENSIFY_PHARMACOTHERAPY = "intensify_pharmacotherapy"  # on meds, still above goal (<130/80)
    LIFESTYLE_ONLY = "lifestyle_only"                        # normal/elevated, or low-risk Stage 1, untreated
    AT_GOAL_CONTINUE = "at_goal_continue"                    # on meds, at goal (<130/80)
    ABSTAIN = "abstain"                                      # determinant unknown, or acute-context BP


@dataclass(frozen=True)
class Citation:
    """A guideline anchor backing a decision step."""
    anchor: str   # e.g. "AHA-ACC-2025:stage2-initiate"
    text: str     # short human-readable guideline statement


@dataclass(frozen=True)
class TraceStep:
    """One step of the engine's reasoning (feeds trace_concordance scoring, HC-39)."""
    rule: str                 # which rule fired, e.g. "bp_staging"
    detail: str               # human-readable reasoning
    citation: str | None = None   # anchor id backing this step


@dataclass(frozen=True)
class StagingResult:
    """Output of the staging rule (HC-32). stage is None when the engine must abstain."""
    stage: str | None
    abstain_reason: str | None   # e.g. "acute_context", "unknown_bp"; None when staged
    citation: Citation
    trace: TraceStep


@dataclass(frozen=True)
class EngineDecision:
    """The canonical, citation-linked, traced decision for one PatientProfile."""
    decision: Decision
    bp_stage: str | None
    triggers: tuple[str, ...]        # e.g. ("diabetes", "prevent_ge_7.5")
    abstain_reason: str | None       # not_encoded reason when decision == ABSTAIN
    citations: tuple[Citation, ...]  # guideline anchors backing the decision
    trace: tuple[TraceStep, ...]     # ordered reasoning steps
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_types.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Checkpoint / commit**

Run: `python -m pytest tests/ -q` — expect all green (37 existing + 3 new).

```bash
git add engine/ tests/test_engine_types.py && git commit -m "feat(engine): result types (Decision, Citation, TraceStep, EngineDecision)"
```

---

### Task 2: Citation registry

**Files:**
- Create: `engine/citations.py`
- Test: `tests/test_engine_citations.py`

**Interfaces:**
- Consumes: `Citation` from `engine.types`.
- Produces: `CITATIONS: dict[str, Citation]`; `cite(anchor: str) -> Citation` (raises `KeyError` on unknown anchor); `GUIDELINE_DOI: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_citations.py`:

```python
"""Tests for the guideline citation registry."""
import pytest

from engine.citations import CITATIONS, cite


def test_cite_returns_matching_citation():
    c = cite("AHA-ACC-2025:stage2-initiate")
    assert c.anchor == "AHA-ACC-2025:stage2-initiate"
    assert "Stage 2" in c.text


def test_cite_unknown_anchor_raises():
    with pytest.raises(KeyError):
        cite("AHA-ACC-2025:does-not-exist")


def test_registry_keys_match_citation_anchors():
    for anchor, c in CITATIONS.items():
        assert c.anchor == anchor


def test_required_anchors_present():
    required = {
        "AHA-ACC-2025:bp-categories",
        "AHA-ACC-2025:stage2-initiate",
        "AHA-ACC-2025:stage1-high-risk-initiate",
        "AHA-ACC-2025:stage1-lowrisk-lifestyle",
        "AHA-ACC-2025:elevated-lifestyle",
        "AHA-ACC-2025:normal-lifestyle",
        "AHA-ACC-2025:bp-goal-130-80",
        "AHA-ACC-2025:acute-context-not-encoded",
        "HTN-CONCORD:abstain-insufficient-data",
    }
    assert required <= set(CITATIONS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_citations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.citations'`

- [ ] **Step 3: Write `engine/citations.py`**

```python
"""Guideline citation registry — 2025 AHA/ACC hypertension guideline.

Reference: DOI 10.1161/HYP.0000000000000249. Anchors are stable symbolic ids; the exact
printed section numbers are filled by the citation linker (HC-38) against the source
document. The HTN-CONCORD:* anchor states the engine's own abstention principle.
"""
from __future__ import annotations

from engine.types import Citation

GUIDELINE_DOI = "10.1161/HYP.0000000000000249"

CITATIONS: dict[str, Citation] = {
    "AHA-ACC-2025:bp-categories": Citation(
        "AHA-ACC-2025:bp-categories",
        "BP categories: Normal <120/80; Elevated 120-129/<80; Stage 1 130-139/80-89; Stage 2 >=140/90.",
    ),
    "AHA-ACC-2025:stage2-initiate": Citation(
        "AHA-ACC-2025:stage2-initiate",
        "Stage 2 hypertension: initiate antihypertensive pharmacotherapy plus lifestyle modification.",
    ),
    "AHA-ACC-2025:stage1-high-risk-initiate": Citation(
        "AHA-ACC-2025:stage1-high-risk-initiate",
        "Stage 1: initiate pharmacotherapy when high-risk (established CVD, diabetes, CKD, age >=65, or "
        "estimated 10-year CVD risk >=7.5%); otherwise lifestyle modification.",
    ),
    "AHA-ACC-2025:stage1-lowrisk-lifestyle": Citation(
        "AHA-ACC-2025:stage1-lowrisk-lifestyle",
        "Stage 1 without high-risk features: lifestyle modification, reassess in 3-6 months.",
    ),
    "AHA-ACC-2025:elevated-lifestyle": Citation(
        "AHA-ACC-2025:elevated-lifestyle",
        "Elevated BP: lifestyle modification; no pharmacotherapy indicated.",
    ),
    "AHA-ACC-2025:normal-lifestyle": Citation(
        "AHA-ACC-2025:normal-lifestyle",
        "Normal BP: promote healthy lifestyle; no pharmacotherapy indicated.",
    ),
    "AHA-ACC-2025:bp-goal-130-80": Citation(
        "AHA-ACC-2025:bp-goal-130-80",
        "Treated BP goal <130/80 mmHg; intensify therapy when BP remains above goal.",
    ),
    "AHA-ACC-2025:acute-context-not-encoded": Citation(
        "AHA-ACC-2025:acute-context-not-encoded",
        "Acute-care (ED/ICU/admission) BP does not establish chronic staging; not encoded.",
    ),
    "HTN-CONCORD:abstain-insufficient-data": Citation(
        "HTN-CONCORD:abstain-insufficient-data",
        "Engine abstains (not_encoded) when a determinant required for the decision is unknown.",
    ),
}


def cite(anchor: str) -> Citation:
    """Look up a Citation by anchor id; raise KeyError if it is not registered."""
    try:
        return CITATIONS[anchor]
    except KeyError as exc:
        raise KeyError(f"Unknown citation anchor {anchor!r}") from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_citations.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Checkpoint / commit**

```bash
git add engine/citations.py tests/test_engine_citations.py && git commit -m "feat(engine): guideline citation registry"
```

---

### Task 3: HC-32 — BP staging rule

**Files:**
- Create: `engine/rules/aha_acc_2025/staging.py`
- Test: `tests/test_engine_staging.py`

**Interfaces:**
- Consumes: `vocab.bp_stage_scalar(sbp, dbp) -> str | None`; `cite` from `engine.citations`; `StagingResult`, `TraceStep` from `engine.types`.
- Produces: `stage_bp(profile: Mapping[str, Any]) -> StagingResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_staging.py`:

```python
"""Tests for HC-32 BP staging rule."""
import pytest

from engine.rules.aha_acc_2025.staging import stage_bp


@pytest.mark.parametrize("sbp,dbp,expected", [
    (118, 78, "normal"),
    (120, 79, "elevated"),
    (129, 79, "elevated"),
    (130, 79, "stage1"),   # isolated systolic boundary
    (118, 82, "stage1"),   # isolated diastolic
    (139, 89, "stage1"),
    (140, 85, "stage2"),   # systolic drives
    (135, 90, "stage2"),   # diastolic drives
])
def test_stage_bp_boundaries(sbp, dbp, expected):
    r = stage_bp({"sbp": sbp, "dbp": dbp, "bp_context": "chronic"})
    assert r.stage == expected
    assert r.abstain_reason is None
    assert r.citation.anchor == "AHA-ACC-2025:bp-categories"
    assert r.trace.rule == "bp_staging"


def test_office_context_stages_normally():
    r = stage_bp({"sbp": 145, "dbp": 92, "bp_context": "office"})
    assert r.stage == "stage2"


def test_admission_context_abstains():
    r = stage_bp({"sbp": 180, "dbp": 100, "bp_context": "admission"})
    assert r.stage is None
    assert r.abstain_reason == "acute_context"
    assert r.citation.anchor == "AHA-ACC-2025:acute-context-not-encoded"


def test_missing_bp_abstains():
    r = stage_bp({"sbp": None, "dbp": None, "bp_context": "chronic"})
    assert r.stage is None
    assert r.abstain_reason == "unknown_bp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_staging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.rules.aha_acc_2025.staging'`

- [ ] **Step 3: Write `engine/rules/aha_acc_2025/staging.py`**

```python
"""HC-32 — 2025 AHA/ACC blood-pressure staging as a cited engine rule.

Delegates the numeric thresholds to vocab.bp_stage_scalar (single source of truth) and
attaches a guideline citation + one reasoning-trace step. Signals abstention (stage=None)
when BP is acute-context (admission) or missing.
"""
from __future__ import annotations

from typing import Any, Mapping

import vocab

from engine.citations import cite
from engine.types import StagingResult, TraceStep


def stage_bp(profile: Mapping[str, Any]) -> StagingResult:
    context = profile.get("bp_context")
    sbp = profile.get("sbp")
    dbp = profile.get("dbp")

    # Acute-care BP does not establish chronic staging -> abstain.
    if context == "admission":
        c = cite("AHA-ACC-2025:acute-context-not-encoded")
        return StagingResult(
            stage=None,
            abstain_reason="acute_context",
            citation=c,
            trace=TraceStep("bp_staging", "BP is acute-context (admission); chronic staging not encoded.", c.anchor),
        )

    stage = vocab.bp_stage_scalar(sbp, dbp)

    # Missing SBP/DBP -> cannot stage -> abstain.
    if stage is None:
        c = cite("HTN-CONCORD:abstain-insufficient-data")
        return StagingResult(
            stage=None,
            abstain_reason="unknown_bp",
            citation=c,
            trace=TraceStep("bp_staging", "SBP/DBP missing; cannot stage.", c.anchor),
        )

    c = cite("AHA-ACC-2025:bp-categories")
    return StagingResult(
        stage=stage,
        abstain_reason=None,
        citation=c,
        trace=TraceStep("bp_staging", f"BP {sbp}/{dbp} -> {stage}.", c.anchor),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_staging.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Checkpoint / commit**

```bash
git add engine/rules/aha_acc_2025/staging.py tests/test_engine_staging.py && git commit -m "feat(engine): HC-32 BP staging rule"
```

---

### Task 4: Add `clinical_cvd` to the profile contract

**Files:**
- Modify: `schemas/patient_profile.schema.json` (add `clinical_cvd` property)
- Modify: `pipelines/nhanes/build_profiles.py:18` (`PROFILE_COLUMNS`)
- Test: `tests/test_engine_schema_clinical_cvd.py`

**Interfaces:**
- Produces: profiles may carry `clinical_cvd: boolean | null`. NHANES emits it as null (the `for c in PROFILE_COLUMNS` loop at `build_profiles.py:91` fills absent columns with `pd.NA`, and `validate._row_to_jsonable` maps `pd.NA` → `None`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_schema_clinical_cvd.py`:

```python
"""clinical_cvd is part of the PatientProfile contract (added for HC-33)."""
import json
from pathlib import Path

import jsonschema

_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "patient_profile.schema.json"


def _schema():
    return json.loads(_SCHEMA.read_text())


def test_schema_declares_clinical_cvd():
    prop = _schema()["properties"]["clinical_cvd"]
    assert prop["type"] == ["boolean", "null"]


def test_profile_with_clinical_cvd_validates():
    row = {
        "source": "nhanes", "age": 60, "sex": "male", "sbp": 135, "dbp": 85,
        "bp_stage": "stage1", "bp_context": "chronic", "med_classes": [],
        "contraindications": [], "clinical_cvd": None,
    }
    jsonschema.Draft7Validator(_schema()).validate(row)
    row["clinical_cvd"] = True
    jsonschema.Draft7Validator(_schema()).validate(row)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_schema_clinical_cvd.py -v`
Expected: FAIL with `KeyError: 'clinical_cvd'`

- [ ] **Step 3: Add the property to `schemas/patient_profile.schema.json`**

Find this line:

```json
    "diabetes": {"type": ["boolean", "null"]},
```

Insert immediately after it:

```json
    "clinical_cvd": {"type": ["boolean", "null"], "description": "established atherosclerotic CVD; high-risk trigger for Stage-1 initiation. NHANES emits null."},
```

- [ ] **Step 4: Add the column to the NHANES pipeline**

In `pipelines/nhanes/build_profiles.py`, find in `PROFILE_COLUMNS` (starts line 18):

```python
    "diabetes", "hba1c",
```

Change it to:

```python
    "diabetes", "clinical_cvd", "hba1c",
```

(No other change needed: the loop at `build_profiles.py:91` sets absent columns to `pd.NA`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine_schema_clinical_cvd.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Verify the NHANES pipeline still validates (regression)**

Run: `python -m pytest tests/test_clean_and_qa.py tests/test_derive.py -q`
Expected: PASS (no regressions). If NHANES raw data is present locally, optionally run `python -m pipelines.nhanes.build_profiles` and confirm it still prints "profiles validate against patient_profile.schema.json"; skip if raw data absent.

- [ ] **Step 7: Checkpoint / commit**

```bash
git add schemas/patient_profile.schema.json pipelines/nhanes/build_profiles.py tests/test_engine_schema_clinical_cvd.py && git commit -m "feat(schema): add clinical_cvd to PatientProfile (HC-33 high-risk trigger)"
```

---

### Task 5: HC-33 — recommend(), definite branches

**Files:**
- Create: `engine/rules/aha_acc_2025/initiation_intensification.py`
- Test: `tests/test_engine_initiation.py`

**Interfaces:**
- Consumes: `stage_bp` from `engine.rules.aha_acc_2025.staging`; `cite` from `engine.citations`; `Decision`, `EngineDecision`, `TraceStep` from `engine.types`; `vocab.PREVENT_STAGE1_TREAT`.
- Produces: `recommend(profile: Mapping[str, Any]) -> EngineDecision`; helper `_tri(value) -> bool | None`. (The Stage-1 branch raises `NotImplementedError` until Task 6.)

- [ ] **Step 1: Write the failing test (definite branches only)**

Create `tests/test_engine_initiation.py`:

```python
"""HC-33 initiation/intensification — definite (non-Stage-1) branches."""
from engine.rules.aha_acc_2025.initiation_intensification import _tri, recommend
from engine.types import Decision


def _p(**over):
    base = {"sbp": 135, "dbp": 85, "bp_context": "chronic", "on_bp_meds": False}
    base.update(over)
    return base


def test_tri_three_valued():
    assert _tri(True) is True
    assert _tri(False) is False
    assert _tri(None) is None
    assert _tri("x") is None


def test_admission_context_abstains():
    d = recommend(_p(bp_context="admission", sbp=180, dbp=100))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "acute_context"
    assert d.citations and d.trace


def test_unknown_bp_abstains():
    d = recommend(_p(sbp=None, dbp=None))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "unknown_bp"


def test_unknown_med_status_abstains():
    d = recommend(_p(sbp=150, dbp=95, on_bp_meds=None))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "med_status_unknown"
    assert d.bp_stage == "stage2"


def test_on_meds_above_goal_intensifies():
    d = recommend(_p(sbp=150, dbp=95, on_bp_meds=True))
    assert d.decision is Decision.INTENSIFY_PHARMACOTHERAPY
    assert d.bp_stage == "stage2"


def test_on_meds_at_goal_continues():
    d = recommend(_p(sbp=122, dbp=78, on_bp_meds=True))
    assert d.decision is Decision.AT_GOAL_CONTINUE
    assert d.bp_stage == "elevated"


def test_untreated_stage2_initiates():
    d = recommend(_p(sbp=150, dbp=95, on_bp_meds=False))
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert d.triggers == ("stage2",)


def test_untreated_normal_is_lifestyle():
    d = recommend(_p(sbp=118, dbp=76, on_bp_meds=False))
    assert d.decision is Decision.LIFESTYLE_ONLY
    assert d.bp_stage == "normal"


def test_untreated_elevated_is_lifestyle():
    d = recommend(_p(sbp=124, dbp=78, on_bp_meds=False))
    assert d.decision is Decision.LIFESTYLE_ONLY
    assert d.bp_stage == "elevated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_initiation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.rules.aha_acc_2025.initiation_intensification'`

- [ ] **Step 3: Write `engine/rules/aha_acc_2025/initiation_intensification.py`**

```python
"""HC-33 — 2025 AHA/ACC initiation / intensification decision as a cited engine rule.

Pure function of a PatientProfile. Composes staging (HC-32), then decides initiate /
intensify / lifestyle / continue / abstain. Missing determinants resolve to ABSTAIN via
three-valued logic (see _tri). The Stage-1 high-risk branch lands in the next task.
"""
from __future__ import annotations

from typing import Any, Mapping

import vocab

from engine.citations import cite
from engine.rules.aha_acc_2025.staging import stage_bp
from engine.types import Decision, EngineDecision, TraceStep

_STAGE1_TREAT = vocab.PREVENT_STAGE1_TREAT  # 7.5% 10-yr CVD risk


def _tri(value: Any) -> bool | None:
    """Three-valued read: a real boolean -> its value; anything else -> None (unknown).

    Accepts a Python bool or a numpy bool (what a pandas row yields for a bool column).
    Plain ints 0/1 are deliberately NOT treated as booleans (`1 == True` in Python):
    a stray 1 read as True would silently mask a missing determinant.
    """
    if isinstance(value, bool):
        return value
    if getattr(getattr(value, "dtype", None), "kind", None) == "b":
        return bool(value)
    return None


def _num(value: Any) -> float | None:
    """Read a real, finite number -> float; None / NaN / bool / non-numeric -> None.

    Guards numeric comparisons (the PREVENT threshold): a missing risk score arrives as
    float('nan') in a pandas row, and `isinstance(nan, float)` is True, so a naive
    `nan >= 7.5` would silently read as low-risk. NaN must resolve to 'unknown' instead.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> None


def recommend(profile: Mapping[str, Any]) -> EngineDecision:
    staging = stage_bp(profile)
    citations = [staging.citation]
    trace = [staging.trace]

    # 1. Cannot stage (acute context or missing BP) -> abstain.
    if staging.stage is None:
        return EngineDecision(Decision.ABSTAIN, None, (), staging.abstain_reason,
                              tuple(citations), tuple(trace))
    stage = staging.stage

    # 2. Medication status must be known to choose initiate vs intensify.
    on_meds = _tri(profile.get("on_bp_meds"))
    if on_meds is None:
        c = cite("HTN-CONCORD:abstain-insufficient-data")
        citations.append(c)
        trace.append(TraceStep("initiation", "Medication status unknown; cannot decide initiate vs intensify.", c.anchor))
        return EngineDecision(Decision.ABSTAIN, stage, (), "med_status_unknown",
                              tuple(citations), tuple(trace))

    # 3. Already treated: goal is <130/80 -> intensify if above goal, else continue.
    if on_meds is True:
        c = cite("AHA-ACC-2025:bp-goal-130-80")
        citations.append(c)
        if stage in ("stage1", "stage2"):
            trace.append(TraceStep("intensification", f"On BP meds, {stage} (above goal <130/80) -> intensify.", c.anchor))
            return EngineDecision(Decision.INTENSIFY_PHARMACOTHERAPY, stage, (), None,
                                  tuple(citations), tuple(trace))
        trace.append(TraceStep("intensification", f"On BP meds, {stage} (at goal <130/80) -> continue current therapy.", c.anchor))
        return EngineDecision(Decision.AT_GOAL_CONTINUE, stage, (), None,
                              tuple(citations), tuple(trace))

    # 4. Untreated: stage drives initiation.
    if stage == "stage2":
        c = cite("AHA-ACC-2025:stage2-initiate")
        citations.append(c)
        trace.append(TraceStep("initiation", "Untreated Stage 2 -> initiate pharmacotherapy.", c.anchor))
        return EngineDecision(Decision.INITIATE_PHARMACOTHERAPY, stage, ("stage2",), None,
                              tuple(citations), tuple(trace))

    if stage in ("normal", "elevated"):
        anchor = "AHA-ACC-2025:normal-lifestyle" if stage == "normal" else "AHA-ACC-2025:elevated-lifestyle"
        c = cite(anchor)
        citations.append(c)
        trace.append(TraceStep("initiation", f"Untreated {stage} -> lifestyle only.", c.anchor))
        return EngineDecision(Decision.LIFESTYLE_ONLY, stage, (), None,
                              tuple(citations), tuple(trace))

    # stage == "stage1": high-risk determination lands in the next task.
    raise NotImplementedError("Stage-1 high-risk logic is implemented in the next task")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_initiation.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Checkpoint / commit**

```bash
git add engine/rules/aha_acc_2025/initiation_intensification.py tests/test_engine_initiation.py && git commit -m "feat(engine): HC-33 recommend() definite branches"
```

---

### Task 6: HC-33 — Stage-1 high-risk + three-valued abstention

**Files:**
- Modify: `engine/rules/aha_acc_2025/initiation_intensification.py` (replace the `NotImplementedError` line; add `_stage1_decision`)
- Test: `tests/test_engine_stage1.py`

**Interfaces:**
- Consumes: everything from Task 5.
- Produces: `_stage1_decision(profile, stage, citations, trace) -> EngineDecision`. Indeterminacy set `{diabetes, ckd_albuminuria, prevent_ge_7.5}`; `clinical_cvd` is a positive-only trigger; **age is not a standalone trigger** (it enters only via PREVENT).

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_stage1.py`:

```python
"""HC-33 Stage-1 high-risk trigger + three-valued abstention.

Stage-1 initiation is risk-based: clinical CVD / diabetes / CKD / PREVENT >=7.5%.
Age is NOT a standalone trigger (it enters only via the PREVENT score).
"""
from engine.rules.aha_acc_2025.initiation_intensification import recommend
from engine.types import Decision


def _s1(**over):
    """Untreated Stage 1 (135/85) profile; all high-risk determinants default known-False."""
    base = {
        "sbp": 135, "dbp": 85, "bp_context": "chronic", "on_bp_meds": False,
        "age": 50, "diabetes": False, "ckd_albuminuria": False,
        "clinical_cvd": False, "prevent_10yr": 5.0,
    }
    base.update(over)
    return base


def test_diabetes_initiates_even_if_prevent_missing():
    d = recommend(_s1(diabetes=True, prevent_10yr=None))
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert "diabetes" in d.triggers


def test_prevent_over_threshold_initiates():
    d = recommend(_s1(prevent_10yr=10.0))
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert d.triggers == ("prevent_ge_7.5",)


def test_ckd_initiates():
    d = recommend(_s1(ckd_albuminuria=True))
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert "ckd_albuminuria" in d.triggers


def test_clinical_cvd_true_initiates_even_if_prevent_missing():
    d = recommend(_s1(clinical_cvd=True, prevent_10yr=None))
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert "clinical_cvd" in d.triggers


def test_age_alone_does_not_initiate():
    # Age is not a standalone trigger; an otherwise-low-risk older adult gets lifestyle.
    d = recommend(_s1(age=70))
    assert d.decision is Decision.LIFESTYLE_ONLY
    assert d.triggers == ()


def test_multiple_triggers_all_listed_sorted():
    d = recommend(_s1(diabetes=True, ckd_albuminuria=True, prevent_10yr=12.0))
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert d.triggers == ("ckd_albuminuria", "diabetes", "prevent_ge_7.5")


def test_all_known_low_risk_is_lifestyle():
    d = recommend(_s1())  # all False, prevent 5.0
    assert d.decision is Decision.LIFESTYLE_ONLY
    assert d.triggers == ()


def test_clinical_cvd_none_does_not_force_abstain():
    # clinical_cvd unknown but every other determinant known-low -> still lifestyle.
    d = recommend(_s1(clinical_cvd=None))
    assert d.decision is Decision.LIFESTYLE_ONLY


def test_unknown_determinant_abstains():
    # diabetes unknown, prevent uncomputable -> cannot rule out high-risk -> abstain.
    d = recommend(_s1(diabetes=None, prevent_10yr=None))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "stage1_risk_indeterminate"


def test_prevent_uncomputable_abstains_though_comorbidities_low():
    # Comorbidities known-False but PREVENT uncomputable (e.g. age outside 30-79) ->
    # cannot rule out >=7.5% risk -> abstain, do not default to lifestyle.
    d = recommend(_s1(age=82, prevent_10yr=None))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "stage1_risk_indeterminate"


def test_nan_prevent_abstains_not_lifestyle():
    # A missing PREVENT arrives as float('nan') from a pandas row, not Python None.
    # isinstance(nan, float) is True, so a naive comparison would read it as <7.5 (low-risk)
    # and wrongly recommend lifestyle. The engine must instead abstain.
    d = recommend(_s1(prevent_10yr=float("nan")))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "stage1_risk_indeterminate"


def test_every_stage1_decision_has_citation_and_trace():
    for d in (recommend(_s1(diabetes=True)), recommend(_s1()), recommend(_s1(diabetes=None, prevent_10yr=None))):
        assert d.citations and d.trace
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_stage1.py -v`
Expected: FAIL — the Stage-1 profiles hit `NotImplementedError`.

- [ ] **Step 3: Implement `_stage1_decision` and wire it in**

In `engine/rules/aha_acc_2025/initiation_intensification.py`, replace this line:

```python
    # stage == "stage1": high-risk determination lands in the next task.
    raise NotImplementedError("Stage-1 high-risk logic is implemented in the next task")
```

with:

```python
    # stage == "stage1": high-risk determination (three-valued).
    return _stage1_decision(profile, stage, citations, trace)


def _stage1_decision(profile, stage, citations, trace) -> EngineDecision:
    """Untreated Stage 1: initiate iff any high-risk feature; else lifestyle; else abstain.

    Stage-1 initiation is risk-based: established clinical CVD, diabetes, CKD (with
    albuminuria), or PREVENT 10-year total-CVD risk >=7.5%. Age is NOT a standalone trigger
    -- it enters the decision only through its weight in the PREVENT score. Because PREVENT
    is defined for ages 30-79, a low-risk Stage-1 adult outside that range has
    prevent_10yr = None and therefore abstains rather than being initiated.

    Indeterminacy is judged over {diabetes, ckd_albuminuria, prevent_ge_7.5}. clinical_cvd is
    a positive-only trigger: known-True fires INITIATE, but its absence/None is ignored
    (NHANES cannot ascertain it, so it must not force abstention).
    """
    prevent = _num(profile.get("prevent_10yr"))

    determinants = {
        "diabetes": _tri(profile.get("diabetes")),
        "ckd_albuminuria": _tri(profile.get("ckd_albuminuria")),
        "prevent_ge_7.5": (prevent >= _STAGE1_TREAT) if prevent is not None else None,
    }
    clinical_cvd = _tri(profile.get("clinical_cvd"))

    fired = [name for name, v in determinants.items() if v is True]
    if clinical_cvd is True:
        fired.append("clinical_cvd")
    fired = tuple(sorted(fired))

    # Any high-risk feature known-True -> initiate (PREVENT not required once one fires).
    if fired:
        c = cite("AHA-ACC-2025:stage1-high-risk-initiate")
        citations.append(c)
        trace.append(TraceStep("initiation", f"Untreated Stage 1, high-risk ({', '.join(fired)}) -> initiate.", c.anchor))
        return EngineDecision(Decision.INITIATE_PHARMACOTHERAPY, stage, fired, None,
                              tuple(citations), tuple(trace))

    # None fired. Every risk determinant known-False -> low risk -> lifestyle.
    if all(v is False for v in determinants.values()):
        c = cite("AHA-ACC-2025:stage1-lowrisk-lifestyle")
        citations.append(c)
        trace.append(TraceStep("initiation", "Untreated Stage 1, no high-risk features -> lifestyle only.", c.anchor))
        return EngineDecision(Decision.LIFESTYLE_ONLY, stage, (), None,
                              tuple(citations), tuple(trace))

    # Otherwise a needed determinant is unknown -> abstain rather than guess low-risk.
    c = cite("HTN-CONCORD:abstain-insufficient-data")
    citations.append(c)
    trace.append(TraceStep("initiation", "Untreated Stage 1, high-risk status indeterminate (missing determinant) -> abstain.", c.anchor))
    return EngineDecision(Decision.ABSTAIN, stage, (), "stage1_risk_indeterminate",
                          tuple(citations), tuple(trace))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_stage1.py tests/test_engine_initiation.py -v`
Expected: PASS (both files; Stage-1 = 12 tests, definite = 10 tests)

- [ ] **Step 5: Checkpoint / commit**

```bash
git add engine/rules/aha_acc_2025/initiation_intensification.py tests/test_engine_stage1.py && git commit -m "feat(engine): HC-33 Stage-1 high-risk trigger + abstention"
```

---

### Task 7: evaluate() orchestrator + end-to-end test

**Files:**
- Create: `engine/evaluate.py`
- Test: `tests/test_engine_evaluate.py`

**Interfaces:**
- Consumes: `recommend` from `engine.rules.aha_acc_2025.initiation_intensification`; `EngineDecision`.
- Produces: `evaluate(profile: Mapping[str, Any]) -> EngineDecision` — the stable public entry point.

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_evaluate.py`:

```python
"""End-to-end tests for the engine's public entry point."""
from engine.evaluate import evaluate
from engine.types import Decision


def test_evaluate_realistic_nhanes_profile_initiates():
    # 62-yo diabetic, Stage 1, untreated -> initiate (diabetes fires).
    profile = {
        "source": "nhanes", "age": 62, "sex": "female", "sbp": 134, "dbp": 84,
        "bp_context": "chronic", "on_bp_meds": False, "diabetes": True,
        "ckd_albuminuria": False, "clinical_cvd": None, "prevent_10yr": 9.1,
        "med_classes": [], "contraindications": [],
    }
    d = evaluate(profile)
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert "diabetes" in d.triggers
    assert d.bp_stage == "stage1"
    assert d.citations and d.trace


def test_evaluate_icu_profile_abstains():
    profile = {"source": "mimic_iv", "age": 55, "sbp": 175, "dbp": 99,
               "bp_context": "admission", "on_bp_meds": True,
               "med_classes": [], "contraindications": []}
    d = evaluate(profile)
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "acute_context"


def test_evaluate_returns_engine_decision_type():
    from engine.types import EngineDecision
    d = evaluate({"sbp": 118, "dbp": 76, "bp_context": "chronic", "on_bp_meds": False})
    assert isinstance(d, EngineDecision)
    assert d.decision is Decision.LIFESTYLE_ONLY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_evaluate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.evaluate'`

- [ ] **Step 3: Write `engine/evaluate.py`**

```python
"""Top-level engine entry point.

Composes the 2025 AHA/ACC rules into one decision for a PatientProfile. Thin for now
(staging -> initiation/intensification, both handled inside recommend()). As later rules
land (HC-34 drug-class selection, HC-36 contraindications), they compose here.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.rules.aha_acc_2025.initiation_intensification import recommend
from engine.types import EngineDecision


def evaluate(profile: Mapping[str, Any]) -> EngineDecision:
    """Return the deterministic guideline decision for one PatientProfile."""
    return recommend(profile)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_evaluate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Full-suite checkpoint / commit**

Run: `python -m pytest tests/ -q`
Expected: PASS — 37 pre-existing + all new engine tests (≈ 44 new).

```bash
git add engine/evaluate.py tests/test_engine_evaluate.py && git commit -m "feat(engine): evaluate() orchestrator + end-to-end tests"
```

---

### Task 8: Correct stale status records + update trackers

**Files:**
- Modify: `docs/HTN-Concord_Master_Plan.md` (the "9 tests" claim, line ~121)
- Modify: `docs/HTN-Concord_Backlog.md` (HC-32/HC-33 status rows)
- Update: Notion progress tracker rows HC-32, HC-33
- Update: memory file `htn-concord-project.md`

**Interfaces:** none (documentation/tracking only).

- [ ] **Step 1: Fix the Master Plan's false claim**

In `docs/HTN-Concord_Master_Plan.md`, find the row asserting
`engine/rules/aha_acc_2025/initiation_intensification.py | ✅ (9 tests)` and change its status
to reflect reality after this plan: `✅ (HC-32/33 built: staging + initiation/intensification, ~44 tests)`.

- [ ] **Step 2: Update the Backlog**

In `docs/HTN-Concord_Backlog.md`, set HC-32 status to `✅` and HC-33 status to `✅`
(initiation/intensification now consumes the PREVENT ≥7.5% gate + abstention).

- [ ] **Step 3: Update the Notion progress tracker**

Query the tracker data source (`339526e6-7360-4472-9e51-a8c2cc3fbc3d`) for the HC-32 and HC-33
pages and set each Status to `Done`, updating Notes ("engine built from scratch; staging +
initiation/intensification, ~44 tests, citations + trace").

- [ ] **Step 4: Correct the memory file**

Update `/Users/aria/.claude/projects/-Users-aria-Documents-PhD-GenAI/memory/htn-concord-project.md`:
remove the "Initiation/intensification rule exists (9 tests)" claim; record that the `engine/`
package and HC-32/HC-33 were built in this session (staging, initiation/intensification, the
`EngineDecision` result object with citations + trace, and the `clinical_cvd` schema field).

- [ ] **Step 5: Final verification**

Run: `python -m pytest tests/ -q`
Expected: PASS (all tests green).

```bash
git add docs/ && git commit -m "docs: correct engine status; HC-32/33 done"
```

---

## Self-Review

**Spec coverage:**
- §3 architecture (engine package, composable rules, thin orchestrator) → Tasks 1, 3, 5–7. ✓
- §4 EngineDecision/Citation/TraceStep → Task 1. ✓
- §5 HC-32 staging (wraps `vocab.bp_stage_scalar`, admission/null → abstain) → Task 3. ✓
- §6 HC-33 decision table incl. `on_bp_meds`-null → abstain, three-valued Stage-1 → Tasks 5, 6. ✓
- §7 `clinical_cvd` schema change + NHANES null → Task 4. ✓
- §8 citations registry → Task 2. ✓
- §9 TDD test plan (staging boundary matrix; initiation case matrix; ≥1 citation + non-empty trace per decision) → Tasks 3, 5, 6, 7. ✓
- §1 correction of the stale "9 tests" claim → Task 8. ✓

**Placeholder scan:** no TBD/TODO; every code step shows full code; the single `NotImplementedError` in Task 5 is intentional WIP explicitly removed in Task 6. ✓

**Type consistency:** `stage_bp → StagingResult` (Task 3) consumed in Task 5; `recommend → EngineDecision` (Task 5) consumed by `_stage1_decision` (Task 6) and `evaluate` (Task 7); `Decision`/`Citation`/`TraceStep` names identical across tasks; `cite(anchor)` used consistently; trigger names (`diabetes`, `ckd_albuminuria`, `prevent_ge_7.5`, `clinical_cvd`, `stage2`) match between rule and tests (age is not a standalone trigger). ✓
