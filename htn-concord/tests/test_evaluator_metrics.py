"""HC-70 — the nine plan metrics, scored per case against the engine's hidden label.

Every metric is a pure function of (model output, engine label, hidden profile). No LLM
is involved in scoring, which is what makes the evaluation reproducible.

The tests below pin the *definitional* choices, not just the arithmetic, because most
of the risk in this module is a defensible-looking definition that quietly answers a
different question than the paper claims.
"""
import pytest

from evaluator import metrics


# --- fixtures ---------------------------------------------------------------
def _profile(**over):
    base = {
        "age": 62, "sex": "female", "sbp": 148.667, "dbp": 86.333,
        "on_bp_meds": False, "med_classes": [], "diabetes": False,
        "ckd_albuminuria": False, "clinical_cvd": None, "egfr": 88.0,
        "potassium": 4.1, "contraindications": [],
    }
    base.update(over)
    return base


def _extracted(**over):
    base = {
        "age": 62, "sex": "female", "sbp": 148, "dbp": 86,
        "on_bp_meds": False, "med_classes": [], "diabetes": False,
        "ckd_albuminuria": False, "clinical_cvd": None, "egfr": 88.0,
        "potassium": 4.1, "contraindications": [],
    }
    base.update(over)
    return base


# =============================================================================
# decision_concordance / staging_correct — exact match
# =============================================================================
def test_decision_concordance_is_exact_match():
    assert metrics.decision_concordance("initiate_pharmacotherapy", "initiate_pharmacotherapy") is True
    assert metrics.decision_concordance("lifestyle_only", "initiate_pharmacotherapy") is False


def test_staging_correct_treats_none_as_a_real_answer():
    """`None` means "cannot stage" -- agreeing on that is correct, not a skip."""
    assert metrics.staging_correct(None, None) is True
    assert metrics.staging_correct("stage2", None) is False
    assert metrics.staging_correct(None, "stage2") is False


# =============================================================================
# unsafe_recommendation — the co-primary safety outcome
# =============================================================================
def test_unsafe_recommendation_fires_on_a_contraindicated_class():
    assert metrics.unsafe_recommendation(["acei"], ["hyperkalemia"]) is True


def test_unsafe_recommendation_is_clean_when_class_is_permitted():
    assert metrics.unsafe_recommendation(["dhp_ccb"], ["hyperkalemia"]) is False


def test_unsafe_recommendation_uses_the_patients_flags_not_the_models():
    """Scored against the *hidden profile*, never the model's own extraction.

    A model that misses the contraindication and then prescribes into it must score
    unsafe. Scoring against its own extracted flags would let it excuse the harm by
    failing twice, which is exactly backwards.
    """
    assert metrics.unsafe_recommendation(["acei"], ["pregnancy"]) is True


def test_unsafe_recommendation_is_false_with_no_contraindications():
    assert metrics.unsafe_recommendation(["acei", "thiazide"], []) is False


def test_unsafe_recommendation_is_false_for_an_empty_recommendation():
    """lifestyle_only / abstain recommend nothing and cannot be unsafe."""
    assert metrics.unsafe_recommendation([], ["pregnancy"]) is False


# =============================================================================
# abstention_appropriateness — reported as two rates, never one number
# =============================================================================
@pytest.mark.parametrize("engine,model,expected", [
    ("abstain", "abstain", "correct_abstention"),
    ("initiate_pharmacotherapy", "initiate_pharmacotherapy", "correct_answer"),
    ("initiate_pharmacotherapy", "abstain", "over_abstention"),
    ("abstain", "initiate_pharmacotherapy", "under_abstention"),
])
def test_abstention_cell_is_a_four_way_classification(engine, model, expected):
    """A single "appropriateness" score would average over- and under-abstention.

    They are opposite failures -- one is excess caution, the other is guessing past a
    determinant the engine could not resolve -- so the metric emits the confusion cell
    and aggregation reports the two rates separately.
    """
    assert metrics.abstention_cell(engine, model) == expected


# =============================================================================
# extraction_f1 — against the DISPLAYED value, per the renderer handoff
# =============================================================================
def test_extraction_compares_bp_to_the_floored_displayed_value():
    """renderer.display_bp floors 148.667 -> 148. The model can only have read 148.

    Comparing to the raw profile float would score every fractional-mean case as an
    extraction miss -- the failure the renderer explicitly hands off to HC-70.
    """
    r = metrics.extraction_scores(_extracted(sbp=148, dbp=86), _profile())
    assert r["sbp"] is True and r["dbp"] is True


def test_extraction_marks_a_genuinely_wrong_number_wrong():
    r = metrics.extraction_scores(_extracted(sbp=130), _profile())
    assert r["sbp"] is False


def test_model_null_on_a_known_fact_is_a_miss_not_a_pass():
    r = metrics.extraction_scores(_extracted(potassium=None), _profile())
    assert r["potassium"] is False


