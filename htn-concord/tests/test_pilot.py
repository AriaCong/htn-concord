"""HC-80 pilot harness and its pre-registered kill criteria.

Hermetic: every "model call" here is a ScriptedProvider, so the suite never
needs a key or a network. The criteria are tested by constructing the summaries
that should and should not trip each one — the point of putting the thresholds
in code is that they can be tested before any real number exists.
"""
from __future__ import annotations

import json

import pytest

from experiments import kill_criteria as kc
from experiments.pilot import (
    CallRecord,
    PilotSpec,
    iter_planned_calls,
    load_records,
    run_pilot,
    select_patients,
    summarize,
)
from runner import ScriptedProvider
from tasks import task_b


@pytest.fixture
def corpus(tmp_path):
    profiles = []
    for i in range(40):
        profiles.append({
            "SEQN": str(5000 + i), "source": "nhanes", "age": 40.0 + (i % 30),
            "sex": "female" if i % 2 else "male",
            "sbp": 108.0 + 3 * (i % 15), "dbp": 60.0 + 2 * (i % 12),
            "bp_context": "chronic", "bp_n_readings": 3.0, "creatinine": 1.0,
            "egfr": 70.0, "potassium": 4.2, "uacr": 10.0, "ckd_albuminuria": False,
            "diabetes": i % 3 == 0, "clinical_cvd": None, "hba1c": 5.5,
            "total_chol": 180.0, "hdl": 50.0, "bmi": 27.0, "current_smoker": False,
            "told_hypertension": True, "on_bp_meds": i % 2 == 0,
            "med_classes": ["acei"] if i % 2 == 0 else [], "statin_use": False,
            "prevent_10yr": 5.0, "contraindications": [],
        })
    task_b.build(profiles, tmp_path, seed=1)
    return tmp_path, {p["SEQN"]: p for p in profiles}


def _valid_output(decision="lifestyle_only"):
    return {
        "schema_version": "1.0", "bp_stage": "stage1", "decision": decision,
        "abstain_reason": None,
        "extracted": {"age": 50.0, "sex": "male", "sbp": 130.0, "dbp": 80.0,
                      "on_bp_meds": False, "med_classes": [], "diabetes": False,
                      "ckd_albuminuria": False, "clinical_cvd": None,
                      "egfr": 70.0, "potassium": 4.2, "contraindications": []},
        "recommendation": {"drug_classes": [], "rationale": "x"},
        "citations": ["AHA-ACC-2025:stage1-lowrisk-lifestyle"],
        "trace": [{"rule": "bp_staging", "detail": "staged", "citation": None}],
    }


def _spec(**over):
    base = dict(models=("model-a", "model-b"), n_patients=4, replicates=2, split="test")
    base.update(over)
    return PilotSpec(**base)


# ---------------------------------------------------------------------------
# Sampling and planning
# ---------------------------------------------------------------------------

def test_selection_is_deterministic(corpus):
    corpus_dir, _ = corpus
    spec = _spec()
    assert select_patients(corpus_dir, spec) == select_patients(corpus_dir, spec)


def test_selection_is_stratified_rather_than_uniform(corpus):
    """The test split is dominated by one class; a uniform draw of 20 would be
    mostly `lifestyle_only` and would teach the pilot nothing about the rest."""
    corpus_dir, _ = corpus
    spec = _spec(n_patients=6)
    picked = set(select_patients(corpus_dir, spec))
    labels = [json.loads(l) for l in
              (corpus_dir / task_b.LABELS_FILE).read_text().splitlines() if l]
    decisions = {str(r["patient_id"]): r["decision"] for r in labels
                 if r["case_id"].endswith("-simple")}
    represented = {decisions[p] for p in picked}
    assert len(represented) > 1, "sample collapsed onto a single decision class"


