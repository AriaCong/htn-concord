"""Tests for the shared controlled-vocabulary module (HC-3)."""
import json
from pathlib import Path

import pytest

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


# --- medrecon therapeutic-class mapping (HC-20) -----------------------------
@pytest.mark.parametrize("desc,expected", [
    ("ACE Inhibitors", ["acei"]),
    ("Angiotensin II Receptor Blockers (ARBs)", ["arb"]),
    ("Beta Blockers Cardiac Selective", ["beta_blocker"]),
    ("Alpha-Beta Blockers", ["beta_blocker"]),
    ("Calcium Channel Blockers - Dihydropyridines", ["dhp_ccb"]),
    ("Calcium Channel Blockers - Benzothiazepines", ["nondhp_ccb"]),
    ("Calcium Channel Blockers - Phenylakylamines", ["nondhp_ccb"]),
    ("Diuretic - Thiazides and Related", ["thiazide"]),
    ("Diuretic - Loop", ["loop_diuretic"]),
    ("Aldosterone Receptor Antagonists", ["mra"]),
    ("Peripheral Alpha-1 Receptor Blockers", ["alpha_blocker"]),
])
def test_etc_description_maps_to_engine_classes(desc, expected):
    assert vocab.classify_etc_description(desc) == expected


@pytest.mark.parametrize("desc,expected", [
    ("ACE Inhibitor and Diuretic Combinations", ["acei", "thiazide"]),
    ("Angiotensin II Receptor Blocker (ARB)-Calcium Channel Blocker-Diuretic",
     ["arb", "dhp_ccb", "thiazide"]),
    ("Cardiac Selective Beta Blocker-Thiazide Diuretic and Related Comb.",
     ["beta_blocker", "thiazide"]),
])
def test_etc_description_combination_products_yield_every_component(desc, expected):
    assert vocab.classify_etc_description(desc) == expected


@pytest.mark.parametrize("desc", [
    # Each of these is a real medrecon class that a substring rule would
    # wrongly capture. The counts beside them are rows in the real table.
    "Asthma/COPD Therapy - Beta 2-Adrenergic Agents, Inhaled, Short Acting",  # ~57k
    "Ophthalmic - Beta blockers-Carbonic Anhydrase Inhibitor Combinations",   # ~2k
    "Ophthalmic - Beta blockers-Adrenergic Combinations",
    "Aminopenicillin Antibiotic - Beta-lactamase Inhibitor Combinations",
    "Antidepressant - Alpha-2 Receptor Antagonists (NaSSA)",
    "Minerals and Electrolytes - Calcium Replacement/Vitamin D Combinations",  # ~21k
    "Antacid - Calcium",
    "Analgesic - Neuronal (N)-Type Calcium Channel Blockers (NCCBs)",
    "Pulmonary Antihypertensive Agents - Prostacyclin-type",
    "Prostatic Hypertrophy Agent - alpha-1-Adrenoceptor Antagonists",          # ~15k
    "Diuretic - Carbonic Anhydrase Inhibitors",
    "Antidiuretic and Vasopressor Hormones",
    "Smoking Deterrents - Nicotinic Receptor Partial Agonist, alpha4beta2",
])
def test_etc_description_rejects_lookalike_classes(desc):
    """Exact matching is the point: none of these is a systemic antihypertensive,
    and every one of them is caught by a naive substring rule."""
    assert vocab.classify_etc_description(desc) == []


@pytest.mark.parametrize("desc", [
    "Renin Inhibitor, Direct",
    "Central Alpha-2 Receptor Agonists",
    "Direct Acting Vasodilators",
    "Diuretic - Potassium Sparing",
])
def test_etc_description_known_gaps_map_to_nothing(desc):
    """Real antihypertensives that MED_CLASSES cannot express. They map to
    nothing rather than to an approximate neighbour -- calling clonidine an
    alpha_blocker or amiloride an mra would be wrong, not merely coarse.
    Documented limitation, flagged for HC-49."""
    assert vocab.classify_etc_description(desc) == []


def test_etc_description_handles_missing_and_unknown():
    assert vocab.classify_etc_description(None) == []
    assert vocab.classify_etc_description("") == []
    assert vocab.classify_etc_description("Some Class Invented In 2027") == []


def test_every_mapped_class_is_in_the_engine_vocabulary():
    """A typo here would silently drop a med class at profile-build time."""
    for classes in vocab.ETC_DESCRIPTION_CLASS.values():
        for c in classes:
            assert c in vocab.MED_CLASSES, c


def test_statin_by_therapeutic_class():
    assert vocab.is_statin_etc_description(
        "Antihyperlipidemic - HMG CoA Reductase Inhibitors (statins)")
    assert not vocab.is_statin_etc_description("Diuretic - Loop")
    assert not vocab.is_statin_etc_description(None)
