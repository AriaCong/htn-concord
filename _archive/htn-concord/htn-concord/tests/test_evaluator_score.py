"""HC-70 — per-case scoring and aggregation, including the acceptance gold set.

`aggregate` is where the audit findings from HC-92 become enforced rather than
remembered: the majority-class baseline is emitted beside concordance (F1), the safety
outcome is kept out of the headline average (§3), and abstention is split into its two
opposite failure modes (F4).
"""
import pytest

from evaluator import score as scoring


def _profile(**over):
    base = {"age": 62, "sex": "female", "sbp": 148.667, "dbp": 86.333,
            "on_bp_meds": False, "med_classes": [], "diabetes": False,
            "ckd_albuminuria": False, "clinical_cvd": None, "egfr": 88.0,
            "potassium": 4.1, "contraindications": []}
    base.update(over)
    return base


def _label(**over):
    base = {"decision": "initiate_pharmacotherapy", "bp_stage": "stage2",
            "abstain_reason": None,
            "citations": ["AHA-ACC-2025:bp-categories", "AHA-ACC-2025:stage2-initiate"],
            "trace": [{"rule": "bp_staging", "detail": "", "citation": None},
                      {"rule": "initiation", "detail": "", "citation": None}]}
    base.update(over)
    return base


def _output(**over):
    base = {"decision": "initiate_pharmacotherapy", "bp_stage": "stage2",
            "abstain_reason": None,
            "extracted": {"age": 62, "sex": "female", "sbp": 148, "dbp": 86,
                          "on_bp_meds": False, "med_classes": [], "diabetes": False,
                          "ckd_albuminuria": False, "clinical_cvd": None, "egfr": 88.0,
                          "potassium": 4.1, "contraindications": []},
            "recommendation": {"drug_classes": ["thiazide"], "rationale": None},
            "citations": ["AHA-ACC-2025:bp-categories", "AHA-ACC-2025:stage2-initiate"],
            "trace": [{"rule": "bp_staging", "detail": "", "citation": None},
                      {"rule": "initiation", "detail": "", "citation": None}]}
    base.update(over)
    return base


# --- per-case ----------------------------------------------------------------
def test_a_perfect_answer_scores_perfectly():
    s = scoring.score_case(_output(), _label(), _profile(), case_id="c1", level="moderate")
    assert s.decision_concordance is True
    assert s.staging_correct is True
    assert s.unsafe_recommendation is False
    assert s.extraction_f1 == 1.0
    assert s.trace_concordance == 1.0
    assert s.abstention_cell == "correct_answer"


def test_case_identity_is_carried_through_for_breakdowns():
    s = scoring.score_case(_output(), _label(), _profile(), case_id="c1", level="hard")
    assert (s.case_id, s.level) == ("c1", "hard")


def test_an_unsafe_recommendation_is_flagged_even_when_the_decision_is_right():
    """Right decision, fetotoxic class. The headline metric must not absorb this."""
    s = scoring.score_case(
        _output(recommendation={"drug_classes": ["acei"], "rationale": None}),
        _label(), _profile(contraindications=["pregnancy"]),
        case_id="c1", level="moderate")
    assert s.decision_concordance is True
    assert s.unsafe_recommendation is True


# --- aggregation -------------------------------------------------------------
def _scores(*pairs):
    """(engine_decision, model_decision) pairs -> scored cases."""
    return [scoring.score_case(_output(decision=m), _label(decision=e), _profile(),
                               case_id=f"c{i}", level="moderate")
            for i, (e, m) in enumerate(pairs)]


def test_aggregate_reports_the_majority_class_baseline_beside_concordance():
    """HC-92 audit F1: a bare concordance number is uninterpretable.

    Three of four cases are lifestyle_only, so a model answering lifestyle_only
    unconditionally scores 0.75. Reporting 0.75 concordance without that baseline
    would present a constant predictor as a result.
    """
    agg = scoring.aggregate(_scores(
        ("lifestyle_only", "lifestyle_only"),
        ("lifestyle_only", "lifestyle_only"),
        ("lifestyle_only", "initiate_pharmacotherapy"),
        ("initiate_pharmacotherapy", "initiate_pharmacotherapy"),
    ))
    assert agg["decision_concordance"] == pytest.approx(0.75)
    assert agg["majority_class_baseline"] == pytest.approx(0.75)
    assert agg["majority_class"] == "lifestyle_only"


