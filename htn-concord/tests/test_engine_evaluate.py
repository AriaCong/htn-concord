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
