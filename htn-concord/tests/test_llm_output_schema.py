"""LLMOutput / ModelRecommendation contract (HC-5).

The schema is the model half of every metric comparison, so these tests pin it to
the engine half: enums are asserted equal to vocab.py and engine.types so the two
sides of a metric can never drift apart. The committed hand example is the Master
Plan's Task-B vignette answered correctly.
"""
import json
from dataclasses import fields
from pathlib import Path

import jsonschema
import pytest

import vocab
from engine.types import Decision, TraceStep

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = _ROOT / "schemas" / "llm_output.schema.json"
_EXAMPLE = _ROOT / "schemas" / "examples" / "llm_output.example.json"
_PROFILE_SCHEMA = _ROOT / "schemas" / "patient_profile.schema.json"


def _schema():
    return json.loads(_SCHEMA.read_text())


def _example():
    return json.loads(_EXAMPLE.read_text())


def _validator():
    return jsonschema.Draft7Validator(_schema())


# ---------------------------------------------------------------------------
# Acceptance: the hand example validates
# ---------------------------------------------------------------------------

def test_hand_example_validates():
    _validator().validate(_example())


def test_schema_itself_is_valid_draft7():
    jsonschema.Draft7Validator.check_schema(_schema())


# ---------------------------------------------------------------------------
# Drift guards: the model half must equal the engine half
# ---------------------------------------------------------------------------

def test_decision_enum_matches_engine():
    enum = set(_schema()["properties"]["decision"]["enum"])
    assert enum == {d.value for d in Decision}


def test_med_class_enum_matches_vocab():
    rec = _schema()["definitions"]["ModelRecommendation"]
    assert set(rec["properties"]["drug_classes"]["items"]["enum"]) == set(vocab.MED_CLASSES)
    extracted = _schema()["properties"]["extracted"]
    assert set(extracted["properties"]["med_classes"]["items"]["enum"]) == set(vocab.MED_CLASSES)


def test_contraindication_enum_matches_vocab():
    extracted = _schema()["properties"]["extracted"]
    enum = set(extracted["properties"]["contraindications"]["items"]["enum"])
    assert enum == set(vocab.CONTRAINDICATION_FLAGS)


def test_trace_step_mirrors_engine_tracestep():
    """HC-5/HC-39 joint-design contract: the schema's TraceStep is the engine's."""
    step = _schema()["definitions"]["TraceStep"]
    assert set(step["properties"]) == {f.name for f in fields(TraceStep)}
    assert set(step["required"]) == {"rule", "detail"}


def test_extracted_fields_are_patient_profile_fields():
    """extraction_f1 scores extracted facts field-by-field against the hidden
    PatientProfile row, so every extracted field must exist there under the
    same name."""
    profile_props = set(json.loads(_PROFILE_SCHEMA.read_text())["properties"])
    extracted = set(_schema()["properties"]["extracted"]["properties"])
    assert extracted <= profile_props


def test_bp_stage_enum_matches_profile_schema():
    ours = _schema()["properties"]["bp_stage"]["enum"]
    theirs = json.loads(_PROFILE_SCHEMA.read_text())["properties"]["bp_stage"]["enum"]
    assert ours == theirs


# ---------------------------------------------------------------------------
# Strictness: deterministic scoring needs a closed contract
# ---------------------------------------------------------------------------

def _assert_invalid(doc):
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(doc)


def test_unknown_top_level_field_rejected():
    doc = _example()
    doc["free_text_answer"] = "the model rambles here"
    _assert_invalid(doc)


def test_unknown_drug_class_rejected():
    doc = _example()
    doc["recommendation"]["drug_classes"] = ["renin_inhibitor"]
    _assert_invalid(doc)


def test_unknown_decision_rejected():
    doc = _example()
    doc["decision"] = "start_two_drugs"
    _assert_invalid(doc)


def test_missing_trace_rejected():
    doc = _example()
    del doc["trace"]
    _assert_invalid(doc)


def test_abstain_requires_reason():
    doc = _example()
    doc["decision"] = "abstain"
    doc["abstain_reason"] = None
    _assert_invalid(doc)


def test_non_abstain_forbids_reason():
    doc = _example()
    assert doc["decision"] != "abstain"
    doc["abstain_reason"] = "acute_context"
    _assert_invalid(doc)


def test_abstain_with_reason_validates():
    doc = _example()
    doc["decision"] = "abstain"
    doc["abstain_reason"] = "acute_context"
    doc["recommendation"]["drug_classes"] = []
    _validator().validate(doc)
