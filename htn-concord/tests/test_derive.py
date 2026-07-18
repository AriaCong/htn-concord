"""Unit tests for shared clinical derivations. A branch without a test does not ship."""
import numpy as np
import pandas as pd
import pytest

from pipelines.nhanes import derive


def test_egfr_ckdepi_2021_known_values():
    # Published CKD-EPI 2021 race-free anchors (Inker 2021).
    scr = pd.Series([0.9, 1.5, 1.0])
    age = pd.Series([50, 68, 60])
    sex = pd.Series(["male", "female", "male"])
    egfr = derive.egfr_ckdepi_2021(scr, age, sex)
    assert egfr.iloc[0] == pytest.approx(104.0, abs=1.0)
    assert egfr.iloc[1] == pytest.approx(37.7, abs=1.0)
    assert egfr.iloc[2] == pytest.approx(86.2, abs=1.5)


def test_egfr_nan_propagates():
    out = derive.egfr_ckdepi_2021(pd.Series([np.nan]), pd.Series([60]), pd.Series(["male"]))
    assert pd.isna(out.iloc[0])


@pytest.mark.parametrize("sbp,dbp,expected", [
    (118, 78, "normal"),
    (119, 79, "normal"),
    (120, 79, "elevated"),
    (129, 79, "elevated"),
    (130, 79, "stage1"),     # isolated systolic boundary
    (118, 82, "stage1"),     # isolated diastolic
    (139, 89, "stage1"),
    (140, 85, "stage2"),     # systolic drives
    (135, 90, "stage2"),     # diastolic drives
    (160, 100, "stage2"),
])
def test_bp_stage_boundaries(sbp, dbp, expected):
    out = derive.bp_stage(pd.Series([sbp]), pd.Series([dbp]))
    assert out.iloc[0] == expected


def test_bp_stage_na():
    out = derive.bp_stage(pd.Series([np.nan]), pd.Series([np.nan]))
    assert pd.isna(out.iloc[0])


def test_resolve_diabetes_kleene():
    # self=True -> True regardless; self=NA & hba1c high -> True; both unknown -> NA
    df = pd.DataFrame({
        "diabetes_self": pd.array([True, False, pd.NA, False], dtype="boolean"),
        "hba1c": [5.0, 7.0, 5.5, np.nan],
    })
    out = derive.resolve_diabetes(df)
    assert out.iloc[0] == True                                  # self yes
    assert out.iloc[1] == True                                  # hba1c 7.0 >= 6.5
    assert pd.isna(out.iloc[2])                                 # self NA | lab False -> NA (abstain)
    assert pd.isna(out.iloc[3])                                 # self False | lab NA -> NA


def test_prevent_computes_and_gates_by_age():
    df = pd.DataFrame({
        "age": [50, 25], "sex": ["female", "female"],
        "total_chol": [200, 200], "hdl": [45, 45], "sbp": [160, 160],
        "diabetes": [True, True], "current_smoker": [False, False],
        "egfr": [90, 90], "on_bp_meds": [True, True], "statin_use": [False, False],
    })
    out = derive.prevent_10yr(df)
    assert out.iloc[0] == pytest.approx(14.683939, abs=1e-4)   # eligible -> Table S12A value
    assert pd.isna(out.iloc[1])                                 # age 25 < 30 -> NaN (abstain)


# --- Regression tests for the 2026-07-18 correctness fixes -------------------

@pytest.mark.parametrize("sbp,dbp,expected", [
    (139.5, 79.0, "stage1"),    # non-integer SBP inside the old between(130,139) gap
    (129.5, 79.0, "elevated"),  # non-integer SBP inside the old between(120,129) gap
    (119.5, 79.5, "normal"),
    (120.0, 89.5, "stage1"),    # non-integer DBP in the old between(80,89) gap
    (135.0, 89.5, "stage1"),
    (139.5, 89.5, "stage1"),
])
def test_bp_stage_handles_non_integer_means(sbp, dbp, expected):
    """Means of 3 oscillometric readings are routinely non-integer.

    The old vectorized `between()` bounds voided these to NA while the engine's
    scalar rule staged them correctly, so the profile column silently disagreed
    with the engine on 56 of 4,806 real rows.
    """
    out = derive.bp_stage(pd.Series([sbp]), pd.Series([dbp]))
    assert out.iloc[0] == expected


def test_bp_stage_matches_vocab_scalar_on_boundary_grid():
    """derive.bp_stage and vocab.bp_stage_scalar must never diverge."""
    import vocab
    vals = [119, 119.5, 120, 129.5, 130, 139.5, 140, 79, 79.5, 80, 89.5, 90, 91]
    sbps = [v for v in vals for _ in vals]
    dbps = [v for _ in vals for v in vals]
    got = derive.bp_stage(pd.Series(sbps), pd.Series(dbps))
    want = [vocab.bp_stage_scalar(s, d) for s, d in zip(sbps, dbps)]
    assert list(got) == want


def test_bp_stage_na_only_when_bp_actually_missing():
    out = derive.bp_stage(pd.Series([np.nan, 130.0]), pd.Series([80.0, np.nan]))
    assert pd.isna(out.iloc[0])
    assert pd.isna(out.iloc[1])


def test_ckd_albuminuria_preserves_unknown():
    """Missing kidney labs must stay NA so the engine can ABSTAIN, never False."""
    egfr = pd.Series([50.0, 90.0, np.nan, np.nan, 90.0])
    uacr = pd.Series([10.0, 40.0, 10.0, np.nan, np.nan])
    out = derive.ckd_albuminuria(egfr, uacr)
    assert out.iloc[0] == True      # low eGFR -> True regardless of UACR
    assert out.iloc[1] == True      # high UACR -> True regardless of eGFR
    assert pd.isna(out.iloc[2])     # eGFR unknown, UACR negative -> unknown
    assert pd.isna(out.iloc[3])     # both unknown -> unknown
    assert pd.isna(out.iloc[4])     # eGFR negative, UACR unknown -> unknown


def test_ckd_albuminuria_false_only_when_both_labs_negative():
    out = derive.ckd_albuminuria(pd.Series([90.0]), pd.Series([10.0]))
    assert out.iloc[0] == False
