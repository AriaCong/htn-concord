"""HC-18 -- the MIMIC profile builder's contract, without touching real data."""
import json
from pathlib import Path

import pandas as pd
import pytest

from pipelines.common import validate
from pipelines.mimic import build_profiles as bp

_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "patient_profile.schema.json").read_text()
)


def test_every_required_schema_field_is_emitted():
    """A missing required column fails validation on the first row, but only at
    runtime after a multi-hour lab pass. Cheaper to catch here."""
    for field in _SCHEMA["required"]:
        assert field in bp.PROFILE_COLUMNS, field


def test_profile_columns_are_known_to_the_schema_or_are_join_keys():
    known = set(_SCHEMA["properties"]) | {"subject_id", "hadm_id"}
    assert set(bp.PROFILE_COLUMNS) <= known


def test_range_values_match_the_schema_bounds():
    """If the gate allowed a value the schema forbids, the build would pass QA
    and then fail contract validation -- after the expensive work."""
    props = _SCHEMA["properties"]
    for col, rng in bp.RANGES.items():
        if col not in props:
            continue
        spec = props[col]
        if "minimum" in spec:
            assert rng.lo >= spec["minimum"], col
        if "maximum" in spec:
            assert rng.hi <= spec["maximum"], col


def test_age_is_offset_to_the_index_admission_not_raw_anchor_age():
    """anchor_age is the age at the patient's anchor year, which can be years
    from the index encounter. Using it raw misplaces patients against the adult
    cutoff and the PREVENT 30-79 window."""
    cohort = pd.DataFrame({
        "subject_id": [90000001],
        "hadm_id": [20000001],
        "index_admit": pd.to_datetime(["2200-06-01"]),
    })
    patients = pd.DataFrame({
        "subject_id": [90000001], "anchor_age": [60], "anchor_year": [2195],
    })
    assert bp._age_at_index(cohort, patients).iloc[0] == 65


def test_absence_reading_must_be_one_of_the_two():
    with pytest.raises(ValueError, match="reading must be one of"):
        bp.build("whatever_i_feel_like")


def test_a_synthetic_profile_row_validates_against_the_contract():
    """The shape this builder emits is the shape the schema accepts."""
    row = {c: None for c in bp.PROFILE_COLUMNS}
    row.update({
        "subject_id": 90000001, "hadm_id": 20000001,
        "source": "mimic_iv", "age": 65.0, "sex": "male",
        "sbp": 148.0, "dbp": 90.0, "bp_stage": "stage2", "bp_context": "office",
        "med_classes": ["acei"], "contraindications": ["hyperkalemia"],
        "on_bp_meds": True, "told_hypertension": True,
    })
    assert validate.validate_profiles(pd.DataFrame([row])) == 1


def test_an_admission_context_profile_would_be_rejected_by_our_own_builder():
    """bp_context is hardcoded to office because every profile BP is outpatient
    OMR taken before the index admission. ED and ICU readings are `admission`
    and never reach this column."""
    src = (Path(__file__).resolve().parents[1]
           / "pipelines" / "mimic" / "build_profiles.py").read_text()
    assert 'df["bp_context"] = "office"' in src
    assert '"admission"' not in src


def test_contraindication_names_are_the_engine_vocabulary():
    import vocab
    assert set(_SCHEMA["properties"]["contraindications"]["items"]["enum"]) == set(
        vocab.CONTRAINDICATION_FLAGS
    )
