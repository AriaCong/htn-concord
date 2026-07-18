"""HC-14 — MIMIC OMR blood-pressure parser + context flag.

Pure parsing (parse_bp_value, normalize_posture) is unit-tested without any file;
load_omr_bp / summarize are tested on a tiny in-memory CSV so they never touch the
42 MB omr.csv.gz.
"""
import io

import pytest

from pipelines.mimic.omr_bp import (
    load_omr_bp,
    normalize_posture,
    parse_bp_value,
    summarize,
)


# --- parse_bp_value ---------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("120/80", (120, 80)),
    ("110/65", (110, 65)),
    (" 152/90 ", (152, 90)),      # surrounding whitespace
    ("152 / 90", (152, 90)),      # spaces around slash
    ("60/30", (60, 30)),          # lower boundary, sbp>dbp
    ("290/200", (290, 200)),      # upper boundary
])
def test_parse_bp_value_valid(raw, expected):
    assert parse_bp_value(raw) == expected


@pytest.mark.parametrize("raw", [
    "120/",        # missing dbp
    "/80",         # missing sbp
    "abc",         # non-numeric
    "120",         # no slash
    "120/80/90",   # three parts
    "9/60",        # single-digit sbp (implausible / not 2-3 digits)
    None,          # non-string
])
def test_parse_bp_value_malformed(raw):
    assert parse_bp_value(raw) is None


@pytest.mark.parametrize("raw", [
    "300/80",      # sbp > 290
    "50/30",       # sbp < 60
    "120/210",     # dbp > 200
    "120/20",      # dbp < 30
    "80/120",      # reversed: sbp <= dbp
    "130/130",     # sbp not strictly > dbp
])
def test_parse_bp_value_out_of_range(raw):
    assert parse_bp_value(raw) is None


# --- normalize_posture ------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("Blood Pressure", "unspecified"),
    ("Blood Pressure Sitting", "sitting"),
    ("Blood Pressure Standing (1 min)", "standing"),
    ("Blood Pressure Standing (3 mins)", "standing"),
    ("Blood Pressure Standing", "standing"),
    ("Blood Pressure Lying", "lying"),
])
def test_normalize_posture(name, expected):
    assert normalize_posture(name) == expected


# --- load_omr_bp / summarize ------------------------------------------------
_CSV = (
    "subject_id,chartdate,seq_num,result_name,result_value\n"
    "10000032,2180-04-27,1,Blood Pressure,110/65\n"        # ok, unspecified
    "10000032,2180-05-07,1,BMI (kg/m2),18.0\n"             # excluded (not BP)
    "10000032,2180-04-27,1,Weight (Lbs),94\n"              # excluded (not BP)
    "10000099,2180-06-01,1,Blood Pressure,152/90\n"        # ok, unspecified
    "10000099,2180-06-01,1,Blood Pressure Sitting,150/88\n"  # ok, sitting
    "10000099,2180-06-02,1,Blood Pressure,120/\n"          # malformed -> dropped
    "10000099,2180-06-03,1,Blood Pressure,300/80\n"        # out_of_range -> dropped
    "10000099,2180-06-04,1,Blood Pressure Standing (1 min),140/85\n"  # ok, standing
)


def _buf():
    return io.StringIO(_CSV)


def test_load_omr_bp_keeps_only_valid_bp_rows():
    df = load_omr_bp(_buf())
    assert len(df) == 4  # 110/65, 152/90, 150/88, 140/85
    assert set(df.columns) == {"subject_id", "chartdate", "sbp", "dbp", "posture", "bp_context"}


def test_load_omr_bp_excludes_non_bp_rows():
    df = load_omr_bp(_buf())
    # No Weight/BMI leakage: every surviving reading is a plausible BP pair.
    assert (df["sbp"] > df["dbp"]).all()
    assert df["sbp"].between(60, 290).all()


def test_load_omr_bp_tags_office_context_and_posture():
    df = load_omr_bp(_buf())
    assert (df["bp_context"] == "office").all()
    assert sorted(df["posture"]) == ["sitting", "standing", "unspecified", "unspecified"]


def test_load_omr_bp_values_are_ints():
    df = load_omr_bp(_buf())
    row = df[(df["sbp"] == 110)].iloc[0]
    assert int(row["dbp"]) == 65


def test_summarize_counts_outcomes():
    s = summarize(_buf())
    assert s["bp_rows"] == 6          # rows whose result_name starts "Blood Pressure"
    assert s["parsed_ok"] == 4
    assert s["dropped_malformed"] == 1     # "120/"
    assert s["dropped_out_of_range"] == 1  # "300/80"
    assert s["posture_ok"]["unspecified"] == 2
    assert s["posture_ok"]["sitting"] == 1
    assert s["posture_ok"]["standing"] == 1
