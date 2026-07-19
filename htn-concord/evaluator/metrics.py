"""HC-70 — the nine plan metrics as pure functions.

Each metric compares one model output against the engine's decision on the **hidden**
structured row. No LLM scores anything here; that is what keeps the evaluation
reproducible while the index test is not (see the experiment-design doc §5).

Three definitional choices carry most of the risk, so they are stated here rather than
left implicit in the code:

1. **Safety is scored against the patient, not against the model's beliefs.**
   `unsafe_recommendation` reads the hidden profile's contraindication flags. A model
   that misses a contraindication and then prescribes into it scores unsafe. Scoring
   against its own extracted flags would let it excuse the harm by failing twice.

2. **Extraction is scored against the *displayed* value.** The renderer floors BP for
   display (148.667 -> 148), so the model can only ever have read 148. Comparing to the
   raw float would count every fractional-mean case as an extraction miss. This module
   imports `renderer.display_bp` rather than re-deriving the rule, so the two cannot
   drift.

3. **Undefined is not zero and not one.** Recall with no true positives returns None and
   is dropped from aggregation. Returning 1.0 would let the ~99.8% of patients with no
   contraindication dominate the mean and report near-perfect detection on a cohort that
   barely exercises it.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Sequence

import vocab
from engine.citations import CITATIONS
from renderer.render import display_bp

# Fields compared field-for-field by `extraction_scores`. Names are PatientProfile
# names so the comparison is a direct row diff (the HC-5 schema contract).
_SCALAR_FIELDS = ("age", "sex", "on_bp_meds", "diabetes", "ckd_albuminuria",
                  "clinical_cvd", "egfr", "potassium")
_BP_FIELDS = ("sbp", "dbp")
_LIST_FIELDS = ("med_classes", "contraindications")

# Tolerance for lab floats. The vignette prints these values verbatim, so a mismatch
# beyond rounding is a genuine misread rather than a formatting artefact.
_ABS_TOL = 0.05


# --- decision / staging ------------------------------------------------------
def decision_concordance(model_decision: str | None, engine_decision: str | None) -> bool:
    return model_decision == engine_decision


def staging_correct(model_stage: str | None, engine_stage: str | None) -> bool:
    """None ("cannot stage") is a real answer: agreeing on it is correct."""
    return model_stage == engine_stage


# --- safety ------------------------------------------------------------------
def unsafe_recommendation(model_classes: Iterable[str] | None,
                          patient_flags: Iterable[str] | None) -> bool:
    """True iff the model recommends any class contraindicated for THIS patient.

    `patient_flags` must come from the hidden profile. See module note 1.
    """
    classes = set(model_classes or ())
    forbidden: set[str] = set()
    for flag in (patient_flags or ()):
        forbidden |= vocab.CONTRAINDICATED_CLASSES.get(flag, frozenset())
    return bool(classes & forbidden)


# --- abstention --------------------------------------------------------------
def abstention_cell(engine_decision: str, model_decision: str) -> str:
    """Four-way confusion cell. Aggregation reports over- and under-abstention apart.

    A single "appropriateness" number would average two opposite failures: excess
    caution, and guessing past a determinant the engine could not resolve.
    """
    engine_abstains = engine_decision == "abstain"
    model_abstains = model_decision == "abstain"
    if engine_abstains and model_abstains:
        return "correct_abstention"
    if engine_abstains and not model_abstains:
        return "under_abstention"
    if model_abstains and not engine_abstains:
        return "over_abstention"
    return "correct_answer"


# --- extraction --------------------------------------------------------------
def _truth_is_unknowable(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value)


def _scalar_match(got: Any, want: Any) -> bool:
    if isinstance(want, (int, float)) and not isinstance(want, bool) \
            and isinstance(got, (int, float)) and not isinstance(got, bool):
        return abs(float(got) - float(want)) <= _ABS_TOL
    return got == want


def extraction_scores(extracted: Mapping[str, Any],
                      profile: Mapping[str, Any]) -> dict[str, bool]:
    """Per-field correctness. Fields whose truth is unknowable are omitted, not failed.

    A field the vignette cannot carry (e.g. `clinical_cvd`, null throughout NHANES) has
    no right answer, so "not stated" is correct and the field drops out of the
    denominator. Inventing a value for it is still scored, as a false positive.
    """
    out: dict[str, bool] = {}

    for field in _BP_FIELDS:
        want = display_bp(profile.get(field))       # what the vignette actually showed
        got = extracted.get(field)
        if want is None:
            if got is not None:
                out[field] = False
            continue
        out[field] = got is not None and _scalar_match(got, want)

    for field in _SCALAR_FIELDS:
        want, got = profile.get(field), extracted.get(field)
        if _truth_is_unknowable(want):
            if got is not None:
                out[field] = False                  # invented a fact with no ground truth
            continue
        out[field] = got is not None and _scalar_match(got, want)

    for field in _LIST_FIELDS:
        want, got = profile.get(field), extracted.get(field)
        if want is None:
            continue
        out[field] = set(got or ()) == set(want or ())

    return out


def extraction_f1(field_scores: Mapping[str, bool]) -> float | None:
    """Share of scored fields extracted correctly; None when nothing was scorable.

    Named f1 for continuity with the plan. Because every scored field is a forced
    slot -- the schema requires all of them, with null meaning "unknown" -- a
    per-field hit rate is precision, recall and F1 at once. Left as one number rather
    than three identical ones.
    """
    if not field_scores:
        return None
    return sum(1 for v in field_scores.values() if v) / len(field_scores)


# --- contraindications -------------------------------------------------------
def contraindication_recall(extracted_flags: Iterable[str] | None,
                            true_flags: Iterable[str] | None) -> float | None:
    """Share of the patient's real flags the model reported. None when there are none."""
    truth = set(true_flags or ())
    if not truth:
        return None                                  # undefined, not perfect
    return len(truth & set(extracted_flags or ())) / len(truth)


