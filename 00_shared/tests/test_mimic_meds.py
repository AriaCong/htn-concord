"""HC-17 -- pre-index medication reconciliation. The bottleneck of the MIMIC arm.

on_bp_meds is the variable separating *initiate* from *intensify*, and medrecon
is its only leakage-safe source. Synthetic ids only (9xxxxxxx, HC-56).
"""
import io

import pandas as pd

from pipelines.mimic import meds

_EDSTAYS = (
    "subject_id,hadm_id,stay_id,intime,outtime,gender,race,arrival_transport,disposition\n"
    "90000001,20000001,30000001,2200-01-05 08:00:00,2200-01-05 14:00:00,F,W,AMBULANCE,ADMITTED\n"
    "90000002,20000002,30000002,2200-02-05 09:00:00,2200-02-05 18:00:00,M,B,WALK IN,ADMITTED\n"
    # a DIFFERENT, later admission for subject 1 -- its meds must not bind
    "90000001,20000099,30000099,2201-01-05 08:00:00,2201-01-05 14:00:00,F,W,WALK IN,ADMITTED\n"
)

_MEDRECON = (
    "subject_id,stay_id,charttime,name,gsn,ndc,etc_rn,etccode,etcdescription\n"
    "90000001,30000001,2200-01-05 08:30:00,Lisinopril,1,1,1,1,ACE Inhibitors\n"
    "90000002,30000002,2200-02-05 09:30:00,Metformin,2,1,1,2,Antidiabetic - Biguanides\n"
    # subject 1's LATER visit -- amlodipine here must not reach the index profile
    "90000001,30000099,2201-01-05 08:30:00,Amlodipine,3,1,1,3,"
    "Calcium Channel Blockers - Dihydropyridines\n"
)

_COHORT = pd.DataFrame({
    "subject_id": [90000001, 90000002, 90000003],
    "hadm_id":    [20000001, 20000002, 20000003],
})


def _run(cohort=_COHORT):
    return meds.pre_index_meds(io.StringIO(_MEDRECON), io.StringIO(_EDSTAYS), cohort)


def test_home_meds_come_from_the_index_stay_only():
    out = _run().set_index("subject_id")
    assert out.loc[90000001, "med_classes"] == ["acei"]


def test_a_later_visits_medications_cannot_reach_the_index_profile():
    """Subject 1 starts amlodipine at a later admission. Binding it here would
    import a post-decision fact into the hidden label."""
    out = _run().set_index("subject_id")
    assert "dhp_ccb" not in out.loc[90000001, "med_classes"]


def test_a_reconciliation_without_antihypertensives_is_a_real_negative():
    out = _run().set_index("subject_id")
    assert out.loc[90000002, "on_bp_meds"] == False   # noqa: E712
    assert out.loc[90000002, "med_classes"] == []


def test_no_reconciliation_yields_null_never_false():
    """THE rule of this ticket. Subject 3 has no ED stay and so no
    reconciliation. Defaulting to False would relabel every intensify case in
    that group as initiate -- a wrong label, silently, at scale."""
    out = _run().set_index("subject_id")
    assert pd.isna(out.loc[90000003, "on_bp_meds"])


def test_med_classes_is_an_empty_list_when_unknown_not_a_null():
    """The schema requires an array. An unknown med history is expressed by
    on_bp_meds being null, not by med_classes being null -- otherwise the
    profile fails contract validation."""
    out = _run().set_index("subject_id")
    assert out.loc[90000003, "med_classes"] == []


def test_on_bp_meds_column_is_nullable_boolean():
    out = _run()
    assert str(out["on_bp_meds"].dtype) == "boolean"


def test_statin_use_is_null_when_there_is_no_reconciliation():
    """statin_use feeds PREVENT. Unknown must not read as not-on-a-statin."""
    out = _run().set_index("subject_id")
    assert pd.isna(out.loc[90000003, "statin_use"])


def test_output_has_one_row_per_cohort_subject():
    out = _run()
    assert len(out) == len(_COHORT)
    assert set(out["subject_id"]) == set(_COHORT["subject_id"])


def test_med_classes_are_all_in_the_engine_vocabulary():
    import vocab
    out = _run()
    for cs in out["med_classes"]:
        for c in cs:
            assert c in vocab.MED_CLASSES
