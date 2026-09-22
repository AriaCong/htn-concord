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
#: Values every level must still state verbatim: eGFR, potassium, UACR, HbA1c,
#: total cholesterol, HDL, age.
#:
#: Blood pressure (154/91) was in this tuple until HC-101 and is deliberately
#: no longer: `hard` now states the three readings and makes the reader average
#: them. Substring presence was always a *proxy* for the property that matters
#: -- that the decision-relevant value is recoverable -- and the two come apart
#: exactly at the change K2 required. The proxy is replaced for BP, not dropped,
#: by `test_bp_is_exactly_recoverable_at_every_level`, which is strictly
#: stronger: it recomputes the mean of whatever readings the level states and
#: asserts it equals the engine's own displayed value. A `hard` vignette that
#: truly withheld BP, or stated readings averaging to anything else, fails that
#: test at every level. Nothing here licenses removing another value from this
#: tuple; a value leaves it only when a stronger check replaces it.
_DECISION_RELEVANT = ("42", "4.8", "55", "7.4", "190", "48", "68")


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


# ===========================================================================
# 4. The `hard` extraction burden (HC-101 / kill criterion K2)
# ===========================================================================
# The HC-80 pilot found the ladder inert: extraction F1 was 0.918 at simple,
# moderate AND hard, to three decimals, with identical per-field counts. Every
# fact was stated in the same sentence with the same label and units at all
# three levels, so reordering paragraphs and adding visit-logistics filler cost
# a reader nothing.
#
# Two mechanisms now make `hard` cost something to read, both aimed at fields
# the evaluator actually scores (`evaluator.metrics`: sbp, dbp, potassium among
# the twelve). Neither removes information -- both change what it costs to
# recover it, which is the line drawn in the renderer's module docstring.

def _bp_pairs(text: str) -> list[tuple[int, int]]:
    """Every `nnn/nn` blood-pressure pair in the rendered text."""
    return [(int(s), int(d)) for s, d in re.findall(r"\b(\d{2,3})/(\d{2,3})\b", text)]


def _mean(values):
    return sum(values) / len(values)


# --- mechanism (a): give the readings, not the average ---------------------
def test_hard_states_each_reading_and_not_the_pre_averaged_value(profile):
    """`hard` hands over the three readings; the average must be computed."""
    profile.update(sbp=154.0, dbp=91.0, bp_n_readings=3.0)
    pairs = _bp_pairs(render(profile, "hard", seed=5))
    assert len(pairs) == 3, "hard must show every reading"
    assert (154, 91) not in pairs, "the pre-averaged value must not be handed over"


def test_simple_and_moderate_still_state_the_averaged_bp(profile):
    """Only `hard` changes. The easier levels keep handing the value over."""
    profile.update(sbp=154.0, dbp=91.0, bp_n_readings=3.0)
    for level in ("simple", "moderate"):
        assert "154/91" in render(profile, level, seed=5)


@pytest.mark.parametrize("sbp,dbp,n", [
    (154.0, 91.0, 3.0), (129.333333, 80.666667, 3.0), (119.0, 75.0, 3.0),
    (167.5, 66.25, 3.0), (98.0, 61.0, 2.0), (142.0, 88.0, 1.0),
])
def test_hard_readings_average_exactly_to_the_displayed_value(profile, sbp, dbp, n):
    """The readings must average to the value the evaluator compares against.

    `evaluator.metrics` scores extraction against `display_bp(profile.sbp)` --
    the floored value the vignette showed. If the readings averaged to anything
    else, a model that read and averaged perfectly would score as an extraction
    miss, and the level-over-level drop would measure our arithmetic rather than
    its reading. Readings are integers summing to `n * displayed`, so the mean
    is exact under any rounding convention the model might apply.
    """
    profile.update(sbp=sbp, dbp=dbp, bp_n_readings=n)
    pairs = _bp_pairs(render(profile, "hard", seed=5))
    assert len(pairs) == int(n)
    assert _mean([s for s, _ in pairs]) == display_bp(sbp)
    assert _mean([d for _, d in pairs]) == display_bp(dbp)


