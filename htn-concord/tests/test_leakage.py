"""Tests for the forbidden-token scanner (shared by HC-50 and HC-53)."""
from __future__ import annotations

import pytest

import leakage


@pytest.mark.parametrize("text,kind", [
    ("The patient has stage 2 hypertension.", "stage_label"),
    ("BP is consistent with Stage1 disease.", "stage_label"),
    ("She has elevated blood pressure.", "stage_label"),
    ("Therapy should be initiated today.", "decision_verb"),
    ("Consider intensification of the regimen.", "decision_verb"),
    ("The patient is at goal.", "decision_verb"),
    ("This is a contraindication to therapy.", "decision_verb"),
    ("Start an ACE inhibitor.", "drug_class"),
    ("She takes a calcium channel blocker.", "drug_class"),
    ("A thiazide would be reasonable.", "drug_class"),
    ("He is on two antihypertensives.", "drug_class"),
])
def test_forbidden_tokens_are_caught(text, kind):
    hits = leakage.scan(text)
    assert hits, f"expected a hit in {text!r}"
    assert kind in {h.kind for h in hits}


@pytest.mark.parametrize("text", [
    # The load-bearing case: a real drug name whose spelling contains a class name.
    "She takes hydrochlorothiazide 25 mg daily.",
    "He takes chlorothiazide 500 mg daily.",
    "Blood pressure was 167/66 mmHg from 3 readings.",
    "Laboratory testing showed potassium 4.0 mmol/L and creatinine 0.92 mg/dL.",
    "She takes lisinopril 10 mg daily and amlodipine 5 mg daily.",
])
def test_clean_text_passes(text):
    assert leakage.is_clean(text), leakage.scan(text)


def test_hydrochlorothiazide_is_not_a_thiazide_hit():
    """Word boundaries, not substrings: HCTZ must survive the scanner.

    A substring scan would reject every correctly-rendered vignette for a patient
    on HCTZ -- the single most common antihypertensive in the NHANES cohort.
    """
    assert leakage.scan("hydrochlorothiazide") == []
    assert leakage.scan("thiazide")  # the bare class name is still caught


def test_assert_clean_raises_with_detail():
    with pytest.raises(leakage.LeakageError) as exc:
        leakage.assert_clean("Initiate therapy for stage 2 hypertension.", where="vignette")
    assert "vignette" in str(exc.value)
    assert exc.value.hits


def test_scan_is_case_insensitive_and_ordered():
    hits = leakage.scan("STAGE 2 disease; later we should INITIATE treatment.")
    assert [h.kind for h in hits] == ["stage_label", "decision_verb"]
    assert hits[0].start < hits[1].start
