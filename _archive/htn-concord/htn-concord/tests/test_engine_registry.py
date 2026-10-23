"""HC-43 — evaluate() dispatches through a guideline registry.

Principle 6: guidelines are separate modules whose disagreement is *reported*, never
merged. That needs (a) every decision tagged with the guideline that produced it and
(b) a dispatch seam so a second guideline (ESC 2024, HC-41) plugs in without editing the
first. These tests pin both, and that a new guideline registers without touching AHA code.
"""
import pytest

from engine.evaluate import evaluate, register
from engine.types import Decision


def _chronic(**over):
    base = {"sbp": 118, "dbp": 76, "bp_context": "chronic", "on_bp_meds": False}
    base.update(over)
    return base


def test_evaluate_defaults_to_aha_and_tags_the_decision():
    d = evaluate(_chronic())
    assert d.decision is Decision.LIFESTYLE_ONLY
    assert d.guideline == "aha_acc_2025"


def test_evaluate_unknown_guideline_raises():
    with pytest.raises(KeyError):
        evaluate(_chronic(), guideline="no_such_guideline")


def test_a_new_guideline_registers_without_editing_existing_rules():
    """The acceptance criterion: adding a rule/guideline needs no edit to existing modules."""
    def toy_guideline(profile, builder):
        from engine.citations import cite
        from engine.types import TraceStep
        c = cite("HTN-CONCORD:abstain-insufficient-data")
        builder.decision = Decision.ABSTAIN
        builder.abstain_reason = "toy"
        builder.add(c, TraceStep("toy", "toy guideline", c.anchor))

    register("toy_guideline_hc43", toy_guideline)
    d = evaluate(_chronic(), guideline="toy_guideline_hc43")
    assert d.guideline == "toy_guideline_hc43"
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "toy"
    assert d.citations and d.trace