def test_plan_covers_every_level_model_and_replicate(corpus):
    corpus_dir, _ = corpus
    spec = _spec()
    planned = list(iter_planned_calls(corpus_dir, spec))
    assert len(planned) == spec.n_calls
    assert {c["level"] for c in planned} == set(spec.levels)
    assert {c["model"] for c in planned} == set(spec.models)


def test_three_levels_not_one(corpus):
    """The resolved scope. §11 said moderate-only, then stated a kill criterion
    about 'all difficulties' — which one level cannot evaluate."""
    corpus_dir, _ = corpus
    assert PilotSpec(models=("m",)).levels == ("simple", "moderate", "hard")


# ---------------------------------------------------------------------------
# Running, resume, and the anti-leakage guarantee
# ---------------------------------------------------------------------------

def test_run_writes_one_record_per_call_and_scores_them(corpus, tmp_path):
    corpus_dir, profiles = corpus
    spec = _spec()
    out = tmp_path / "pilot.jsonl"
    provider = ScriptedProvider([json.dumps(_valid_output())] * spec.n_calls)
    records = run_pilot(corpus_dir, spec, out, lambda _m: provider, profiles=profiles)
    assert len(records) == spec.n_calls
    assert len(load_records(out)) == spec.n_calls


def test_a_resumed_run_does_not_pay_for_completed_calls_again(corpus, tmp_path):
    corpus_dir, profiles = corpus
    spec = _spec()
    out = tmp_path / "pilot.jsonl"
    first = ScriptedProvider([json.dumps(_valid_output())] * spec.n_calls)
    run_pilot(corpus_dir, spec, out, lambda _m: first, profiles=profiles)

    # An exhausted provider raises if it is asked for even one more response.
    second = ScriptedProvider([])
    resumed = run_pilot(corpus_dir, spec, out, lambda _m: second, profiles=profiles)
    assert resumed == []
    assert len(load_records(out)) == spec.n_calls


def test_the_hidden_profile_never_reaches_the_model(corpus, tmp_path):
    """Master Plan principle 4. The structured row is the label."""
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=2, replicates=1)
    provider = ScriptedProvider([json.dumps(_valid_output())] * spec.n_calls)
    run_pilot(corpus_dir, spec, tmp_path / "p.jsonl", lambda _m: provider,
              profiles=profiles)
    for request in provider.calls:
        blob = json.dumps({"system": request.system, "user": request.user})
        for forbidden in ("prevent_10yr", "bp_stage", "contraindications", "SEQN"):
            assert forbidden not in blob


def test_failures_are_recorded_by_kind_not_dropped(corpus, tmp_path):
    """A model that refuses half the cases is not a model with a high score on
    the other half; the denominator has to keep the refusals."""
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=2, replicates=1)
    provider = ScriptedProvider(["this is not json"] * (spec.n_calls * 3))
    records = run_pilot(corpus_dir, spec, tmp_path / "p.jsonl", lambda _m: provider,
                        profiles=profiles)
    assert {r.outcome for r in records} == {"malformed"}
    summary = summarize(records, corpus_dir, profiles)
    for counts in summary["harness"].values():
        assert counts["malformed_output_rate"] == 1.0


def test_summary_keeps_the_majority_class_baseline_beside_concordance(corpus, tmp_path):
    corpus_dir, profiles = corpus
    spec = _spec()
    provider = ScriptedProvider([json.dumps(_valid_output())] * spec.n_calls)
    records = run_pilot(corpus_dir, spec, tmp_path / "p.jsonl", lambda _m: provider,
                        profiles=profiles)
    summary = summarize(records, corpus_dir, profiles)
    for cell in summary["by_model_level"].values():
        assert cell["majority_class_baseline"] is not None
    for cell in summary["by_model"].values():
        assert cell["majority_class_baseline"] is not None


