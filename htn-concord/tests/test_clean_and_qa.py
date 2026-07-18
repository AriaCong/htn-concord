"""Tests for missing-value preservation (abstention principle) and range gating."""
import numpy as np
import pandas as pd

from pipelines.nhanes import clean, qa


def test_diabetes_sentinel_preserved_as_na():
    # DIQ010: 1=yes, 2=no, 3=borderline, 7=refused, 9=don't know
    df = pd.DataFrame({"SEQN": [1, 2, 3, 4], "DIQ010": [1.0, 2.0, 9.0, np.nan]})
    out = clean.clean_diq(df)
    assert out["diabetes_self"].iloc[0] == True
    assert out["diabetes_self"].iloc[1] == False
    assert pd.isna(out["diabetes_self"].iloc[2])   # don't-know -> NA, not False
    assert pd.isna(out["diabetes_self"].iloc[3])   # missing -> NA


def test_smoking_skip_pattern():
    # never smoked (SMQ020==2) -> non-smoker even though SMQ040 not asked (NA)
    df = pd.DataFrame({
        "SEQN": [1, 2, 3, 4],
        "SMQ020": [1.0, 1.0, 2.0, 7.0],
        "SMQ040": [1.0, 3.0, np.nan, np.nan],
    })
    out = clean.clean_smq(df).set_index("SEQN")["current_smoker"]
    assert out.loc[1] == True     # smokes every day
    assert out.loc[2] == False    # former
    assert out.loc[3] == False    # never smoked
    assert pd.isna(out.loc[4])    # refused -> NA


def test_on_bp_meds_skip_pattern():
    # never told high BP (BPQ020==2) -> not on meds; currently taking -> True
    df = pd.DataFrame({
        "SEQN": [1, 2, 3],
        "BPQ020": [1.0, 2.0, 1.0],
        "BPQ040A": [1.0, np.nan, 1.0],
        "BPQ050A": [1.0, np.nan, 2.0],
    })
    out = clean.clean_bpq(df).set_index("SEQN")["on_bp_meds"]
    assert out.loc[1] == True
    assert out.loc[2] == False    # never told -> not on meds (not NA)
    assert out.loc[3] == False    # advised but not taking


def test_apply_ranges_nulls_and_logs():
    df = pd.DataFrame({"sbp": [120, 999], "potassium": [4.0, 20.0]})
    gated, log = qa.apply_ranges(df)
    assert pd.isna(gated["sbp"].iloc[1])
    assert pd.isna(gated["potassium"].iloc[1])
    assert {v["column"] for v in log} == {"sbp", "potassium"}