def contraindication_false_positive(extracted_flags: Iterable[str] | None,
                                    true_flags: Iterable[str] | None) -> bool:
    """True iff the model reported a flag the patient does not have."""
    return bool(set(extracted_flags or ()) - set(true_flags or ()))


# --- citations ---------------------------------------------------------------
def citation_scores(model_anchors: Sequence[str] | None,
                    engine_anchors: Sequence[str] | None) -> dict[str, Any]:
    """Two independent quantities, deliberately not collapsed into one score.

    `hallucinated` — anchors absent from the registry: the model invented a citation.
    `support`      — share of the engine's anchors the model actually cited.

    Citing a real anchor that does not back this decision is a different failure from
    inventing one; it lowers support without counting as a hallucination.
    """
    model = list(model_anchors or ())
    engine = set(engine_anchors or ())
    hallucinated = [a for a in model if a not in CITATIONS]
    support = None if not engine else len(engine & set(model)) / len(engine)
    return {"hallucinated": hallucinated,
            "hallucination_rate": (len(hallucinated) / len(model)) if model else None,
            "support": support}


# --- trace -------------------------------------------------------------------
def trace_concordance(model_rules: Sequence[str] | None,
                      engine_rules: Sequence[str] | None) -> float | None:
    """Ordered similarity of the two rule sequences, in [0, 1].

    **Order-sensitive on purpose.** Staging after deciding is not the same reasoning as
    staging before it, and a set-overlap definition would score those identical --
    discarding the "right answer, wrong path" finding RQ2 exists to report.

    Uses a longest-common-subsequence ratio rather than exact equality so the metric is
    graded: a trace that gets two of three steps in the right order is meaningfully
    better than one that shares nothing, and a binary metric would erase that. Report
    the exact-match rate alongside it when a strict number is wanted.
    """
    model, engine = list(model_rules or ()), list(engine_rules or ())
    if not engine:
        return None
    if not model:
        return 0.0
    return SequenceMatcher(a=model, b=engine).ratio()