def test_replicate_sd_is_measured(corpus, tmp_path):
    """Sampling is not pinnable (HC-64), so run-to-run variance is measured and
    reported rather than assumed away."""
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=2, replicates=2)
    responses = []
    for i in range(spec.n_calls):
        responses.append(json.dumps(_valid_output(
            "lifestyle_only" if i % 2 else "initiate_pharmacotherapy")))
    provider = ScriptedProvider(responses)
    records = run_pilot(corpus_dir, spec, tmp_path / "p.jsonl", lambda _m: provider,
                        profiles=profiles)
    summary = summarize(records, corpus_dir, profiles)
    assert summary["replicate_sd"], "no replicate variance was reported"


# ---------------------------------------------------------------------------
# The kill criteria — tested before any real number exists
# ---------------------------------------------------------------------------

MODELS = ("frontier", "openweight")
LEVELS = ("simple", "moderate", "hard")


def _summary(cells, *, harness=None, replicate_sd=None):
    """`cells` maps (model, level) -> (concordance, extraction_f1, baseline)."""
    by_model_level = {}
    for (model, level), (conc, extraction, baseline) in cells.items():
        by_model_level[f"{model}|{level}"] = {
            "decision_concordance": conc, "extraction_f1": extraction,
            "majority_class_baseline": baseline, "n_cases": 20,
        }
    clean = {m: {"attempted": 100, "ok": 100, "refusal": 0, "truncated": 0,
                 "malformed": 0, "malformed_output_rate": 0.0, "refusal_rate": 0.0,
                 "truncation_rate": 0.0} for m in MODELS}
    return {"by_model_level": by_model_level, "by_model": {},
            "harness": harness or clean,
            "replicate_sd": replicate_sd or {m: {"median_sd": 0.0} for m in MODELS},
            "n_records": 600}


def _uniform(conc, extraction=0.9, baseline=0.5):
    return {(m, l): (conc, extraction, baseline) for m in MODELS for l in LEVELS}


def test_a_healthy_pilot_returns_go():
    cells = {}
    for m, offset in zip(MODELS, (0.0, -0.20)):
        for l, drop in zip(LEVELS, (0.0, -0.06, -0.14)):
            cells[(m, l)] = (0.78 + offset + drop, 0.95 + drop, 0.5)
    verdict = kc.evaluate_criteria(_summary(cells), models=MODELS, levels=LEVELS)
    assert verdict.verdict == "GO"
    assert verdict.fired == []


def test_ceiling_plus_flat_ladder_is_a_stop():
    verdict = kc.evaluate_criteria(_summary(_uniform(0.97, extraction=0.99)),
                                   models=MODELS, levels=LEVELS)
    assert verdict.verdict == "STOP"
    assert "K1" in verdict.fired and "K2" in verdict.fired


def test_models_indistinguishable_is_a_stop():
    """§11's 'frontier ≈ open-weight everywhere'."""
    cells = {}
    for m in MODELS:
        for l, drop in zip(LEVELS, (0.0, -0.08, -0.16)):
            cells[(m, l)] = (0.80 + drop, 0.95 + drop, 0.5)
    verdict = kc.evaluate_criteria(_summary(cells), models=MODELS, levels=LEVELS)
    assert verdict.verdict == "STOP"
    assert "K3" in verdict.fired


def test_nothing_beats_the_baseline_is_a_stop_for_the_instrument():
    """K4 — the mirror of K1, which §11 does not list and should."""
    verdict = kc.evaluate_criteria(_summary(_uniform(0.52, baseline=0.515)),
                                   models=MODELS, levels=LEVELS)
    assert verdict.verdict == "STOP"
    assert "K4" in verdict.fired


def test_a_broken_harness_is_fix_first_and_short_circuits_the_corpus_verdict():
    """Numbers from a broken instrument are not evidence, so K1-K4 are not read."""
    harness = {m: {"attempted": 100, "malformed_output_rate": 0.30,
                   "refusal_rate": 0.0, "truncation_rate": 0.0} for m in MODELS}
    verdict = kc.evaluate_criteria(_summary(_uniform(0.97), harness=harness),
                                   models=MODELS, levels=LEVELS)
    assert verdict.verdict == "FIX-FIRST"


