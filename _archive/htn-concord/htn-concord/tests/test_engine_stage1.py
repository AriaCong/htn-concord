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