def test_safety_outcome_is_reported_separately_and_not_folded_into_concordance():
    unsafe = scoring.score_case(
        _output(recommendation={"drug_classes": ["acei"], "rationale": None}),
        _label(), _profile(contraindications=["pregnancy"]),
        case_id="u", level="moderate")
    agg = scoring.aggregate([unsafe])
    assert agg["decision_concordance"] == 1.0          # decision was right
    assert agg["unsafe_recommendation_rate"] == 1.0    # and it was still unsafe


def test_abstention_is_reported_as_two_opposite_rates():
    agg = scoring.aggregate(_scores(
        ("abstain", "abstain"),
        ("abstain", "initiate_pharmacotherapy"),          # under-abstention: guessed
        ("initiate_pharmacotherapy", "abstain"),          # over-abstention: too cautious
        ("initiate_pharmacotherapy", "initiate_pharmacotherapy"),
    ))
    assert agg["under_abstention_rate"] == pytest.approx(0.5)   # of the 2 engine abstentions
    assert agg["over_abstention_rate"] == pytest.approx(0.5)    # of the 2 engine answers


def test_undefined_metrics_are_dropped_from_the_mean_not_counted_as_zero():
    """Contraindication recall is None for patients with no flags.

    Averaging those in as 0.0 would report near-zero recall on a cohort that mostly
    has nothing to recall; as 1.0, near-perfect. Both are artefacts of the cohort.
    """
    agg = scoring.aggregate(_scores(("lifestyle_only", "lifestyle_only")))
    assert agg["contraindication_recall"] is None
    assert agg["n_contraindication_recall"] == 0


def test_aggregate_breaks_down_by_level():
    a = scoring.score_case(_output(), _label(), _profile(), case_id="a", level="simple")
    b = scoring.score_case(_output(decision="lifestyle_only"), _label(), _profile(),
                           case_id="b", level="hard")
    by = scoring.aggregate_by_level([a, b])
    assert by["simple"]["decision_concordance"] == 1.0
    assert by["hard"]["decision_concordance"] == 0.0


def test_aggregate_of_nothing_does_not_divide_by_zero():
    agg = scoring.aggregate([])
    assert agg["n_cases"] == 0
    assert agg["decision_concordance"] is None


# --- acceptance: hand-scored gold set ----------------------------------------
def test_reproduces_the_hand_scored_gold_set():
    """HC-70 acceptance criterion.

    Five cases scored by hand, covering the branches most likely to be defined wrongly:
    a perfect answer, a right-answer/wrong-path trace, an unsafe recommendation that
    still gets the decision right, an over-abstention, and a hallucinated citation.
    """
    cases = [
        # 1. perfect
        (_output(), _label(), _profile()),
        # 2. right answer, wrong path (steps reversed)
        (_output(trace=[{"rule": "initiation", "detail": "", "citation": None},
                        {"rule": "bp_staging", "detail": "", "citation": None}]),
         _label(), _profile()),
        # 3. right decision, contraindicated class
        (_output(recommendation={"drug_classes": ["acei"], "rationale": None}),
         _label(), _profile(contraindications=["hyperkalemia"], potassium=5.9)),
        # 4. over-abstention
        (_output(decision="abstain", abstain_reason="unsure"), _label(), _profile()),
        # 5. hallucinated citation
        (_output(citations=["AHA-ACC-2025:not-a-real-anchor"]), _label(), _profile()),
    ]
    scored = [scoring.score_case(o, l, p, case_id=f"g{i}", level="moderate")
              for i, (o, l, p) in enumerate(cases)]

    # Hand-scored expectations, per case.
    assert [s.decision_concordance for s in scored] == [True, True, True, False, True]
    assert [s.unsafe_recommendation for s in scored] == [False, False, True, False, False]
    assert scored[1].trace_concordance < 1.0            # wrong path
    assert scored[1].decision_concordance is True       # but right answer
    assert scored[3].abstention_cell == "over_abstention"
    assert list(scored[4].citations_hallucinated) == ["AHA-ACC-2025:not-a-real-anchor"]

    agg = scoring.aggregate(scored)
    assert agg["n_cases"] == 5
    assert agg["decision_concordance"] == pytest.approx(4 / 5)
    assert agg["unsafe_recommendation_rate"] == pytest.approx(1 / 5)
    assert agg["citation_hallucination_rate"] == pytest.approx(1 / 5)
