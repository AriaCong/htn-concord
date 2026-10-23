"""HC-42 — DecisionBuilder: the mutable composition seam frozen once into an EngineDecision.

Rules mutate a builder as (profile, builder) -> None contributions instead of each
constructing a whole frozen EngineDecision; build() freezes it. These tests pin the
builder contract and that independent contributions accumulate into one decision.
"""
import dataclasses

import pytest

from engine.builder import DecisionBuilder
from engine.types import Citation, Decision, EngineDecision, TraceStep


def test_builder_accumulates_and_freezes_into_engine_decision():
    b = DecisionBuilder(guideline="aha_acc_2025")
    b.bp_stage = "stage2"
    b.decision = Decision.INITIATE_PHARMACOTHERAPY
    b.triggers.append("stage2")
    b.citations.append(Citation("AHA-ACC-2025:stage2-initiate", "text"))
    b.trace.append(TraceStep("initiation", "Untreated Stage 2 -> initiate.", "AHA-ACC-2025:stage2-initiate"))

    d = b.build()

    assert isinstance(d, EngineDecision)
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert d.bp_stage == "stage2"
    assert d.triggers == ("stage2",)          # list frozen to tuple
    assert d.abstain_reason is None
    assert d.citations == (Citation("AHA-ACC-2025:stage2-initiate", "text"),)
    assert len(d.trace) == 1
    assert d.guideline == "aha_acc_2025"
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.decision = Decision.LIFESTYLE_ONLY


def test_independent_contributions_accumulate_into_one_builder():
    """Two rules that never reference each other still compose — the whole point of the seam."""
    def rule_a(profile, bld):
        bld.citations.append(Citation("AHA-ACC-2025:bp-categories", "a"))
        bld.trace.append(TraceStep("bp_staging", "staged", "AHA-ACC-2025:bp-categories"))
        bld.bp_stage = "stage1"

    def rule_b(profile, bld):
        bld.citations.append(Citation("AHA-ACC-2025:stage1-lowrisk-lifestyle", "b"))
        bld.trace.append(TraceStep("initiation", "low risk", "AHA-ACC-2025:stage1-lowrisk-lifestyle"))
        bld.decision = Decision.LIFESTYLE_ONLY

    b = DecisionBuilder(guideline="aha_acc_2025")
    rule_a({}, b)
    rule_b({}, b)
    d = b.build()

    assert d.decision is Decision.LIFESTYLE_ONLY
    assert d.bp_stage == "stage1"
    assert len(d.citations) == 2 and len(d.trace) == 2


def test_build_before_a_decision_is_set_raises():
    """A contribution that forgets to decide is a bug, not a silent None decision."""
    with pytest.raises(ValueError):
        DecisionBuilder(guideline="aha_acc_2025").build()