def test_hard_readings_stay_physiologically_plausible(profile):
    """A reading outside the cleaning gate would be a tell that the text is generated."""
    for sbp, dbp in ((98.0, 61.0), (154.0, 91.0), (196.0, 104.0)):
        profile.update(sbp=sbp, dbp=dbp, bp_n_readings=3.0)
        for seed in range(12):
            for s, d in _bp_pairs(render(profile, "hard", seed=seed)):
                assert vocab.SBP_MIN <= s <= vocab.SBP_MAX
                assert vocab.DBP_MIN <= d <= vocab.DBP_MAX
                assert s > d, "systolic must exceed diastolic in every reading"


# --- the invariant, restated ------------------------------------------------
@pytest.mark.parametrize("level", LEVELS)
def test_bp_is_exactly_recoverable_at_every_level(profile, level):
    """BP is the one value `hard` no longer states verbatim, so the invariant
    it must satisfy is restated in the form it always meant.

    `test_every_level_carries_every_decision_relevant_value` checks substring
    presence, which was the right check while every level stated every value in
    the same words. It is a *proxy* for the property that matters -- that the
    decision-relevant value is recoverable -- and the two come apart exactly at
    the change K2 requires. This replaces the proxy for BP with the property
    itself, and is strictly stronger: it verifies the recovery path arrives at
    the engine's own displayed value, which substring presence never checked.
    """
    text = render(profile, level, seed=5)
    pairs = _bp_pairs(text)
    assert pairs, f"{level} vignette carries no blood pressure"
    assert _mean([s for s, _ in pairs]) == display_bp(profile["sbp"])
    assert _mean([d for _, d in pairs]) == display_bp(profile["dbp"])


# --- mechanism (b): a temporal decoy on potassium ---------------------------
# Potassium only, deliberately. Its single path to a label is
# `k >= vocab.K_HYPERKALEMIA -> "hyperkalemia"` (pipelines/common/derive.py), so
# a decoy on the same side of that one threshold is *provably* decision-inert.
# eGFR was considered and rejected: it enters PREVENT as two continuous spline
# terms, so any alternative value shifts `prevent_10yr` and can cross
# PREVENT_STAGE1_TREAT. Conservative call, flagged for HC-49.

def test_hard_states_a_prior_potassium_beside_the_current_one(profile):
    profile["potassium"] = 4.0
    text = render(profile, "hard", seed=5)
    values = {float(v) for v in re.findall(r"\b(\d\.\d)\b", text)}
    assert 4.0 in values, "the current value must still be stated"
    assert len(values & {round(x * 0.1, 1) for x in range(25, 66)}) >= 2, \
        "hard must state a second, earlier potassium"


def test_simple_and_moderate_state_one_potassium_only(profile):
    profile["potassium"] = 4.0
    for level in ("simple", "moderate"):
        text = render(profile, level, seed=5)
        assert text.count("mmol/L") == 1


def test_the_current_potassium_is_the_one_labelled_current(profile):
    """A careless reader takes the wrong number; a careful one cannot be misled."""
    profile["potassium"] = 4.0
    text = render(profile, "hard", seed=5)
    current = re.search(r"potassium[^.;]*?(\d\.\d)\s*mmol/L today", text)
    assert current and float(current.group(1)) == 4.0


@pytest.mark.parametrize("potassium", [3.0, 3.4, 4.0, 4.8, 5.4, 5.5, 5.9, 6.4])
def test_potassium_decoy_never_crosses_the_hyperkalemia_threshold(profile, potassium):
    """The decoy may not change the flag the engine derives from potassium."""
    from renderer.render import potassium_decoy

    for seed in range(40):
        decoy = potassium_decoy(potassium, _case_rng_for(profile, seed))
        if decoy is None:
            continue
        assert (decoy >= vocab.K_HYPERKALEMIA) == (potassium >= vocab.K_HYPERKALEMIA), \
            f"decoy {decoy} crosses K_HYPERKALEMIA for a current value of {potassium}"
        assert 1.5 < decoy < 9.0, "decoy must stay inside the cleaning plausibility range"
        assert decoy != potassium, "an identical decoy is not a decoy"


def _case_rng_for(profile, seed):
    from renderer.render import _rng
    return _rng(profile, "hard", seed)
