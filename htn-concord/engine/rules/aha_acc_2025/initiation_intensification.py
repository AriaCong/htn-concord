"""HC-33 — 2025 AHA/ACC initiation / intensification decision as a cited engine rule.

Pure function of a PatientProfile. Composes staging (HC-32), then decides initiate /
intensify / lifestyle / continue / abstain. Missing determinants resolve to ABSTAIN via
three-valued logic (see _tri / _num).
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
