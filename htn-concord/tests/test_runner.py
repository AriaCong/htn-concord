"""JSON-mode model runner (HC-60).

Every test here is hermetic: the runner takes a Provider, and these use scripted
fakes, so the suite never needs an API key or a network call. That is deliberate —
the runner is the only stage that touches an LLM, so it is also the only stage that
could make CI non-deterministic.
"""
import json
from pathlib import Path

import jsonschema
import pytest

from runner import (
    MalformedOutputError,
    ProviderResponse,
    ReplayProvider,
    ScriptedProvider,
    api_safe_schema,
    load_output_schema,
    replay,
    run_case,
)

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE = _ROOT / "schemas" / "examples" / "llm_output.example.json"


def _valid_output() -> dict:
    return json.loads(_EXAMPLE.read_text())


def _valid_json_text() -> str:
    return json.dumps(_valid_output())


PROMPT = "A 68-year-old woman attends a routine visit. Recent readings were 156/92..."


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_run_case_returns_parsed_output():
    provider = ScriptedProvider([_valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.output == _valid_output()
    assert result.attempts == 1
    assert result.malformed_attempts == 0


def test_run_case_records_model_and_prompt_hash():
    provider = ScriptedProvider([_valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.transcript["model"] == "claude-opus-4-8"
    assert len(result.transcript["prompt"]["prompt_sha256"]) == 64


def test_run_case_captures_latency_and_usage():
    provider = ScriptedProvider([_valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.transcript["latency_ms"] >= 0
    assert result.transcript["usage"]["input_tokens"] == 100
    assert result.transcript["usage"]["output_tokens"] == 50


def test_cost_is_computed_from_the_price_table():
    provider = ScriptedProvider([_valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider)
    # opus-4-8: $5/MTok in, $25/MTok out -> 100*5e-6 + 50*25e-6
    assert result.transcript["cost_usd"] == pytest.approx(100 * 5e-6 + 50 * 25e-6)


def test_unknown_model_records_null_cost_rather_than_guessing():
    provider = ScriptedProvider([_valid_json_text()])
    result = run_case(model="some-open-weight-model", prompt_input=PROMPT,
                      profile=None, provider=provider)
    assert result.transcript["cost_usd"] is None


# ---------------------------------------------------------------------------
# Malformed JSON: retry, then fail loudly
# ---------------------------------------------------------------------------

def test_malformed_json_is_retried_then_succeeds():
    provider = ScriptedProvider(["not json at all", _valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider, max_attempts=2)
    assert result.output == _valid_output()
    assert result.attempts == 2
    assert result.malformed_attempts == 1


def test_schema_violation_is_retried():
    bad = _valid_output()
    bad["decision"] = "start_two_drugs"  # not in the Decision enum
    provider = ScriptedProvider([json.dumps(bad), _valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider, max_attempts=2)
    assert result.attempts == 2


def test_exhausted_retries_raise_with_the_raw_text_attached():
    provider = ScriptedProvider(["nope", "still nope"])
    with pytest.raises(MalformedOutputError) as exc:
        run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                 provider=provider, max_attempts=2)
    assert "still nope" in exc.value.raw_text
    assert exc.value.attempts == 2


def test_fenced_json_is_recovered():
    """Models sometimes wrap JSON in a markdown fence even in JSON mode."""
    provider = ScriptedProvider([f"```json\n{_valid_json_text()}\n```"])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.output == _valid_output()
    assert result.malformed_attempts == 0


# ---------------------------------------------------------------------------
# API-safe schema derivation
# ---------------------------------------------------------------------------

def test_api_safe_schema_strips_unsupported_keywords():
    """Structured outputs rejects if/then, numeric and length constraints. They
    must be stripped from the request copy but kept in the local contract."""
    safe = api_safe_schema(load_output_schema())
    blob = json.dumps(safe)
    for keyword in ("\"if\"", "\"then\"", "\"else\"", "allOf",
                    "minimum", "maximum", "minItems", "minLength"):
        assert keyword not in blob, f"{keyword} survived into the API schema"


def test_api_safe_schema_keeps_the_scored_structure():
    safe = api_safe_schema(load_output_schema())
    assert safe["additionalProperties"] is False
    assert set(safe["properties"]["decision"]["enum"]) == {
        "initiate_pharmacotherapy", "intensify_pharmacotherapy",
        "lifestyle_only", "at_goal_continue", "abstain",
    }
    assert "trace" in safe["required"]


def test_api_safe_schema_is_still_valid_draft7():
    jsonschema.Draft7Validator.check_schema(api_safe_schema(load_output_schema()))


def test_local_validation_still_enforces_the_stripped_rules():
    """The whole point of stripping: the API can't enforce abstain_reason, so the
    runner must. A model answer the API would accept still fails locally."""
    bad = _valid_output()
    bad["decision"] = "abstain"
    bad["abstain_reason"] = None
    provider = ScriptedProvider([json.dumps(bad), _valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider, max_attempts=2)
    assert result.attempts == 2


# ---------------------------------------------------------------------------
# Deterministic replay — the HC-60 acceptance gate
# ---------------------------------------------------------------------------

def test_replay_reproduces_the_stored_transcript():
    provider = ScriptedProvider([_valid_json_text()])
    original = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                        provider=provider)
    assert replay(original.transcript) == original.output


def test_replay_detects_a_tampered_transcript():
    provider = ScriptedProvider([_valid_json_text()])
    original = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                        provider=provider)
    tampered = json.loads(json.dumps(original.transcript))
    tampered["response"]["raw_text"] = json.dumps({"decision": "lifestyle_only"})
    with pytest.raises(MalformedOutputError):
        replay(tampered)


def test_replay_provider_reruns_the_pipeline_without_a_network_call():
    live = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                    provider=ScriptedProvider([_valid_json_text()]))
    rerun = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                     provider=ReplayProvider(live.transcript))
    assert rerun.output == live.output
    assert rerun.transcript["prompt"]["prompt_sha256"] == live.transcript["prompt"]["prompt_sha256"]


def test_replay_provider_refuses_a_different_prompt():
    """Replay must not silently serve a stored answer for a prompt that changed."""
    live = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                    provider=ScriptedProvider([_valid_json_text()]))
    with pytest.raises(ValueError, match="prompt"):
        run_case(model="claude-opus-4-8", prompt_input="a different vignette",
                 profile=None, provider=ReplayProvider(live.transcript))


# ---------------------------------------------------------------------------
# Profile linkage (hidden label never reaches the model)
# ---------------------------------------------------------------------------

def test_profile_is_recorded_but_never_sent_to_the_model():
    profile = {"source": "nhanes", "seqn": 12345, "bp_stage": "stage2"}
    provider = ScriptedProvider([_valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=profile,
                      provider=provider, case_id="nhanes-12345")
    assert result.transcript["case_id"] == "nhanes-12345"
    assert result.transcript["profile_sha256"] is not None
    sent = provider.calls[0]
    assert "12345" not in sent.user
    assert "stage2" not in sent.user
    assert "stage2" not in (sent.system or "")


def test_no_profile_means_no_profile_hash():
    provider = ScriptedProvider([_valid_json_text()])
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.transcript["profile_sha256"] is None


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------

def test_provider_receives_the_api_safe_schema():
    provider = ScriptedProvider([_valid_json_text()])
    run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
             provider=provider)
    sent_schema = provider.calls[0].output_schema
    assert "allOf" not in json.dumps(sent_schema)
    assert sent_schema["properties"]["decision"]["enum"]


def test_scripted_provider_exhaustion_is_an_explicit_error():
    provider = ScriptedProvider([])
    with pytest.raises(RuntimeError, match="exhausted"):
        run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                 provider=provider)


def test_provider_response_usage_defaults_are_zero():
    resp = ProviderResponse(text="{}", model="m")
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0


# ---------------------------------------------------------------------------
# AnthropicProvider request shape
#
# These pin the wire shape against a mock client. They do NOT prove the API
# accepts it — that needs a live credentialed call (see the runner README).
# ---------------------------------------------------------------------------

class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeUsage:
    input_tokens = 11
    output_tokens = 22


class _FakeMessage:
    model = "claude-opus-4-8"
    stop_reason = "end_turn"
    usage = _FakeUsage()

    def __init__(self, text):
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeMessage(self._text)


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def _anthropic_kwargs():
    from runner import AnthropicProvider

    client = _FakeClient(_valid_json_text())
    provider = AnthropicProvider(client=client)
    run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
             provider=provider)
    return client.messages.kwargs


def test_anthropic_provider_sends_json_schema_output_config():
    kwargs = _anthropic_kwargs()
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["output_config"]["effort"] == "high"


def test_anthropic_provider_sends_no_sampling_parameters():
    """temperature/top_p/top_k are rejected (400) on current frontier models —
    HC-61. Determinism comes from transcript replay, not sampling control."""
    kwargs = _anthropic_kwargs()
    for banned in ("temperature", "top_p", "top_k", "seed"):
        assert banned not in kwargs


def test_anthropic_provider_reports_real_usage():
    from runner import AnthropicProvider

    client = _FakeClient(_valid_json_text())
    result = run_case(model="claude-opus-4-8", prompt_input=PROMPT, profile=None,
                      provider=AnthropicProvider(client=client))
    assert result.transcript["usage"] == {"input_tokens": 11, "output_tokens": 22}
