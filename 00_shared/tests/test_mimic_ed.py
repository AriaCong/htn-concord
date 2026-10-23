"""HC-20 -- MIMIC-IV-ED pipeline: edstays spine, medrecon home meds, acute vitals.

Synthetic fixtures only. Subject ids are in the 9xxxxxxx range, disjoint from the
real MIMIC range, per HC-56.
"""
import io

import pandas as pd
import pytest

from pipelines.mimic import ed

_EDSTAYS = (
    "subject_id,hadm_id,stay_id,intime,outtime,gender,race,arrival_transport,disposition\n"
    "90000001,20000001,30000001,2200-01-05 08:00:00,2200-01-05 14:00:00,F,WHITE,AMBULANCE,ADMITTED\n"
    "90000002,20000002,30000002,2200-02-05 09:00:00,2200-02-05 18:00:00,M,BLACK,WALK IN,ADMITTED\n"
    "90000003,,30000003,2200-03-05 09:00:00,2200-03-05 12:00:00,M,ASIAN,WALK IN,HOME\n"
)

_MEDRECON = (
    "subject_id,stay_id,charttime,name,gsn,ndc,etc_rn,etccode,etcdescription\n"
    # on an ACEI + a thiazide, plus a statin
    "90000001,30000001,2200-01-05 08:30:00,Lisinopril,012345,1,1,101,ACE Inhibitors\n"
    "90000001,30000001,2200-01-05 08:30:00,Hydrochlorothiazide,012346,1,1,102,Diuretic - Thiazides and Related\n"
    "90000001,30000001,2200-01-05 08:30:00,Atorvastatin,012347,1,1,103,"
    "Antihyperlipidemic - HMG CoA Reductase Inhibitors (statins)\n"
    # exact duplicate row -- must not count twice
    "90000001,30000001,2200-01-05 08:31:00,Lisinopril,012345,1,1,101,ACE Inhibitors\n"
    # reconciliation exists but contains no antihypertensive
    "90000002,30000002,2200-02-05 09:30:00,Metformin,022222,1,1,201,Antidiabetic - Biguanides\n"
    # an inhaler: a substring rule would read this as a beta blocker
    "90000002,30000002,2200-02-05 09:30:00,Albuterol,022223,1,1,202,"
    "Asthma/COPD Therapy - Beta 2-Adrenergic Agents, Inhaled, Short Acting\n"
)

_TRIAGE = (
    "subject_id,stay_id,temperature,heartrate,resprate,o2sat,pain,acuity,sbp,dbp,chiefcomplaint\n"
    "90000001,30000001,98.0000,88.0000,18.0000,97.0000,3,2.0000,196.0000,104.0000,Headache\n"
    "90000002,30000002,97.5000,72.0000,16.0000,99.0000,0,3.0000,128.0000,78.0000,Cough\n"
    "90000003,30000003,98.1000,80.0000,17.0000,98.0000,2,3.0000,,,Rash\n"
)

_VITALSIGN = (
    "subject_id,stay_id,charttime,temperature,heartrate,resprate,o2sat,sbp,dbp,rhythm,pain\n"
    "90000001,30000001,2200-01-05 09:00:00,98.0000,86.0000,18.0000,97.0000,188.0000,98.0000,SR,2\n"
    "90000001,30000001,2200-01-05 10:00:00,98.0000,84.0000,18.0000,98.0000,402.0000,99.0000,SR,2\n"
    "90000002,30000002,2200-02-05 10:00:00,97.5000,70.0000,16.0000,99.0000,126.0000,76.0000,SR,0\n"
)


def _b(s):
    return io.StringIO(s)


# --- edstays ----------------------------------------------------------------
def test_load_edstays_keeps_only_visits_that_reached_an_admission():
    df = ed.load_edstays(_b(_EDSTAYS))
    assert set(df["stay_id"]) == {30000001, 30000002}
    assert df["hadm_id"].notna().all()


def test_load_edstays_types_the_join_keys_as_integers():
    df = ed.load_edstays(_b(_EDSTAYS))
    assert df["hadm_id"].dtype.kind in "iu"
    assert df["stay_id"].dtype.kind in "iu"


# --- medrecon ---------------------------------------------------------------
def test_medrecon_collapses_to_one_class_set_per_stay():
    out = ed.med_classes_by_stay(_b(_MEDRECON))
    row = out[out["stay_id"] == 30000001].iloc[0]
    assert row["med_classes"] == ["acei", "thiazide"]


def test_medrecon_deduplicates_on_subject_name_gsn():
    """A repeated reconciliation row must not make one drug look like several."""
    out = ed.med_classes_by_stay(_b(_MEDRECON))
    assert out[out["stay_id"] == 30000001].iloc[0]["n_medrecon_rows"] == 3


