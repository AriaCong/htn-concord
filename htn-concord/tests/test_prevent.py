"""Tests for PREVENT. Numeric-risk assertions validate the base 10-year total-CVD model
against Khan 2024 Suppl. Table S12A (superseded note: these were xfail until HC-31 filled
the Khan 2024 coefficients — they document the published check cases to validate against."""
import math

import pytest

from pipelines.nhanes import prevent


def _inputs(**over):
    base = dict(age=50, sex="female", total_chol_mgdl=200, hdl_mgdl=50, sbp=140,
                on_bp_meds=False, diabetes=False, current_smoker=False, egfr=90, statin=False)
    base.update(over)
    return prevent.PreventInputs(**base)


def test_coefficients_filled():
    assert prevent.COEFFICIENTS_FILLED is True


def test_published_example_table_s12a():
    """Khan 2024 Table S12A worked example must reproduce exactly.
    Age 50, TC 200, HDL 45, SBP 160, diabetes, on antiHTN, eGFR 90, no statin/smoke.
    Published Risk: Women 14.684%, Men 16.317%."""
    common = dict(age=50, total_chol_mgdl=200, hdl_mgdl=45, sbp=160,
                  on_bp_meds=True, diabetes=True, current_smoker=False,
                  egfr=90, statin=False)
    women = prevent.prevent_10yr_cvd_risk(prevent.PreventInputs(sex="female", **common))
    men = prevent.prevent_10yr_cvd_risk(prevent.PreventInputs(sex="male", **common))
    assert women == pytest.approx(14.683939, abs=1e-4)
    assert men == pytest.approx(16.317056, abs=1e-4)


def test_age_gate():
    assert prevent.prevent_10yr_cvd_risk(_inputs(age=25)) is None   # <30
    assert prevent.prevent_10yr_cvd_risk(_inputs(age=85)) is None   # >79


def test_incomplete_inputs_return_none():
    assert prevent.prevent_10yr_cvd_risk(_inputs(sex="unknown")) is None
    assert prevent.prevent_10yr_cvd_risk(_inputs(egfr=float("nan"))) is None


def test_feature_transform_shapes_and_units():
    # Unit conversion + centering are testable now (coefficient-independent).
    f = prevent._features(_inputs(age=55, total_chol_mgdl=193.35, hdl_mgdl=50.27, sbp=110, egfr=90))
    assert f["cage"] == pytest.approx(0.0)                 # age 55 centered
    assert f["sbp_lt110"] == pytest.approx(0.0)            # SBP at 110 knot
    assert f["sbp_ge110"] == pytest.approx((110 - 130) / 20)
    assert f["egfr_ge60"] == pytest.approx((90 - 90) / -15)
    # non-HDL: (193.35-50.27)/38.67 - 3.5 ≈ 3.7 - 3.5 = 0.2
    assert f["non_hdl"] == pytest.approx(0.2, abs=0.05)
    assert set(prevent.FEATURE_ORDER).issubset(f.keys())


def test_indicator_and_interaction_features():
    f = prevent._features(_inputs(diabetes=True, current_smoker=True, on_bp_meds=True, statin=True, sbp=150))
    assert f["diabetes"] == 1.0 and f["smoker"] == 1.0
    assert f["sbp_ge110_x_bpmed"] == pytest.approx(f["sbp_ge110"] * 1.0)
    assert f["non_hdl_x_statin"] == pytest.approx(f["non_hdl"] * 1.0)


def test_risk_in_valid_range():
    risk = prevent.prevent_10yr_cvd_risk(_inputs())
    assert risk is not None and 0.0 <= risk <= 100.0
