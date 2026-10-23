"""HC-16 -- ICD-9/10 crosswalk to per-subject comorbidity flags.

Synthetic ids only (9xxxxxxx range, HC-56). icd_sets holds the code predicates;
this module is the frame-level crosswalk and, above all, the ABSENCE SEMANTICS.
"""
import io

import pandas as pd

from pipelines.mimic import icd

_DX = (
    "subject_id,hadm_id,seq_num,icd_code,icd_version\n"
    # 1: diabetic, coded at a PRIOR admission
    "90000001,20000001,1,E119,10\n"
    "90000001,20000001,2,I10,10\n"
    # 2: has billed rows, but no diabetes code -> a real negative
    "90000002,20000002,1,J189,10\n"
    # 3: diabetes coded at the INDEX admission only
    "90000003,20000003,1,E119,10\n"
    # 4: ICD-9 coding
    "90000004,20000004,1,25000,9\n"
    "90000004,20000004,2,41401,9\n"
)

_COHORT = pd.DataFrame({
    "subject_id": [90000001, 90000002, 90000003, 90000004, 90000005],
    "hadm_id":    [20000009, 20000002, 20000003, 20000004, 20000005],
})
# prior admissions, by subject
_PRIOR = {90000001: {20000001}, 90000002: set(), 90000003: set(), 90000004: {20000004},
          90000005: set()}


def _dx():
    return pd.read_csv(io.StringIO(_DX), dtype={"icd_code": "string", "icd_version": "Int64"})


def test_a_billed_code_reads_as_true():
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms={20000001}, index_hadms=set())
    assert out.set_index("subject_id").loc[90000001, "diabetes"] == True  # noqa: E712


def test_absence_within_a_complete_enumeration_reads_as_false():
    """Subject 2 has billed rows and no diabetes code. Absence inside an existing
    enumeration is a negative, mirroring the NHANES med_classes argument."""
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms=set(), index_hadms={20000002})
    assert out.set_index("subject_id").loc[90000002, "diabetes"] == False  # noqa: E712


def test_no_billed_rows_at_all_reads_as_null_not_false():
    """Subject 5 appears in no diagnosis row. The enumeration does not exist, so
    absence carries no information. Reading it as False would assert a negative
    about a patient nobody coded -- the guess the ABSTAIN contract forbids."""
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms=set(), index_hadms={20000002})
    assert pd.isna(out.set_index("subject_id").loc[90000005, "diabetes"])


def test_index_encounter_codes_are_excluded_under_the_prior_only_reading():
    """Subject 3's only diabetes code is at the index encounter, which is coded
    at discharge. Under the leakage-safe reading it must not resolve."""
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms=set(), index_hadms=set())
    assert pd.isna(out.set_index("subject_id").loc[90000003, "diabetes"])


def test_index_encounter_codes_are_included_under_the_other_reading():
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms=set(), index_hadms={20000003})
    assert out.set_index("subject_id").loc[90000003, "diabetes"] == True  # noqa: E712


def test_icd9_and_icd10_are_both_crosswalked():
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms={20000004}, index_hadms=set())
    row = out.set_index("subject_id").loc[90000004]
    assert row["diabetes"] == True        # noqa: E712  -- 250.00
    assert row["clinical_cvd"] == True    # noqa: E712  -- 414.01


def test_the_hypertension_anchor_never_sets_a_flag():
    """Subject 1 carries I10. It must contribute nothing: the anchor selects the
    encounter, it never generates a label."""
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms={20000001}, index_hadms=set())
    row = out.set_index("subject_id").loc[90000001]
    assert row["clinical_cvd"] == False   # noqa: E712 -- billed, but not by I10


def test_every_flag_column_is_nullable_boolean():
    """Object-dtype columns would let a stray 1 read as True downstream."""
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms={20000001}, index_hadms=set())
    from pipelines.mimic import icd_sets
    for f in icd_sets.FLAGS:
        assert str(out[f].dtype) == "boolean", f


def test_output_has_exactly_one_row_per_cohort_subject():
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms=set(), index_hadms=set())
    assert len(out) == len(_COHORT)
    assert set(out["subject_id"]) == set(_COHORT["subject_id"])


def test_contraindications_are_assembled_from_the_flags():
    dx = pd.read_csv(io.StringIO(
        "subject_id,hadm_id,seq_num,icd_code,icd_version\n"
        "90000001,20000001,1,T783XXA,10\n"
        "90000001,20000001,2,O139,10\n"
    ), dtype={"icd_code": "string", "icd_version": "Int64"})
    cohort = pd.DataFrame({"subject_id": [90000001], "hadm_id": [20000001]})
    out = icd.crosswalk(dx, cohort, prior_hadms={20000001}, index_hadms=set())
    assert icd.contraindications_from_flags(out).iloc[0] == ["angioedema_hx", "pregnancy"]


def test_contraindication_list_is_empty_not_null_when_flags_are_known_negative():
    out = icd.crosswalk(_dx(), _COHORT, prior_hadms=set(), index_hadms={20000002})
    got = icd.contraindications_from_flags(out)
    assert got.iloc[1] == []          # subject 2: enumerated, no flags
