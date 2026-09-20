"""HC-18 -- cohort selection. Synthetic ids only (9xxxxxxx, HC-56)."""
import io

import pandas as pd

from pipelines.mimic import cohort

_DX = (
    "subject_id,hadm_id,seq_num,icd_code,icd_version\n"
    "90000001,20000001,1,I10,10\n"        # anchor
    "90000001,20000002,1,I10,10\n"        # later anchor admission
    "90000002,20000003,1,4019,9\n"        # ICD-9 anchor
    "90000003,20000004,1,I150,10\n"       # SECONDARY HTN -- excluded
    "90000004,20000005,1,J189,10\n"       # not hypertensive at all
    "90000005,20000006,1,I110,10\n"       # anchor, but no OMR
)

_ADM = (
    "subject_id,hadm_id,admittime,dischtime\n"
    "90000001,20000001,2200-06-01 10:00:00,2200-06-05 10:00:00\n"
    "90000001,20000002,2201-06-01 10:00:00,2201-06-05 10:00:00\n"
    "90000002,20000003,2200-06-01 10:00:00,2200-06-05 10:00:00\n"
    "90000003,20000004,2200-06-01 10:00:00,2200-06-05 10:00:00\n"
    "90000004,20000005,2200-06-01 10:00:00,2200-06-05 10:00:00\n"
    "90000005,20000006,2200-06-01 10:00:00,2200-06-05 10:00:00\n"
)

# same admittime, two hadm_ids -- the tie-break must be deterministic
_ADM_TIE = (
    "subject_id,hadm_id,admittime,dischtime\n"
    "90000001,20000077,2200-06-01 10:00:00,2200-06-05 10:00:00\n"
    "90000001,20000001,2200-06-01 10:00:00,2200-06-05 10:00:00\n"
)
_DX_TIE = (
    "subject_id,hadm_id,seq_num,icd_code,icd_version\n"
    "90000001,20000077,1,I10,10\n"
    "90000001,20000001,1,I10,10\n"
)

_OMR = (
    "subject_id,chartdate,seq_num,result_name,result_value\n"
    # subject 1: two distinct dates inside the window, one same-day, one too old
    "90000001,2200-01-10,1,Blood Pressure,150/92\n"
    "90000001,2200-03-10,1,Blood Pressure,146/88\n"
    "90000001,2200-06-01,1,Blood Pressure,210/120\n"   # same day -- excluded
    "90000001,2198-01-10,1,Blood Pressure,120/70\n"    # outside window
    # subject 2: only ONE distinct date inside the window
    "90000002,2200-03-10,1,Blood Pressure,138/86\n"
    "90000002,2200-03-10,1,Blood Pressure Sitting,140/88\n"
)

_EDSTAYS = (
    "subject_id,hadm_id,stay_id,intime,outtime,gender,race,arrival_transport,disposition\n"
    "90000001,20000001,30000001,2200-06-01 08:00:00,2200-06-01 10:00:00,F,W,AMBULANCE,ADMITTED\n"
    "90000002,20000003,30000002,2200-06-01 08:00:00,2200-06-01 10:00:00,M,W,WALK IN,ADMITTED\n"
    "90000005,20000006,30000005,2200-06-01 08:00:00,2200-06-01 10:00:00,M,W,WALK IN,ADMITTED\n"
)

_MEDRECON = (
    "subject_id,stay_id,charttime,name,gsn,ndc,etc_rn,etccode,etcdescription\n"
    "90000001,30000001,2200-06-01 08:30:00,Lisinopril,1,1,1,1,ACE Inhibitors\n"
    "90000005,30000005,2200-06-01 08:30:00,Lisinopril,1,1,1,1,ACE Inhibitors\n"
)


def _b(s):
    return io.StringIO(s)


def test_anchor_excludes_secondary_hypertension():
    """ICD-9 405 / ICD-10 I15 are out of scope for a primary-HTN benchmark."""
    out = cohort.anchor_subject_hadms(_b(_DX))
    assert 90000003 not in set(out["subject_id"])


def test_anchor_includes_icd9_and_icd10():
    out = cohort.anchor_subject_hadms(_b(_DX))
    assert {90000001, 90000002, 90000005} <= set(out["subject_id"])