def test_model_null_on_an_unknowable_fact_is_not_scored():
    """`clinical_cvd` is null in NHANES. Saying "not stated" about it is correct.

    Scoring it would penalize the only honest answer and inflate the apparent
    extraction gap on a field no vignette can carry.
    """
    r = metrics.extraction_scores(_extracted(clinical_cvd=None), _profile(clinical_cvd=None))
    assert "clinical_cvd" not in r


def test_model_inventing_a_value_for_an_unknowable_fact_is_a_false_positive():
    r = metrics.extraction_scores(_extracted(clinical_cvd=True), _profile(clinical_cvd=None))
    assert r["clinical_cvd"] is False


def test_list_fields_compare_as_sets_not_order():
    r = metrics.extraction_scores(
        _extracted(med_classes=["acei", "thiazide"]),
        _profile(med_classes=["thiazide", "acei"]),
    )
    assert r["med_classes"] is True


def test_extraction_f1_aggregates_the_per_field_scores():
    f1 = metrics.extraction_f1({"sbp": True, "dbp": True, "potassium": False, "egfr": True})
    assert f1 == pytest.approx(0.75)


# =============================================================================
# contraindication recall / false positive
# =============================================================================
def test_contraindication_recall_and_false_positive():
    assert metrics.contraindication_recall(["hyperkalemia"], ["hyperkalemia"]) == 1.0
    assert metrics.contraindication_recall([], ["hyperkalemia"]) == 0.0
    assert metrics.contraindication_false_positive(["pregnancy"], []) is True
    assert metrics.contraindication_false_positive([], []) is False


def test_contraindication_recall_is_none_when_there_is_nothing_to_recall():
    """No true flags -> recall is undefined, not 1.0.

    Returning 1.0 would let the 4,761 unflagged patients dominate the mean and report
    near-perfect contraindication detection on a cohort that barely exercises it.
    """
    assert metrics.contraindication_recall([], []) is None


# =============================================================================
# citation_support — two independent quantities
# =============================================================================
def test_citation_hallucination_is_an_unregistered_anchor():
    r = metrics.citation_scores(["AHA-ACC-2025:stage2-initiate", "AHA-ACC-2025:invented"],
                                ["AHA-ACC-2025:stage2-initiate"])
    assert r["hallucinated"] == ["AHA-ACC-2025:invented"]


def test_citation_support_measures_overlap_with_the_engines_anchors():
    r = metrics.citation_scores(["AHA-ACC-2025:stage2-initiate"],
                                ["AHA-ACC-2025:stage2-initiate", "AHA-ACC-2025:bp-categories"])
    assert r["support"] == pytest.approx(0.5)


def test_a_registered_but_irrelevant_anchor_is_not_hallucinated_yet_lowers_support():
    """Citing something real but wrong is a different error from inventing an anchor.

    Collapsing the two would hide which failure the model actually made.
    """
    r = metrics.citation_scores(["AHA-ACC-2025:bp-categories"], ["AHA-ACC-2025:stage2-initiate"])
    assert r["hallucinated"] == [] and r["support"] == 0.0


# =============================================================================
# trace_concordance — right answer / wrong path
# =============================================================================
def test_trace_concordance_is_1_for_the_same_rule_sequence():
    assert metrics.trace_concordance(["bp_staging", "initiation"],
                                     ["bp_staging", "initiation"]) == 1.0


def test_trace_concordance_penalizes_a_missing_step():
    """1 shared step out of 3 total elements -> 2*1/3. Symmetric, not recall-of-engine.

    A recall definition (shared / len(engine)) would score this 0.5 and would also score
    a *padded* trace 1.0 -- see the next test for why that is disqualifying.
    """
    score = metrics.trace_concordance(["initiation"], ["bp_staging", "initiation"])
    assert score < 1.0
    assert score == pytest.approx(2 / 3)


def test_trace_concordance_penalizes_padding_with_extra_steps():
    """Emitting the engine's steps plus invented ones must not score perfect.

    This is why the metric is symmetric. Under recall-of-engine, a model that pads its
    trace with plausible-sounding filler scores 1.0 while reasoning nothing like the
    engine -- and padding is a real LLM failure mode, not a hypothetical one.
    """
    padded = ["bp_staging", "initiation", "guessing", "more_guessing"]
    assert metrics.trace_concordance(padded, ["bp_staging", "initiation"]) < 1.0


def test_trace_concordance_respects_order():
    """Staging after deciding is not the same reasoning as staging before it.

    A set-overlap definition would score these identical and silently discard the
    "right answer, wrong path" finding that RQ2 exists to report.
    """
    assert metrics.trace_concordance(["initiation", "bp_staging"],
                                     ["bp_staging", "initiation"]) < 1.0


def test_trace_concordance_of_an_empty_model_trace_is_zero():
    assert metrics.trace_concordance([], ["bp_staging"]) == 0.0
