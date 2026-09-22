"""HC-15 + HC-27 -- itemid-filtered lab loading, strictly bound before admittime.

Synthetic ids only (9xxxxxxx, HC-56). The chunked reader is exercised against a
small buffer with a chunk size of 2, so the chunk boundary is actually crossed.
"""
import io

import pandas as pd
import pytest

from pipelines.mimic import labs

# itemids: 50912 creatinine, 50971 potassium, 51070 uacr, 50931 glucose (unwanted)
_LABS = (
    "labevent_id,subject_id,hadm_id,specimen_id,itemid,order_provider_id,charttime,"
    "storetime,value,valuenum,valueuom,ref_range_lower,ref_range_upper,flag,priority,comments\n"
    # 1: two pre-index creatinines -- the LATER one must win
    "1,90000001,,1,50912,,2200-01-01 08:00:00,,1.0,1.0,mg/dL,,,,,\n"
    "2,90000001,,1,50912,,2200-03-01 08:00:00,,1.6,1.6,mg/dL,,,,,\n"
    # 1: a creatinine drawn DURING the index admission -- post-decision, must not bind
    "3,90000001,,1,50912,,2200-06-02 08:00:00,,3.4,3.4,mg/dL,,,,,\n"
    # 1: potassium, deid text value but a usable valuenum
    "4,90000001,,1,50971,,2200-03-01 08:00:00,,___,5.8,mEq/L,,,,,\n"
    # 1: an unwanted itemid must never be loaded
    "5,90000001,,1,50931,,2200-03-01 08:00:00,,99.0,99.0,mg/dL,,,,,\n"
    # 2: a lab outside the 365 d window but inside the 730 d sensitivity window
    "6,90000002,,1,50912,,2199-01-01 08:00:00,,1.1,1.1,mg/dL,,,,,\n"
    # 3: null valuenum -- dropped, never imputed
    "7,90000003,,1,50912,,2200-03-01 08:00:00,,___,,mg/dL,,,,,\n"
    # 4: a same-day-as-admission draw. Day 0 is at/after the decision point.
    "8,90000004,,1,50912,,2200-06-01 00:00:00,,2.2,2.2,mg/dL,,,,,\n"
)

_COHORT = pd.DataFrame({
    "subject_id": [90000001, 90000002, 90000003, 90000004],
    "index_admit": pd.to_datetime(["2200-06-01", "2200-06-01", "2200-06-01", "2200-06-01"]),
})


def _load(**kw):
    return labs.load_labs(io.StringIO(_LABS), _COHORT, chunk_rows=2, **kw)


def test_only_configured_itemids_are_loaded():
    out = _load()
    assert "glucose" not in out.columns


def test_most_recent_pre_index_value_wins():
    out = _load().set_index("subject_id")
    assert out.loc[90000001, "creatinine"] == 1.6


def test_a_value_drawn_during_the_index_admission_cannot_bind():
    """HC-27. The old 'nearest the index encounter' rule was bidirectional and
    would pick 3.4 here -- a post-decision value that plausibly reflects the
    therapy being evaluated. That is the leak this bound exists to close."""
    out = _load().set_index("subject_id")
    assert out.loc[90000001, "creatinine"] != 3.4


def test_a_same_day_draw_does_not_bind():
    """Day 0 is at or after the decision point, not before it."""
    out = _load().set_index("subject_id")
    assert pd.isna(out.loc[90000004, "creatinine"])


def test_a_value_older_than_the_lookback_window_does_not_bind():
    """A two-year-old potassium must not set a contraindication."""
    out = _load().set_index("subject_id")
    assert pd.isna(out.loc[90000002, "creatinine"])


def test_the_sensitivity_window_admits_the_older_value():
    out = labs.load_labs(io.StringIO(_LABS), _COHORT, chunk_rows=2,
                         lookback_days=730).set_index("subject_id")
    assert out.loc[90000002, "creatinine"] == 1.1


def test_null_valuenum_is_dropped_never_carried_forward():
    out = _load().set_index("subject_id")
    assert pd.isna(out.loc[90000003, "creatinine"])


def test_valuenum_is_used_not_the_deid_text_column():
    """`value` may hold the deid token; `valuenum` is the only usable column."""
    out = _load().set_index("subject_id")
    assert out.loc[90000001, "potassium"] == 5.8


def test_missing_lab_is_null_so_the_engine_abstains():
    out = _load()
    assert out["uacr"].isna().all()


def test_output_has_one_row_per_cohort_subject():
    out = _load()
    assert len(out) == len(_COHORT)
    assert set(out["subject_id"]) == set(_COHORT["subject_id"])


def test_chunking_does_not_change_the_result():
    """The chunk loop is an optimisation for a 2.4 GB table; if the boundary
    changed the answer it would be a silent data bug."""
    a = labs.load_labs(io.StringIO(_LABS), _COHORT, chunk_rows=1)
    b = labs.load_labs(io.StringIO(_LABS), _COHORT, chunk_rows=10_000)
    pd.testing.assert_frame_equal(a, b)


def test_unexpected_units_raise_rather_than_silently_converting():
    bad = _LABS.replace("1.6,mg/dL", "1.6,umol/L")
    with pytest.raises(ValueError, match="unit"):
        labs.load_labs(io.StringIO(bad), _COHORT, chunk_rows=2)


def test_potassium_accepts_meq_per_litre():
    """MIMIC records K+ as mEq/L, numerically identical to mmol/L for a
    monovalent ion. A unit assertion copied from the NHANES wording would
    reject every MIMIC potassium."""
    out = _load().set_index("subject_id")
    assert out.loc[90000001, "potassium"] == 5.8
