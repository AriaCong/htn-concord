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
