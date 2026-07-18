"""clinical_cvd is part of the PatientProfile contract (added for HC-33)."""
import json
from pathlib import Path

import jsonschema

_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "patient_profile.schema.json"


def _schema():
    return json.loads(_SCHEMA.read_text())


def test_schema_declares_clinical_cvd():
    prop = _schema()["properties"]["clinical_cvd"]
    assert prop["type"] == ["boolean", "null"]


def test_profile_with_clinical_cvd_validates():
    row = {
        "source": "nhanes", "age": 60, "sex": "male", "sbp": 135, "dbp": 85,
        "bp_stage": "stage1", "bp_context": "chronic", "med_classes": [],
        "contraindications": [], "clinical_cvd": None,
    }
    jsonschema.Draft7Validator(_schema()).validate(row)
    row["clinical_cvd"] = True
    jsonschema.Draft7Validator(_schema()).validate(row)
