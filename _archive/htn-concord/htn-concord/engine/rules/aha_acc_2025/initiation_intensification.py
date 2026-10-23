"""HC-33 — 2025 AHA/ACC initiation / intensification decision as a cited engine rule.

Pure function of a PatientProfile. Composes staging (HC-32), then decides initiate /
intensify / lifestyle / continue / abstain. Missing determinants resolve to ABSTAIN via
three-valued logic (see _tri / _num).

HC-42: the decision is assembled by mutating a `DecisionBuilder` (`contribute`) rather than
by constructing a frozen `EngineDecision` per branch, so later rules (drug class, HC-34;
contraindications, HC-36; trace emitter, HC-39) add to the same builder without touching
this module. `recommend()` remains the public single-guideline entry point.
"""
from __future__ import annotations

from typing import Any, Mapping

import vocab

from engine.builder import DecisionBuilder
from engine.citations import cite
from engine.rules.aha_acc_2025.staging import stage_bp
from engine.types import Decision, EngineDecision, TraceStep

_STAGE1_TREAT = vocab.PREVENT_STAGE1_TREAT  # 7.5% 10-yr CVD risk


def _tri(value: Any) -> bool | None:
    """Three-valued read: a real boolean -> its value; anything else -> None (unknown).

    Accepts a Python bool or a numpy bool (what a pandas row yields for a bool column); a
    numpy scalar is recognised by its dtype kind 'b', which separates it from a numpy int
    without importing numpy. Plain ints 0/1 are deliberately NOT treated as booleans here
    (`1 == True` in Python): treating a stray 1 as True would silently mask a missing
    determinant, which is exactly what this three-valued logic exists to prevent.
    """
    if isinstance(value, bool):
        return value
    if getattr(getattr(value, "dtype", None), "kind", None) == "b":
        return bool(value)
    return None


def _num(value: Any) -> float | None:
    """Read a real, finite number -> float; None / NaN / bool / non-numeric -> None.

    Guards numeric comparisons (e.g. the PREVENT threshold): a missing risk score arrives
    as float('nan') in a pandas row, and `isinstance(nan, float)` is True, so a naive
    `nan >= 7.5` would silently read as low-risk. NaN must resolve to 'unknown' instead.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> None


def _has_flag(profile: Mapping[str, Any], flag: str) -> bool:
    """True iff `flag` is present in the profile's contraindication list.

    Positive-only by design: a missing or unreadable list means "not recorded", never
    "absent", so this can gate a scope decision without inventing an absence.
    """
    flags = profile.get("contraindications")
    try:
        return flag in flags
    except TypeError:
        return False


def contribute(profile: Mapping[str, Any], builder: DecisionBuilder) -> None:
    """HC-42 contribution: mutate `builder` with the AHA/ACC 2025 decision (returns None)."""
    # 0. Scope gate (HC-96). The encoded module covers adult primary hypertension in the
    # non-pregnant adult; hypertensive disorders of pregnancy are a different framework and
    # ACEi/ARB are fetotoxic. This precedes staging deliberately: a BP-driven answer for a
    # pregnant patient is a guess dressed as a guideline label, and at Stage 2 it would be
    # INITIATE. Scope does not depend on BP, so a normotensive pregnant patient abstains too.
    if _has_flag(profile, "pregnancy"):
        c = cite("HTN-CONCORD:abstain-out-of-scope")
        builder.decision = Decision.ABSTAIN
        builder.abstain_reason = "pregnancy_management_out_of_scope"
        builder.add(c, TraceStep("scope", "Pregnancy: outside the encoded module's scope "
                                          "(adult primary HTN, non-pregnant); abstain.", c.anchor))
        return

    staging = stage_bp(profile)
    builder.add(staging.citation, staging.trace)

    # 1. Cannot stage (acute context or missing BP) -> abstain.
    if staging.stage is None:
        builder.decision = Decision.ABSTAIN
        builder.abstain_reason = staging.abstain_reason
        return
    stage = staging.stage
    builder.bp_stage = stage

    # 2. Medication status must be known to choose initiate vs intensify.
    on_meds = _tri(profile.get("on_bp_meds"))
    if on_meds is None:
        c = cite("HTN-CONCORD:abstain-insufficient-data")
        builder.add(c, TraceStep("initiation", "Medication status unknown; cannot decide initiate vs intensify.", c.anchor))
        builder.decision = Decision.ABSTAIN
        builder.abstain_reason = "med_status_unknown"
        return

    # 3. Already treated: goal is <130/80 -> intensify if above goal, else continue.
    if on_meds is True:
        c = cite("AHA-ACC-2025:bp-goal-130-80")
        if stage in ("stage1", "stage2"):
            builder.add(c, TraceStep("intensification", f"On BP meds, {stage} (above goal <130/80) -> intensify.", c.anchor))
            builder.decision = Decision.INTENSIFY_PHARMACOTHERAPY
            return
        builder.add(c, TraceStep("intensification", f"On BP meds, {stage} (at goal <130/80) -> continue current therapy.", c.anchor))
        builder.decision = Decision.AT_GOAL_CONTINUE
        return

    # 4. Untreated: stage drives initiation.
    if stage == "stage2":
        c = cite("AHA-ACC-2025:stage2-initiate")
        builder.add(c, TraceStep("initiation", "Untreated Stage 2 -> initiate pharmacotherapy.", c.anchor))
        builder.decision = Decision.INITIATE_PHARMACOTHERAPY
        builder.triggers.append("stage2")
        return

    if stage in ("normal", "elevated"):
        anchor = "AHA-ACC-2025:normal-lifestyle" if stage == "normal" else "AHA-ACC-2025:elevated-lifestyle"
        c = cite(anchor)
        builder.add(c, TraceStep("initiation", f"Untreated {stage} -> lifestyle only.", c.anchor))
        builder.decision = Decision.LIFESTYLE_ONLY
        return

    # stage == "stage1": high-risk determination (three-valued).
    _stage1_contribute(profile, stage, builder)


def _stage1_contribute(profile: Mapping[str, Any], stage: str, builder: DecisionBuilder) -> None:
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
        builder.add(c, TraceStep("initiation", f"Untreated Stage 1, high-risk ({', '.join(fired)}) -> initiate.", c.anchor))
        builder.decision = Decision.INITIATE_PHARMACOTHERAPY
        builder.triggers.extend(fired)
        return

    # None fired. Every risk determinant known-False -> low risk -> lifestyle.
    if all(v is False for v in determinants.values()):
        c = cite("AHA-ACC-2025:stage1-lowrisk-lifestyle")
        builder.add(c, TraceStep("initiation", "Untreated Stage 1, no high-risk features -> lifestyle only.", c.anchor))
        builder.decision = Decision.LIFESTYLE_ONLY
        return

    # Otherwise a needed determinant is unknown -> abstain rather than guess low-risk.
    c = cite("HTN-CONCORD:abstain-insufficient-data")
    builder.add(c, TraceStep("initiation", "Untreated Stage 1, high-risk status indeterminate (missing determinant) -> abstain.", c.anchor))
    builder.decision = Decision.ABSTAIN
    builder.abstain_reason = "stage1_risk_indeterminate"


def recommend(profile: Mapping[str, Any]) -> EngineDecision:
    """Public single-guideline entry: build the AHA/ACC 2025 decision for one profile."""
    builder = DecisionBuilder(guideline="aha_acc_2025")
    contribute(profile, builder)
    return builder.build()
