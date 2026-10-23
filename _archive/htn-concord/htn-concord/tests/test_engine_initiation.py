"""HC-33 initiation/intensification — definite (non-Stage-1) branches + input readers."""
from engine.rules.aha_acc_2025.initiation_intensification import _num, _tri, recommend
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
    assert _tri(1) is None            # a number is not a boolean
    assert _tri(float("nan")) is None


def test_tri_reads_numpy_bool():
    np = __import__("numpy")
    assert _tri(np.bool_(True)) is True
    assert _tri(np.bool_(False)) is False


def test_num_rejects_nan_and_bool():
    assert _num(5.0) == 5.0
    assert _num(0) == 0.0
    assert _num(None) is None
    assert _num(float("nan")) is None   # missing PREVENT must not read as a value
    assert _num(True) is None           # a bool is not a risk score
    assert _num("x") is None


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
