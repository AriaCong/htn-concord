"""HC-50 — vignette renderer: determinism, facts-only, and fact-preservation.

The three properties that make the rendered corpus usable as a benchmark:

1. **Deterministic** — same (profile, level, seed) -> byte-identical text.
2. **Facts-only** — no label-bearing token survives to model-facing text.
3. **Information-preserving across levels** — all three levels carry the same
   decision-relevant facts, so a per-level accuracy drop measures extraction
   difficulty rather than a fact the vignette withheld.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

import leakage
import vocab
from renderer import LEVELS, render
from renderer.render import display_bp
from renderer.phrasing import CLASS_EXEMPLARS, article_for_age

_PROFILES_CSV = Path(__file__).resolve().parents[1] / "data" / "nhanes" / "processed" / "nhanes_profiles_J.csv"


@pytest.fixture
def profile():
    return {
        "SEQN": "12345", "source": "nhanes", "age": 68.0, "sex": "female",
        "sbp": 154.0, "dbp": 91.0, "bp_stage": "stage2", "bp_context": "chronic",
        "bp_n_readings": 3.0, "creatinine": 1.3, "egfr": 42.0, "potassium": 4.8,
        "uacr": 55.0, "ckd_albuminuria": True, "diabetes": True, "clinical_cvd": None,
        "hba1c": 7.4, "total_chol": 190.0, "hdl": 48.0, "bmi": 29.2,
        "current_smoker": False, "told_hypertension": True, "on_bp_meds": True,
        "med_classes": ["dhp_ccb"], "statin_use": True, "prevent_10yr": 18.3,
        "contraindications": [],
    }


# --- 1. Determinism --------------------------------------------------------
@pytest.mark.parametrize("level", LEVELS)
def test_render_is_deterministic(profile, level):
    assert render(profile, level, seed=7) == render(profile, level, seed=7)


@pytest.mark.parametrize("level", LEVELS)
def test_seed_changes_nothing_that_matters_but_is_stable(profile, level):
    """A different seed may reword; the same seed must never drift."""
    a = [render(profile, level, seed=s) for s in range(4)]
    b = [render(profile, level, seed=s) for s in range(4)]
    assert a == b


def test_levels_differ(profile):
    texts = {render(profile, lvl, seed=1) for lvl in LEVELS}
    assert len(texts) == 3, "levels must produce distinct surface forms"


def test_unknown_level_rejected(profile):
    with pytest.raises(ValueError):
        render(profile, "extreme", seed=1)  # type: ignore[arg-type]


# --- 2. Facts-only ---------------------------------------------------------
@pytest.mark.parametrize("level", LEVELS)
def test_no_leakage_tokens(profile, level):
    leakage.assert_clean(render(profile, level, seed=3))


@pytest.mark.parametrize("level", LEVELS)
def test_label_fields_never_appear(profile, level):
    """The hidden label columns must not surface in any form."""
    text = render(profile, level, seed=3).lower()
    assert "stage2" not in text and "stage 2" not in text
    assert "18.3" not in text, "prevent_10yr is a derived label determinant"
    assert "ckd" not in text, "ckd_albuminuria is derived; render eGFR and UACR instead"


def test_contraindication_rendered_as_event_not_as_label(profile):
    profile["contraindications"] = ["angioedema_hx"]
    text = render(profile, "moderate", seed=3)
    assert "swelling" in text.lower()
    assert "angioedema" not in text.lower()
    leakage.assert_clean(text)


def test_hyperkalemia_reaches_the_model_as_a_potassium_value(profile):
    profile["contraindications"] = ["hyperkalemia"]
    profile["potassium"] = 5.9
    text = render(profile, "moderate", seed=3)
    assert "5.9" in text
    assert "hyperkalemia" not in text.lower()


def test_pregnancy_is_stated_as_a_fact(profile):
    profile["contraindications"] = ["pregnancy"]
    text = render(profile, "moderate", seed=3)
    assert "pregnant" in text.lower()
    leakage.assert_clean(text)


# --- 3. Information preservation ------------------------------------------
_DECISION_RELEVANT = ("154", "91", "42", "4.8", "55", "7.4", "190", "48", "68")


@pytest.mark.parametrize("level", LEVELS)
def test_every_level_carries_every_decision_relevant_value(profile, level):
    text = render(profile, level, seed=5)
    missing = [v for v in _DECISION_RELEVANT if v not in text]
    assert not missing, f"{level} vignette dropped {missing}"


def test_drug_identity_is_stable_across_levels(profile):
    """Same patient, same prescription, whatever the level.

    Drug choice is seeded off the case, not the level; a patient who takes
    amlodipine in the simple vignette must not take felodipine in the hard one.
    """
    profile["med_classes"] = ["acei", "thiazide", "dhp_ccb"]
    drugs = []
    for level in LEVELS:
        text = render(profile, level, seed=11).lower()
        drugs.append({d for cls in profile["med_classes"]
                      for d, _dose in CLASS_EXEMPLARS[cls] if d in text})
    assert drugs[0] == drugs[1] == drugs[2]
    assert len(drugs[0]) == 3, "one named drug per class"


@pytest.mark.parametrize("med_class,drug,dose", [
    (cls, drug, dose) for cls, opts in CLASS_EXEMPLARS.items() for drug, dose in opts
])
def test_exemplar_drugs_round_trip_to_their_class(med_class, drug, dose):
    """render -> re-extract must recover the exact class the profile recorded.

    This is what makes naming a concrete drug lossless: the vignette may not say
    "an ACE inhibitor", so it says "lisinopril", and the evaluator's extraction
    scoring only works if that maps back to exactly {acei}.
    """
    assert vocab.classify_drug(drug) == [med_class]
    assert dose


def test_med_classes_recoverable_from_rendered_text(profile):
    profile["med_classes"] = ["acei", "thiazide"]
    text = render(profile, "moderate", seed=2)
    recovered = sorted({c for tok in re.findall(r"[a-z]+", text.lower())
                        for c in vocab.classify_drug(tok)})
    assert recovered == ["acei", "thiazide"]


# --- Missing / unknown data ------------------------------------------------
def test_unknown_med_status_is_rendered_as_unknown(profile):
    """The engine ABSTAINs here; the model must be able to see the same gap."""
    profile["on_bp_meds"] = None
    profile["med_classes"] = []
    text = render(profile, "moderate", seed=1)
    assert "not documented" in text.lower()


def test_acute_context_is_disclosed(profile):
    profile["bp_context"] = "admission"
    text = render(profile, "moderate", seed=1)
    assert "emergency department" in text.lower()
    leakage.assert_clean(text)


def test_missing_values_render_without_crashing(profile):
    sparse = {"SEQN": "1", "source": "nhanes", "age": None, "sex": None,
              "sbp": None, "dbp": None, "bp_context": "chronic",
              "med_classes": [], "contraindications": [], "on_bp_meds": None}
    for level in LEVELS:
        text = render(sparse, level, seed=1)
        assert text.strip()
        leakage.assert_clean(text)


def test_unknown_sex_uses_they(profile):
    profile["sex"] = None
    profile["current_smoker"] = False
    text = render(profile, "moderate", seed=1)
    assert "they do not smoke" in text.lower() or "they " in text.lower()


@pytest.mark.parametrize("age_text,expected", [
    ("18", "an"), ("8", "an"), ("11", "an"), ("80", "an"),
    ("66", "a"), ("45", "a"), ("30", "a"), ("19", "a"),
])
def test_age_article(age_text, expected):
    assert article_for_age(age_text) == expected


def test_json_string_columns_are_accepted():
    """Profiles read back from the CSV carry list columns as JSON strings."""
    row = {"SEQN": "9", "age": 60.0, "sex": "male", "sbp": 150.0, "dbp": 95.0,
           "bp_context": "chronic", "on_bp_meds": "True",
           "med_classes": '["acei"]', "contraindications": "[]"}
    text = render(row, "simple", seed=1)
    assert "lisinopril" in text or "enalapril" in text or "ramipril" in text


# --- BP display precision --------------------------------------------------
def test_bp_is_displayed_as_whole_mmhg(profile):
    """NHANES BP is a mean; 131.667/64 is a tell that the text is generated."""
    profile["sbp"], profile["dbp"] = 131.6666667, 84.3333
    text = render(profile, "simple", seed=1)
    assert "131/84 mmHg" in text
    assert "131.6" not in text and "84.3" not in text


@pytest.mark.parametrize("sbp,dbp", [
    (129.6, 79.6), (139.9, 89.9), (119.8, 70.0), (131.667, 64.0), (154.0, 91.0),
])
def test_flooring_never_changes_the_stage(sbp, dbp):
    """The displayed BP must stage identically to the BP the label came from.

    129.6 is the case that makes this non-cosmetic: it *rounds* to 130 and crosses
    into Stage 1, which would show the model a BP one stage above its own label.
    """
    assert vocab.bp_stage_scalar(display_bp(sbp), display_bp(dbp)) == \
           vocab.bp_stage_scalar(sbp, dbp)


def test_rounding_would_have_corrupted_cases_but_flooring_does_not():
    """Guards the choice itself, so nobody 'tidies' floor into round later."""
    sbp, dbp = 129.6, 75.0
    assert vocab.bp_stage_scalar(round(sbp), round(dbp)) != vocab.bp_stage_scalar(sbp, dbp)
    assert vocab.bp_stage_scalar(display_bp(sbp), display_bp(dbp)) == \
           vocab.bp_stage_scalar(sbp, dbp)


# --- Corpus-level smoke over the real HC-10 output -------------------------
@pytest.mark.skipif(not _PROFILES_CSV.exists(), reason="HC-10 profiles not built")
def test_real_profiles_render_clean():
    """Every level of a real slice renders and passes the leakage audit."""
    with _PROFILES_CSV.open() as fh:
        rows = [row for _, row in zip(range(60), csv.DictReader(fh))]
    assert rows
    for row in rows:
        for level in LEVELS:
            leakage.assert_clean(render(row, level, seed=13),
                                 where=f"SEQN={row['SEQN']} level={level}")


@pytest.mark.skipif(not _PROFILES_CSV.exists(), reason="HC-10 profiles not built")
def test_rendered_bp_stages_identically_to_profile_bp():
    """Corpus-wide: no vignette shows a BP that stages differently from its label."""
    from tasks.profiles import load_profiles_csv

    mismatches = [
        row["SEQN"] for row in load_profiles_csv(_PROFILES_CSV)
        if row["sbp"] is not None and row["dbp"] is not None
        and vocab.bp_stage_scalar(display_bp(row["sbp"]), display_bp(row["dbp"]))
        != vocab.bp_stage_scalar(row["sbp"], row["dbp"])
    ]
    assert not mismatches, f"{len(mismatches)} profiles render a BP of a different stage"
