"""Tests for missing-value preservation (abstention principle) and range gating."""
import json

import numpy as np
import pandas as pd

from pipelines.common import qa
from pipelines.nhanes import clean, config


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
    gated, log = qa.apply_ranges(df, config.RANGES)
    assert pd.isna(gated["sbp"].iloc[1])
    assert pd.isna(gated["potassium"].iloc[1])
    assert {v["column"] for v in log} == {"sbp", "potassium"}


def test_apply_ranges_takes_an_explicit_range_map():
    """Ranges are a parameter, not a NHANES import, so MIMIC can supply its own."""
    df = pd.DataFrame({"sbp": [120.0, 350.0, 90.0]})
    ranges = {"sbp": qa.Range(60, 290)}
    out, log = qa.apply_ranges(df, ranges)

    assert pd.isna(out.loc[1, "sbp"]), "350 mmHg is out of range and must be nulled"
    assert out.loc[0, "sbp"] == 120.0
    assert log == [{"column": "sbp", "lo": 60, "hi": 290, "n_nulled": 1}]


def test_apply_ranges_rejects_to_na_rather_than_clipping():
    """A clipped 350 becomes a plausible 290 and then a confident Stage-2 label
    from data known to be corrupt. The gate must reject, never clip."""
    df = pd.DataFrame({"sbp": [350.0]})
    out, _ = qa.apply_ranges(df, {"sbp": qa.Range(60, 290)})
    assert pd.isna(out.loc[0, "sbp"])


def test_write_report_takes_an_explicit_out_path(tmp_path):
    """The report path is a parameter so each source writes its own QA file."""
    df = pd.DataFrame({"bp_stage": ["stage1", "normal"], "sbp": [134.0, 110.0]})
    out = tmp_path / "some_qa.json"
    written = qa.write_report(df, [], {"DEMO": 2}, out)

    assert written == out
    payload = json.loads(out.read_text())
    assert payload["n_profiles"] == 2
    assert payload["bp_stage_distribution"] == {"stage1": 1, "normal": 1}
    assert payload["source_row_counts"] == {"DEMO": 2}


def test_write_report_merges_source_specific_extras(tmp_path):
    """`extra` carries per-source fields (NHANES cycle, MIMIC cohort rule) without
    the shared writer having to know about any of them."""
    out = tmp_path / "qa.json"
    qa.write_report(pd.DataFrame({"sbp": [120.0]}), [], {}, out, extra={"cycle": "J"})
    assert json.loads(out.read_text())["cycle"] == "J"