def test_refusals_alone_can_trip_the_harness_criterion():
    harness = {m: {"attempted": 100, "malformed_output_rate": 0.0,
                   "refusal_rate": 0.10, "truncation_rate": 0.0} for m in MODELS}
    verdict = kc.evaluate_criteria(_summary(_uniform(0.80), harness=harness),
                                   models=MODELS, levels=LEVELS)
    assert verdict.verdict == "FIX-FIRST"


def test_a_flat_ladder_alone_narrows_rather_than_stops():
    """K2 kills RQ2a/RQ2b, not the whole benchmark — but it must be reported as
    unanswerable rather than quietly dropped."""
    cells = {}
    for m, offset in zip(MODELS, (0.0, -0.25)):
        for l in LEVELS:
            cells[(m, l)] = (0.75 + offset, 0.92, 0.5)
    verdict = kc.evaluate_criteria(_summary(cells), models=MODELS, levels=LEVELS)
    assert verdict.verdict == "GO-NARROWED"
    assert verdict.fired == ["K2"]


def test_high_replicate_variance_reports_but_never_stops():
    sd = {m: {"median_sd": 0.22} for m in MODELS}
    cells = {}
    for m, offset in zip(MODELS, (0.0, -0.20)):
        for l, drop in zip(LEVELS, (0.0, -0.06, -0.14)):
            cells[(m, l)] = (0.78 + offset + drop, 0.95 + drop, 0.5)
    verdict = kc.evaluate_criteria(_summary(cells, replicate_sd=sd),
                                   models=MODELS, levels=LEVELS)
    assert verdict.verdict == "GO"
    assert "K6" in verdict.fired


def test_a_single_arm_cannot_answer_the_question_the_pilot_exists_for():
    cells = {("frontier", l): (0.78, 0.95, 0.5) for l in LEVELS}
    verdict = kc.evaluate_criteria(_summary(cells), models=("frontier",),
                                   levels=LEVELS)
    k3 = next(c for c in verdict.criteria if c.name == "K3")
    assert not k3.fired
    assert "fewer than two model arms" in k3.statement


def test_thresholds_are_the_ones_that_were_signed():
    """Changing one after a pilot call is a protocol deviation, not an edit."""
    assert (kc.CEILING, kc.LADDER_MIN_SPREAD, kc.MODEL_MIN_SEPARATION,
            kc.FLOOR_MARGIN) == (0.90, 0.05, 0.05, 0.05)
    assert (kc.MAX_MALFORMED_RATE, kc.MAX_REFUSAL_RATE, kc.MAX_TRUNCATION_RATE,
            kc.MAX_MEDIAN_REPLICATE_SD) == (0.05, 0.02, 0.01, 0.05)


# ---------------------------------------------------------------------------
# Surviving the network over a 600-call run
# ---------------------------------------------------------------------------

class _FlakyProvider:
    """Raises a transport-level error for the first `fails` calls of each case."""
    name = "flaky"

    def __init__(self, payload, fails=0, always=False):
        self.payload = payload
        self.fails = fails
        self.always = always
        self.calls = 0

    def complete(self, request):
        from runner.providers import ProviderResponse

        self.calls += 1
        if self.always or self.calls <= self.fails:
            raise RuntimeError("503 Service Unavailable")
        return ProviderResponse(text=self.payload, model=request.model,
                                input_tokens=10, output_tokens=10,
                                stop_reason="end_turn")


def test_a_transient_api_error_is_retried_rather_than_killing_the_run(corpus, tmp_path):
    """A 429 or 5xx mid-run used to propagate and end a multi-hour run.

    The three outcome errors are model behaviour; a transport failure is not,
    and it must not be recorded as one either.
    """
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=2, replicates=1)
    provider = _FlakyProvider(json.dumps(_valid_output()), fails=2)
    records = run_pilot(corpus_dir, spec, tmp_path / "p.jsonl",
                        lambda _m: provider, profiles=profiles,
                        api_retries=3, sleep=lambda _s: None)
    assert len(records) == spec.n_calls
    assert {r.outcome for r in records} == {"ok"}