def test_non_hypertensive_patients_are_not_anchors():
    out = cohort.anchor_subject_hadms(_b(_DX))
    assert 90000004 not in set(out["subject_id"])


def test_index_encounter_is_the_earliest_anchor_admission():
    out = cohort.earliest_anchor_admit(_b(_DX), _b(_ADM)).set_index("subject_id")
    assert out.loc[90000001, "hadm_id"] == 20000001
    assert out.loc[90000001, "index_admit"] == pd.Timestamp("2200-06-01 10:00:00")


def test_one_row_per_subject():
    out = cohort.earliest_anchor_admit(_b(_DX), _b(_ADM))
    assert out["subject_id"].is_unique


def test_admittime_ties_break_deterministically_on_the_smallest_hadm_id():
    """Without this the index encounter depends on row order, so the cohort is
    not reproducible across runs."""
    a = cohort.earliest_anchor_admit(_b(_DX_TIE), _b(_ADM_TIE))
    assert a.iloc[0]["hadm_id"] == 20000001


def test_medrecon_linkage_is_required_not_merely_an_ed_stay():
    """Subject 2 has an ED stay but no reconciliation, so it cannot establish
    on_bp_meds and cannot be in the decision cohort."""
    ed_linked = cohort.ed_linked_hadms(_b(_EDSTAYS))
    with_rec = cohort.hadms_with_medrecon(_b(_EDSTAYS), _b(_MEDRECON))
    assert 20000003 in ed_linked
    assert 20000003 not in with_rec


def test_qualifying_omr_requires_two_distinct_dates():
    """Subject 2 has two readings on ONE date. Distinct dates, not rows: three
    readings at one visit are one occasion."""
    idx = cohort.earliest_anchor_admit(_b(_DX), _b(_ADM))
    keep, _ = cohort.qualifying_omr(idx, _b(_OMR))
    assert set(keep["subject_id"]) == {90000001}


def test_a_same_day_reading_cannot_qualify():
    """Subject 1's 210/120 on the admission date is at or after the decision
    point. If it bound, an acute crisis reading would set chronic stage."""
    idx = cohort.earliest_anchor_admit(_b(_DX), _b(_ADM))
    _, readings = cohort.qualifying_omr(idx, _b(_OMR))
    assert 210 not in set(readings["sbp"])


def test_a_reading_outside_the_window_cannot_qualify():
    idx = cohort.earliest_anchor_admit(_b(_DX), _b(_ADM))
    _, readings = cohort.qualifying_omr(idx, _b(_OMR))
    assert 120 not in set(readings["sbp"])


def test_bp_is_summarised_by_the_mean():
    """HC-23, resolved against the guideline source: the 2025 AHA/ACC text
    specifies the average of >=2 readings and never a median. NHANES computes
    the mean too, so the two arms agree."""
    idx = cohort.earliest_anchor_admit(_b(_DX), _b(_ADM))
    _, readings = cohort.qualifying_omr(idx, _b(_OMR))
    bp = cohort.summarize_bp(readings).set_index("subject_id")
    assert bp.loc[90000001, "sbp"] == (150 + 146) / 2
    assert bp.loc[90000001, "dbp"] == (92 + 88) / 2


def test_bp_n_readings_counts_distinct_dates_not_rows():
    idx = cohort.earliest_anchor_admit(_b(_DX), _b(_ADM))
    _, readings = cohort.qualifying_omr(idx, _b(_OMR))
    bp = cohort.summarize_bp(readings).set_index("subject_id")
    assert bp.loc[90000001, "bp_n_readings"] == 2


def test_primary_cohort_applies_every_rule_together():
    keep, _ = cohort.primary_cohort(
        _b(_DX), _b(_ADM), _b(_EDSTAYS), _b(_MEDRECON), _b(_OMR)
    )
    # 1 qualifies. 2 has a medrecon-less stay AND one BP date. 5 has a medrecon
    # but no OMR. 3 is secondary HTN, 4 is not hypertensive.
    assert set(keep["subject_id"]) == {90000001}
