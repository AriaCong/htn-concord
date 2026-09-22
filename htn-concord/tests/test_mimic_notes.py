"""HC-19 -- discharge-note selection and Task-C silver labels.

Synthetic ids and synthetic prose only (9xxxxxxx, HC-56).
"""
import io

import pandas as pd
import pytest

from pipelines.mimic import notes

# The deid placeholder must survive byte-for-byte. Note the doubled note_id row.
_NOTES = (
    "note_id,subject_id,hadm_id,note_type,note_seq,charttime,storetime,text\n"
    'N1,90000001,20000001,DS,1,2200-06-05 12:00:00,2200-06-05 13:00:00,'
    '"Patient seen on ___ with BP 150/92. Started on ___ 10 mg."\n'
    'N1,90000001,20000001,DS,1,2200-06-05 12:00:00,2200-06-05 13:00:00,'
    '"Patient seen on ___ with BP 150/92. Started on ___ 10 mg."\n'
    'N2,90000001,20000001,DS,2,2200-06-05 14:00:00,2200-06-05 15:00:00,'
    '"Addendum."\n'
    'N3,90000002,20000002,DS,1,2200-07-05 12:00:00,2200-07-05 13:00:00,'
    '"Second patient summary."\n'
    'N4,90000003,,DS,1,2200-08-05 12:00:00,2200-08-05 13:00:00,'
    '"No admission attached."\n'
)

_PROFILES = pd.DataFrame({
    "subject_id": [90000001, 90000002],
    "hadm_id": [20000001, 20000002],
    "age": [65.0, 70.0],
    "sex": ["male", "female"],
    "diabetes": [True, False],
    "on_bp_meds": [True, None],
    "med_classes": [["acei"], []],
    "creatinine": [1.4, 0.9],
    "potassium": [5.8, 4.1],
    "contraindications": [["hyperkalemia"], []],
    "sbp": [150.0, 132.0],
    "bp_stage": ["stage2", "stage1"],
})


def _b():
    return io.StringIO(_NOTES)


def test_notes_are_deduplicated_on_note_id():
    out = notes.load_discharge_notes(_b(), chunk_rows=2)
    assert out["note_id"].is_unique


def test_notes_without_an_admission_are_dropped():
    out = notes.load_discharge_notes(_b(), chunk_rows=2)
    assert "N4" not in set(out["note_id"])


def test_hadm_filter_restricts_the_corpus():
    out = notes.load_discharge_notes(_b(), hadm_ids={20000001}, chunk_rows=2)
    assert set(out["hadm_id"]) == {20000001}


def test_exactly_one_summary_per_admission():
    out = notes.select_index_notes(notes.load_discharge_notes(_b(), chunk_rows=2))
    assert out["hadm_id"].is_unique
    assert len(out) == 2


def test_selection_is_deterministic_on_note_seq_then_note_id():
    """Otherwise the Task-C corpus depends on row order and is not reproducible."""
    out = notes.select_index_notes(notes.load_discharge_notes(_b(), chunk_rows=2))
    assert out[out["hadm_id"] == 20000001].iloc[0]["note_id"] == "N1"


def test_deid_placeholders_survive_verbatim():
    """Never fabricate across a redaction. The token is data, not noise."""
    out = notes.select_index_notes(notes.load_discharge_notes(_b(), chunk_rows=2))
    text = out[out["hadm_id"] == 20000001].iloc[0]["text"]
    assert text == "Patient seen on ___ with BP 150/92. Started on ___ 10 mg."
    assert text.count("___") == 2


def test_chunking_does_not_change_the_selection():
    a = notes.select_index_notes(notes.load_discharge_notes(_b(), chunk_rows=1))
    b = notes.select_index_notes(notes.load_discharge_notes(_b(), chunk_rows=999))
    pd.testing.assert_frame_equal(a, b)


def test_note_stats_report_length_without_emitting_text():
    s = notes.note_stats(notes.select_index_notes(notes.load_discharge_notes(_b(), chunk_rows=2)))
    assert s["n_admissions"] == 2
    assert s["notes_with_deid_placeholder"] == 1
    assert "text" not in s


# --- silver labels ----------------------------------------------------------
def test_silver_labels_come_from_structured_fields():
    out = notes.silver_labels(_PROFILES).set_index("hadm_id")
    assert out.loc[20000001, "diabetes"] == True   # noqa: E712
    assert out.loc[20000001, "potassium"] == 5.8
    assert out.loc[20000001, "med_classes"] == ["acei"]


def test_silver_labels_refuse_a_frame_carrying_note_text():
    """Deriving a label from the same text the model is asked to read would
    score Task C against itself. Enforced, not merely intended."""
    with pytest.raises(ValueError, match="circular|note text"):
        notes.silver_labels(_PROFILES.assign(text="Patient seen on ___"))


def test_silver_labels_exclude_bp_stage():
    """Chronic stage comes from outpatient OMR, which the discharge note does
    not contain. Asking a model to extract it would score it for failing to
    find something that is not there."""
    out = notes.silver_labels(_PROFILES)
    assert "bp_stage" not in out.columns
    assert "sbp" not in out.columns


def test_silver_labels_preserve_unknown_as_unknown():
    out = notes.silver_labels(_PROFILES).set_index("hadm_id")
    assert pd.isna(out.loc[20000002, "on_bp_meds"])


def test_text_cohort_pairs_notes_with_their_silver_labels():
    n, s = notes.build_text_cohort(_PROFILES, notes_path=_b())
    assert set(n["hadm_id"]) == set(s["hadm_id"])
    assert len(n) == len(s) == 2