def test_a_persistent_api_error_leaves_no_record_so_a_resume_retries_it(
        corpus, tmp_path):
    """Recording an infrastructure failure would bake it in permanently: the
    resume check skips keys already present, so a transient outage would become
    a permanent hole in the denominator. Better to write nothing and let the
    next resume pick it up."""
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=2, replicates=1)
    out = tmp_path / "p.jsonl"
    dead = _FlakyProvider(json.dumps(_valid_output()), always=True)
    failures: list = []
    records = run_pilot(corpus_dir, spec, out, lambda _m: dead,
                        profiles=profiles, api_retries=2,
                        sleep=lambda _s: None,
                        on_error=lambda call, exc: failures.append(call["case_id"]))
    assert records == []
    assert not out.exists() or out.read_text().strip() == ""
    assert len(failures) == spec.n_calls

    # A later resume with a working provider fills every gap.
    good = ScriptedProvider([json.dumps(_valid_output())] * spec.n_calls)
    resumed = run_pilot(corpus_dir, spec, out, lambda _m: good, profiles=profiles)
    assert len(resumed) == spec.n_calls


def test_a_model_level_failure_is_still_recorded_not_retried_as_transport(
        corpus, tmp_path):
    """Malformed output is the model's behaviour and belongs in the denominator."""
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=1, replicates=1)
    provider = ScriptedProvider(["not json"] * (spec.n_calls * 3))
    records = run_pilot(corpus_dir, spec, tmp_path / "p.jsonl",
                        lambda _m: provider, profiles=profiles,
                        api_retries=3, sleep=lambda _s: None)
    assert {r.outcome for r in records} == {"malformed"}


class _RateLimited:
    """Rate-limits the first `n` calls, advising a Retry-After each time."""
    name = "ratelimited"

    def __init__(self, payload, n, retry_after=7.0):
        from runner.providers import TransientHTTPError

        self.payload, self.left, self.retry_after = payload, n, retry_after
        self._exc = TransientHTTPError
        self.waits: list = []

    def complete(self, request):
        from runner.providers import ProviderResponse

        if self.left > 0:
            self.left -= 1
            raise self._exc("429 rate limited", status=429,
                            retry_after=self.retry_after)
        return ProviderResponse(text=self.payload, model=request.model,
                                input_tokens=10, output_tokens=10,
                                stop_reason="end_turn")


def test_a_rate_limit_waits_as_long_as_the_host_advised(corpus, tmp_path):
    """Nearly half the open-weight calls were being dropped to 429s because the
    backoff guessed shorter than the host's own advice."""
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=1, replicates=1)
    provider = _RateLimited(json.dumps(_valid_output()), n=1, retry_after=7.0)
    waits: list[float] = []
    records = run_pilot(corpus_dir, spec, tmp_path / "p.jsonl",
                        lambda _m: provider, profiles=profiles,
                        api_retries=3, sleep=waits.append)
    assert [r.outcome for r in records][:1] == ["ok"]
    assert waits and waits[0] >= 7.0, f"waited {waits}, host advised 7s"


def test_retry_after_is_capped_so_one_bad_header_cannot_stall_the_run(
        corpus, tmp_path):
    corpus_dir, profiles = corpus
    spec = _spec(n_patients=1, replicates=1)
    provider = _RateLimited(json.dumps(_valid_output()), n=1, retry_after=9999.0)
    waits: list[float] = []
    run_pilot(corpus_dir, spec, tmp_path / "p.jsonl", lambda _m: provider,
              profiles=profiles, api_retries=3, sleep=waits.append)
    assert max(waits) <= 120.0
