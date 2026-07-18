"""Tests for the shared controlled-vocabulary module (HC-3)."""
import json
from pathlib import Path

import vocab


def test_schema_med_classes_match_vocab():
    """The JSON schema enum and vocab.MED_CLASSES must not drift apart."""
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "patient_profile.schema.json").read_text()
    )
    enum = schema["properties"]["med_classes"]["items"]["enum"]
    assert set(enum) == set(vocab.MED_CLASSES)


def test_schema_contraindications_match_vocab():
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "patient_profile.schema.json").read_text()
    )
    enum = schema["properties"]["contraindications"]["items"]["enum"]
    assert set(enum) == set(vocab.CONTRAINDICATION_FLAGS)


def test_drug_classification_and_combos():
    assert vocab.classify_drug("LISINOPRIL") == ["acei"]
    assert vocab.classify_drug("HYDROCHLOROTHIAZIDE; LISINOPRIL") == ["acei", "thiazide"]
    assert vocab.classify_drug("PRILOCAINE") == []          # false-positive guard
    assert vocab.classify_drug(None) == []


def test_statin():
    assert vocab.is_statin("ATORVASTATIN") is True
    assert vocab.is_statin("LISINOPRIL") is False


def test_first_line_subset_of_classes():
    assert vocab.FIRST_LINE_CLASSES <= set(vocab.MED_CLASSES)


def test_htn_anchor_and_secondary_icd():
    assert vocab.is_htn_anchor("4019", 9) is True
    assert vocab.is_htn_anchor("I10", 10) is True
    assert vocab.is_htn_anchor("I11.0", 10) is True         # dotted, sub-code
    assert vocab.is_htn_anchor("405", 9) is False           # secondary excluded
    assert vocab.is_htn_anchor("I15", 10) is False          # secondary excluded
    assert vocab.is_htn_secondary("I15.1", 10) is True
    assert vocab.is_htn_anchor("25000", 9) is False          # diabetes, not HTN


def test_bp_stage_scalar_matches_thresholds():
    assert vocab.bp_stage_scalar(118, 78) == "normal"
    assert vocab.bp_stage_scalar(122, 78) == "elevated"
    assert vocab.bp_stage_scalar(135, 82) == "stage1"
    assert vocab.bp_stage_scalar(118, 92) == "stage2"       # isolated diastolic
    assert vocab.bp_stage_scalar(None, 80) is None
    assert vocab.bp_stage_scalar(float("nan"), 80) is None
