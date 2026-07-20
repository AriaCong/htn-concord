"""HC-96 — pregnancy is out of the encoded guideline's scope, so the engine abstains.

The 2025 AHA/ACC module encoded here covers adult *primary* hypertension in the
non-pregnant adult. Hypertensive disorders of pregnancy are a different clinical
framework, and ACEi/ARB are fetotoxic. Before HC-96 the pregnancy determinant was
never read, so a pregnant Stage-2 profile produced INITIATE **as ground truth** —
a label that HC-36 (drug-class selection) would then dress in an ACEi/ARB name.

Abstaining rather than guessing is Master Plan principle 1. These tests pin that
the pregnancy branch fires *before* any staging-driven decision can be reached.
"""
from engine.rules.aha_acc_2025.initiation_intensification import recommend
from engine.types import Decision


def _p(**over):
    base = {"sbp": 135, "dbp": 85, "bp_context": "chronic", "on_bp_meds": False,
            "contraindications": []}
    base.update(over)
    return base


def test_pregnant_stage2_untreated_never_initiates():
    """The exact hazard: untreated Stage 2 + pregnancy must not yield INITIATE."""
    d = recommend(_p(sbp=165, dbp=105, contraindications=["pregnancy"]))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "pregnancy_management_out_of_scope"


def test_pregnant_treated_above_goal_never_intensifies():
    """The mirror hazard on the treated arm."""
    d = recommend(_p(sbp=165, dbp=105, on_bp_meds=True,
                     contraindications=["pregnancy"]))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "pregnancy_management_out_of_scope"


def test_pregnant_normotensive_also_abstains():
    """Scope is decided by pregnancy, not by BP.

    A normotensive pregnant patient previously scored LIFESTYLE_ONLY, which reads as
    a guideline-derived statement the encoded module never makes. Out of scope is out
    of scope at every stage, otherwise the corpus's safety depends on its BP
    distribution -- the exact fragility HC-96 exists to remove.
    """
    d = recommend(_p(sbp=105, dbp=65, contraindications=["pregnancy"]))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "pregnancy_management_out_of_scope"


def test_pregnancy_branch_precedes_the_unknown_med_status_abstention():
    """Both branches abstain, but the reason must name pregnancy.

    An abstention tagged `med_status_unknown` would route this case to "collect more
    data", when in fact no amount of data makes the encoded module applicable.
    """
    d = recommend(_p(sbp=165, dbp=105, on_bp_meds=None,
                     contraindications=["pregnancy"]))
    assert d.decision is Decision.ABSTAIN
    assert d.abstain_reason == "pregnancy_management_out_of_scope"


def test_pregnancy_decision_is_cited_and_traced():
    """Every decision carries a registered anchor and a trace step (engine contract)."""
    d = recommend(_p(sbp=165, dbp=105, contraindications=["pregnancy"]))
    assert d.citations, "abstention must still carry a citation"
    assert any("pregnan" in step.detail.lower() for step in d.trace)


def test_other_contraindications_do_not_trigger_the_scope_abstention():
    """Hyperkalemia constrains *which drug*, not whether the module applies.

    Guards against the over-broad fix of abstaining on any contraindication, which
    would silently drop every hyperkalemic patient out of the concordance corpus.
    """
    d = recommend(_p(sbp=165, dbp=105, contraindications=["hyperkalemia"]))
    assert d.decision is Decision.INITIATE_PHARMACOTHERAPY


def test_absent_and_empty_contraindications_are_unaffected():
    d_empty = recommend(_p(sbp=165, dbp=105, contraindications=[]))
    base = _p(sbp=165, dbp=105)
    base.pop("contraindications")
    d_missing = recommend(base)
    assert d_empty.decision is Decision.INITIATE_PHARMACOTHERAPY
    assert d_missing.decision is Decision.INITIATE_PHARMACOTHERAPY
