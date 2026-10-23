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