def test_a_reconciliation_with_no_antihypertensive_is_False_not_missing():
    """Distinguishing 'reconciled, on nothing' from 'never reconciled' is the
    whole point: the first is a real negative, the second is unknown."""
    out = ed.med_classes_by_stay(_b(_MEDRECON))
    row = out[out["stay_id"] == 30000002].iloc[0]
    assert row["med_classes"] == []
    assert row["on_bp_meds"] == False  # noqa: E712


def test_an_inhaler_is_not_a_beta_blocker():
    out = ed.med_classes_by_stay(_b(_MEDRECON))
    assert "beta_blocker" not in out[out["stay_id"] == 30000002].iloc[0]["med_classes"]


def test_statin_is_captured_for_prevent():
    out = ed.med_classes_by_stay(_b(_MEDRECON))
    assert out[out["stay_id"] == 30000001].iloc[0]["statin_use"] == True  # noqa: E712
    assert out[out["stay_id"] == 30000002].iloc[0]["statin_use"] == False  # noqa: E712


def test_on_bp_meds_is_true_when_any_antihypertensive_is_reconciled():
    out = ed.med_classes_by_stay(_b(_MEDRECON))
    assert out[out["stay_id"] == 30000001].iloc[0]["on_bp_meds"] == True  # noqa: E712


# --- vitals -----------------------------------------------------------------
def test_triage_bp_parses_zero_padded_float_strings():
    df = ed.load_triage_bp(_b(_TRIAGE))
    row = df[df["stay_id"] == 30000001].iloc[0]
    assert row["sbp"] == 196.0 and row["dbp"] == 104.0


def test_every_ed_blood_pressure_is_admission_context():
    """ED BP is acute, full stop. If any row said chronic or office, the engine
    would stage an acute reading and produce a label it must abstain on."""
    for frame in (ed.load_triage_bp(_b(_TRIAGE)), ed.load_vitalsign_bp(_b(_VITALSIGN))):
        assert (frame["bp_context"] == "admission").all()
        assert not (frame["bp_context"].isin(["chronic", "office"])).any()


def test_rows_without_a_blood_pressure_are_dropped():
    df = ed.load_triage_bp(_b(_TRIAGE))
    assert 30000003 not in set(df["stay_id"])


def test_implausible_ed_bp_is_rejected_not_clipped():
    df = ed.load_vitalsign_bp(_b(_VITALSIGN))
    assert 402.0 not in set(df["sbp"])
    assert len(df) == 2


def test_vitalsign_keeps_charttime_as_a_datetime():
    df = ed.load_vitalsign_bp(_b(_VITALSIGN))
    assert pd.api.types.is_datetime64_any_dtype(df["charttime"])


# --- hypertensive urgency ---------------------------------------------------
def test_hypertensive_urgency_flag_uses_acute_bp_only():
    """The one legitimate use of ED BP: a severity flag, never chronic staging."""
    df = ed.load_triage_bp(_b(_TRIAGE))
    flagged = ed.hypertensive_urgency(df)
    assert flagged[flagged["stay_id"] == 30000001].iloc[0]["hypertensive_urgency"] == True  # noqa: E712
    assert flagged[flagged["stay_id"] == 30000002].iloc[0]["hypertensive_urgency"] == False  # noqa: E712


# --- dedupe scope (regression) ----------------------------------------------
_MEDRECON_TWO_VISITS = (
    "subject_id,stay_id,charttime,name,gsn,ndc,etc_rn,etccode,etcdescription\n"
    "90000001,30000001,2200-01-05 08:30:00,Lisinopril,1,1,1,1,ACE Inhibitors\n"
    # same patient, same drug, a LATER visit -- a different reconciliation event
    "90000001,30000077,2201-01-05 08:30:00,Lisinopril,1,1,1,1,ACE Inhibitors\n"
)


def test_dedupe_is_scoped_to_the_stay_not_the_patient_history():
    """Deduplicating on (subject, name, gsn) across the whole table drops the
    later visit's row as a 'duplicate'. On the real table that destroys 46,809
    ED stays outright, and a stay with no surviving rows is indistinguishable
    from one that never had a reconciliation -- so on_bp_meds silently flips
    from known to unknown and the patient abstains instead of being labelled."""
    out = ed.med_classes_by_stay(_b(_MEDRECON_TWO_VISITS))
    assert set(out["stay_id"]) == {30000001, 30000077}
    for _, row in out.iterrows():
        assert row["med_classes"] == ["acei"]


def test_repeated_rows_within_one_stay_still_collapse():
    """The dedupe must still do its original job."""
    dup = (
        "subject_id,stay_id,charttime,name,gsn,ndc,etc_rn,etccode,etcdescription\n"
        "90000001,30000001,2200-01-05 08:30:00,Lisinopril,1,1,1,1,ACE Inhibitors\n"
        "90000001,30000001,2200-01-05 09:30:00,Lisinopril,1,1,1,1,ACE Inhibitors\n"
    )
    out = ed.med_classes_by_stay(_b(dup))
    assert out.iloc[0]["n_medrecon_rows"] == 1
