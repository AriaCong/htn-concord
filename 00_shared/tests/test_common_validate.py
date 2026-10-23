"""The canonical-contract gate is shared, so every source validates identically.

This is the invariant the whole architecture rests on: downstream code never
branches on data source because every source emits rows valid against one
schema. A MIMIC row is used here precisely because NHANES already exercises the
module -- the point is that the gate is not NHANES-shaped.
"""
import pandas as pd
import pytest

from pipelines.common import validate


def _valid_row() -> dict:
    return {
        "source": "mimic_iv", "age": 61.0, "sex": "male",
        "sbp": 142.0, "dbp": 88.0, "bp_stage": "stage2", "bp_context": "office",
        "med_classes": ["thiazide"], "contraindications": [],
    }


def test_accepts_a_valid_non_nhanes_row():
    df = pd.DataFrame([_valid_row()])
    assert validate.validate_profiles(df) == 1


def test_rejects_an_unknown_bp_stage():
    row = _valid_row() | {"bp_stage": "stage_1"}
    with pytest.raises(ValueError, match="violates schema"):
        validate.validate_profiles(pd.DataFrame([row]))


def test_rejects_an_unknown_source():
    row = _valid_row() | {"source": "not_a_source"}
    with pytest.raises(ValueError, match="violates schema"):
        validate.validate_profiles(pd.DataFrame([row]))


def test_rejects_an_unknown_med_class():
    """med_classes is a closed vocabulary shared with the engine; a source that
    invents a class would have the engine silently ignore it."""
    row = _valid_row() | {"med_classes": ["ace_inhibitor"]}
    with pytest.raises(ValueError, match="violates schema"):
        validate.validate_profiles(pd.DataFrame([row]))


def test_null_is_allowed_wherever_a_value_is_genuinely_unknown():
    """Abstention depends on null surviving the gate: coercing it to a definite
    value is what the schema exists to prevent."""
    row = _valid_row() | {"age": None, "sex": None, "bp_stage": None}
    assert validate.validate_profiles(pd.DataFrame([row])) == 1


def test_rejects_an_admission_context_typo():
    """bp_context drives whether the engine stages or abstains, so an
    unrecognised value must fail loudly rather than read as chronic."""
    row = _valid_row() | {"bp_context": "inpatient"}
    with pytest.raises(ValueError, match="violates schema"):
        validate.validate_profiles(pd.DataFrame([row]))
