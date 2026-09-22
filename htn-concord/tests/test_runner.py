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
    # `reasoning_tokens` is 0 on this arm rather than absent: Anthropic counts
    # thinking tokens inside `output_tokens` and does not break them out, so the
    # field is present-and-zero to keep one transcript shape across providers.
    assert result.transcript["usage"] == {
        "input_tokens": 11, "output_tokens": 22, "reasoning_tokens": 0}


# ---------------------------------------------------------------------------
# HC-61 — the shapes and outcomes a real API call actually produces.
#
# Still hermetic. These pin behaviour that only became observable once the SDK
# was installed and the live shape was checked against the claude-api reference:
# adaptive thinking, thinking blocks in the response, refusal as its own
# outcome, and truncation as its own outcome.
# ---------------------------------------------------------------------------

class _FakeThinkingBlock:
    type = "thinking"
    thinking = "Let me stage the blood pressure first."


def _fake_client(text, *, stop_reason="end_turn", stop_details=None,
                 extra_blocks=()):
    class _Msg:
        model = "claude-opus-5"

        def __init__(self):
            self.content = [*extra_blocks, _FakeBlock(text)]
            self.stop_reason = stop_reason
            self.stop_details = stop_details
            self.usage = _FakeUsage()

    class _Messages:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return _Msg()

    class _Client:
        def __init__(self):
            self.messages = _Messages()

    return _Client()


def test_anthropic_provider_sends_adaptive_thinking():
    """Guideline reasoning is exactly the work thinking exists for.

    It is also a benchmark variable, so it is pinned and recorded rather than
    left to whatever the model defaults to this month.
    """
    from runner import AnthropicProvider

    client = _fake_client(_valid_json_text())
    run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
             provider=AnthropicProvider(client=client))
    assert client.messages.kwargs["thinking"] == {"type": "adaptive"}


def test_anthropic_provider_does_not_enable_server_side_fallbacks():
    """A server-side fallback silently answers as a *different model*.

    Model identity is a crossed factor in this design and is recorded per call,
    so a benchmark that lets the server substitute a model on refusal is
    reporting a number it cannot attribute. Never enable it here.
    """
    from runner import AnthropicProvider

    client = _fake_client(_valid_json_text())
    run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
             provider=AnthropicProvider(client=client))
    for banned in ("fallbacks", "betas", "speed"):
        assert banned not in client.messages.kwargs


def test_thinking_blocks_never_reach_the_json_parser():
    from runner import AnthropicProvider

    client = _fake_client(_valid_json_text(), extra_blocks=(_FakeThinkingBlock(),))
    result = run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
                      provider=AnthropicProvider(client=client))
    assert result.output["decision"]
    assert "Let me stage" not in result.transcript["response"]["raw_text"]


def test_default_max_tokens_leaves_room_for_thinking():
    """4096 was set before thinking was on by default.

    Thinking tokens count against `max_tokens`, so a low ceiling truncates the
    JSON and the truncation would be counted as a malformed-output rate — the
    one number HC-61 exists to measure. Inflating that number with our own
    configuration error would be worse than not measuring it.
    """
    import inspect

    from runner.run_case import run_case as rc
    assert inspect.signature(rc).parameters["max_tokens"].default >= 16000


def test_refusal_is_its_own_outcome_not_malformed_json():
    """A refusal is a result, not a parse failure.

    Counting a declined clinical question as "malformed JSON" would report a
    model that answered nothing as a model with a formatting problem, and would
    hide a finding that matters on a clinical benchmark.
    """
    from runner import AnthropicProvider, RefusalError

    client = _fake_client("", stop_reason="refusal",
                          stop_details={"type": "refusal", "category": "medical",
                                        "explanation": "declined"})
    with pytest.raises(RefusalError) as exc:
        run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
                 provider=AnthropicProvider(client=client))
    assert exc.value.category == "medical"


def test_a_refusal_is_not_retried():
    """Retrying a refusal spends money to get the same answer."""
    from runner import AnthropicProvider, RefusalError

    client = _fake_client("", stop_reason="refusal",
                          stop_details={"type": "refusal", "category": "medical"})
    calls = []
    original = client.messages.create

    def counting(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    client.messages.create = counting
    with pytest.raises(RefusalError):
        run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
                 provider=AnthropicProvider(client=client), max_attempts=3)
    assert len(calls) == 1


def test_truncation_is_reported_as_truncation_not_as_bad_json():
    """`stop_reason == "max_tokens"` means our ceiling was too low.

    That is our defect, not the model's formatting, and the pilot has to be able
    to tell the two apart.
    """
    from runner import TruncatedOutputError

    truncated = _valid_json_text()[:80]
    provider = ScriptedProvider([truncated] * 3)
    provider.stop_reason = "max_tokens"
    with pytest.raises(TruncatedOutputError):
        run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
                 provider=provider, max_attempts=3)


def test_attempt_outcomes_are_classified_for_the_failure_mode_table():
    """The pilot reports failure modes, so every attempt carries a tag."""
    valid = _valid_json_text()
    provider = ScriptedProvider(["not json at all", valid])
    result = run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
                      provider=provider)
    outcomes = [a["outcome"] for a in result.transcript["attempt_log"]]
    assert outcomes == ["invalid_json", "ok"]


def test_schema_violation_is_tagged_separately_from_invalid_json():
    bad = json.dumps({"schema_version": "1.0", "decision": "abstain"})
    provider = ScriptedProvider([bad, _valid_json_text()])
    result = run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert [a["outcome"] for a in result.transcript["attempt_log"]] == [
        "schema_violation", "ok"]


def test_transcript_records_the_pinned_inference_parameters():
    """`effort` changes answer quality, so a benchmark must record it.

    There is no temperature/seed to pin (HC-64); this is what stands in for it,
    and a result whose effort is unrecorded is not comparable to anything.
    """
    from runner import AnthropicProvider

    client = _fake_client(_valid_json_text())
    result = run_case(model="claude-opus-5", prompt_input=PROMPT, profile=None,
                      provider=AnthropicProvider(client=client, effort="high"))
    request = result.transcript["request"]
    assert request["effort"] == "high"
    assert request["thinking"] == {"type": "adaptive"}


def test_price_table_covers_the_models_the_pilot_will_run():
    from runner.run_case import _PRICES

    for model in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5",
                  "claude-opus-4-8", "claude-fable-5-1"):
        assert model in _PRICES, f"{model} would record a null cost"


def test_opus_5_cost_matches_published_pricing():
    """$5/MTok in, $25/MTok out."""
    from runner.run_case import _cost_usd

    assert _cost_usd("claude-opus-5", 1_000_000, 0) == pytest.approx(5.0)
    assert _cost_usd("claude-opus-5", 0, 1_000_000) == pytest.approx(25.0)


def test_sonnet_5_cost_matches_published_pricing():
    """Was listed at Sonnet 4.6's price, which would have overstated cost 1.5x."""
    from runner.run_case import _cost_usd

    assert _cost_usd("claude-sonnet-5", 1_000_000, 0) == pytest.approx(2.0)
    assert _cost_usd("claude-sonnet-5", 0, 1_000_000) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# The open-weight arm (HC-61, decision D3)
#
# Hermetic: a fake transport stands in for the network. As with AnthropicProvider,
# these pin the wire shape — they do NOT prove a host accepts it.
# ---------------------------------------------------------------------------

def _fake_transport(payload, captured):
    def transport(url, body, headers, timeout):
        captured.update({"url": url, "body": body, "headers": headers,
                         "timeout": timeout})
        return payload
    return transport


def _chat_payload(text, *, finish_reason="stop", model="openweight-x"):
    return {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": text},
                     "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 45},
    }


def _openweight(text, *, finish_reason="stop", **kwargs):
    from runner.providers import OpenAICompatibleProvider

    captured: dict = {}
    provider = OpenAICompatibleProvider(
        "meta-llama/Example-Model-v1", base_url="https://example.test/v1",
        api_key="k", transport=_fake_transport(
            _chat_payload(text, finish_reason=finish_reason), captured),
        **kwargs)
    return provider, captured


def test_open_weight_provider_sends_the_chat_completions_shape():
    provider, captured = _openweight(_valid_json_text())
    run_case(model="meta-llama/Example-Model-v1", prompt_input=PROMPT,
             profile=None, provider=provider)
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][-1]["content"] == PROMPT
    assert captured["headers"]["Authorization"] == "Bearer k"


def test_open_weight_provider_requests_a_json_schema_by_default():
    provider, captured = _openweight(_valid_json_text())
    run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)
    fmt = captured["body"]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["schema"]["type"] == "object"


def test_open_weight_provider_falls_back_to_json_object_when_asked():
    """Not every host supports json_schema; the local validator is still the
    contract either way."""
    provider, captured = _openweight(_valid_json_text(), structured_outputs=False)
    run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_open_weight_provider_sends_the_api_safe_schema_not_the_full_one():
    provider, captured = _openweight(_valid_json_text())
    run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)
    sent = captured["body"]["response_format"]["json_schema"]["schema"]
    assert "allOf" not in sent
    assert "minItems" not in json.dumps(sent)


def test_open_weight_provider_omits_temperature_unless_it_is_chosen():
    """Open-weight hosts accept temperature, so an unset value means the host's
    default silently applies -- exactly the unrecorded variable HC-64 is about."""
    provider, captured = _openweight(_valid_json_text())
    run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)
    assert "temperature" not in captured["body"]

    provider, captured = _openweight(_valid_json_text(), temperature=0.0)
    run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)
    assert captured["body"]["temperature"] == 0.0


def test_open_weight_finish_reasons_map_onto_the_same_outcome_vocabulary():
    """One chain of outcome handling has to cover both arms, or the pilot's
    failure-mode table would mean different things per model."""
    from runner import RefusalError, TruncatedOutputError

    provider, _ = _openweight("", finish_reason="content_filter")
    with pytest.raises(RefusalError):
        run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)

    provider, _ = _openweight(_valid_json_text()[:40], finish_reason="length")
    with pytest.raises(TruncatedOutputError):
        run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)


def test_open_weight_provider_rejects_an_unknown_host_by_name():
    from runner.providers import OpenAICompatibleProvider

    with pytest.raises(ValueError, match="unknown host"):
        OpenAICompatibleProvider.for_host("nope", "m", api_key="k")


def test_open_weight_provider_records_the_model_the_host_reports():
    """The recorded model must be what answered, not what we asked for."""
    provider, _ = _openweight(_valid_json_text())
    result = run_case(model="requested-name", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.transcript["model"] == "openweight-x"


# ---------------------------------------------------------------------------
# The request copy must not depend on draft-07 spellings the API may not share
# ---------------------------------------------------------------------------

def test_api_safe_schema_inlines_every_ref():
    """`$ref: "#/definitions/..."` is draft-07's spelling; the structured-output
    documentation names `$ref`/`$defs`. Rather than bet the first live call on
    whether `definitions` resolves, the request copy carries no refs at all.
    The full local schema keeps them — it is the contract, and jsonschema
    resolves them itself.
    """
    safe = api_safe_schema(load_output_schema())
    assert "$ref" not in json.dumps(safe)


def test_api_safe_schema_drops_draft_metadata():
    """`$schema`, `$id` and a now-empty `definitions` block are not part of the
    output contract and only give the API more to reject."""
    safe = api_safe_schema(load_output_schema())
    for key in ("$schema", "$id", "definitions"):
        assert key not in safe


def test_inlining_preserves_the_shapes_the_refs_pointed_at():
    """Inlining must not quietly drop the scored structure."""
    safe = api_safe_schema(load_output_schema())
    recommendation = safe["properties"]["recommendation"]
    assert recommendation["type"] == "object"
    assert "drug_classes" in recommendation["properties"]
    assert recommendation["additionalProperties"] is False

    step = safe["properties"]["trace"]["items"]
    assert set(step["properties"]) == {"rule", "detail", "citation"}
    # `citation` is optional in the full schema but required here: strict mode
    # rejects optional properties. See
    # test_api_safe_schema_marks_every_property_required.
    assert set(step["required"]) == {"rule", "detail", "citation"}


def test_the_full_schema_still_uses_refs_and_still_validates():
    """Inlining is a property of the *request copy* only."""
    full = load_output_schema()
    assert "$ref" in json.dumps(full)
    jsonschema.Draft7Validator(full).validate(_valid_output())


# ---------------------------------------------------------------------------
# OpenAI as the FRONTIER arm (2026-09-20, replacing Claude at Aria's request)
#
# Hermetic, as everywhere else. The shapes below come from the installed
# openai==3.16.2 type definitions, not from memory:
#   - `max_tokens` is deprecated and incompatible with reasoning models, so the
#     parameter is `max_completion_tokens`;
#   - `reasoning_effort` is the analogue of Anthropic's `effort` and is the thing
#     this project pins and records in place of an unpinnable temperature;
#   - a structured-output refusal arrives in `message.refusal` with `content`
#     null -- reading only `content` would score a refusal as malformed JSON.
# ---------------------------------------------------------------------------

class _OAIMessage:
    def __init__(self, content=None, refusal=None):
        self.content = content
        self.refusal = refusal


class _OAIChoice:
    def __init__(self, message, finish_reason="stop"):
        self.message = message
        self.finish_reason = finish_reason


class _OAIUsage:
    prompt_tokens = 130
    completion_tokens = 60

    class completion_tokens_details:      # noqa: N801 - mirrors the SDK shape
        reasoning_tokens = 40


class _OAICompletion:
    def __init__(self, message, finish_reason, model):
        self.choices = [_OAIChoice(message, finish_reason)]
        self.usage = _OAIUsage()
        self.model = model


class _OAIClient:
    def __init__(self, message, finish_reason="stop", model="gpt-6-astra"):
        self.kwargs = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.kwargs = kwargs
                return _OAICompletion(message, finish_reason, model)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def _openai_provider(message, *, finish_reason="stop", model="gpt-6-astra", **kw):
    from runner import OpenAIProvider

    client = _OAIClient(message, finish_reason, model)
    return OpenAIProvider(client=client, **kw), client


def test_openai_provider_sends_max_completion_tokens_not_max_tokens():
    """`max_tokens` is deprecated and rejected by reasoning models. Sending it
    would fail the first live call, and gpt-6-astra is a reasoning model."""
    provider, client = _openai_provider(_OAIMessage(_valid_json_text()))
    run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
             provider=provider, max_tokens=16000)
    assert client.kwargs["max_completion_tokens"] == 16000
    assert "max_tokens" not in client.kwargs


def test_openai_provider_pins_and_sends_reasoning_effort():
    provider, client = _openai_provider(_OAIMessage(_valid_json_text()),
                                        effort="high")
    run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
             provider=provider)
    assert client.kwargs["reasoning_effort"] == "high"


def test_openai_provider_sends_a_strict_json_schema():
    provider, client = _openai_provider(_OAIMessage(_valid_json_text()))
    run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
             provider=provider)
    fmt = client.kwargs["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert "$ref" not in json.dumps(fmt["json_schema"]["schema"])


def test_openai_provider_sends_no_sampling_parameters():
    """Same position as the Anthropic arm (HC-64): reproducibility rests on the
    transcript, not on sampling control, and an unsent parameter cannot be an
    unrecorded one."""
    provider, client = _openai_provider(_OAIMessage(_valid_json_text()))
    run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
             provider=provider)
    for banned in ("temperature", "top_p", "seed", "verbosity"):
        assert banned not in client.kwargs


def test_openai_structured_output_refusal_is_a_refusal_not_bad_json():
    """The trap unique to this API: on a refusal `content` is null and the text
    lands in `message.refusal`. Reading only `content` yields an empty string,
    which parses as malformed JSON -- scoring a declined clinical question as a
    formatting failure."""
    from runner import RefusalError

    provider, _ = _openai_provider(
        _OAIMessage(None, refusal="I can't help with treatment decisions."))
    with pytest.raises(RefusalError) as exc:
        run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
                 provider=provider)
    assert "treatment decisions" in str(exc.value)


def test_openai_content_filter_is_also_a_refusal():
    from runner import RefusalError

    provider, _ = _openai_provider(_OAIMessage(""), finish_reason="content_filter")
    with pytest.raises(RefusalError):
        run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
                 provider=provider)


def test_openai_length_finish_reason_is_truncation():
    from runner import TruncatedOutputError

    provider, _ = _openai_provider(_OAIMessage(_valid_json_text()[:40]),
                                   finish_reason="length")
    with pytest.raises(TruncatedOutputError):
        run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
                 provider=provider)


def test_openai_reasoning_tokens_are_recorded():
    """Reasoning tokens are billed as output and are the analogue of thinking
    tokens; a cost that ignores them understates the run."""
    provider, _ = _openai_provider(_OAIMessage(_valid_json_text()))
    result = run_case(model="gpt-6-astra", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.transcript["usage"]["reasoning_tokens"] == 40


def test_openai_frontier_models_are_priced():
    from runner.run_case import _PRICES

    for model in ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.5"):
        assert model in _PRICES, f"{model} would record a null cost"


def test_gpt_6_astra_cost_matches_published_pricing():
    """$10/MTok in, $50/MTok out (short-context tier)."""
    from runner.run_case import _cost_usd

    assert _cost_usd("gpt-6-astra", 1_000_000, 0) == pytest.approx(10.0)
    assert _cost_usd("gpt-6-astra", 0, 1_000_000) == pytest.approx(50.0)


def test_openai_provider_records_the_model_the_api_reports():
    provider, _ = _openai_provider(_OAIMessage(_valid_json_text()),
                                   model="gpt-6-astra")
    result = run_case(model="requested", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.transcript["model"] == "gpt-6-astra"


# ---------------------------------------------------------------------------
# Groq + openai/gpt-oss-120b as the open-weight arm (2026-09-22)
#
# Three requirements taken from the host's own documentation, each of which
# would have broken or silently degraded the first live call.
# ---------------------------------------------------------------------------

def _all_objects(node):
    """Every object schema in the tree, for the strict-mode checks below."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            yield node
        for value in node.values():
            yield from _all_objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _all_objects(value)


def test_api_safe_schema_marks_every_property_required():
    """Strict structured outputs requires *all* properties to be in `required`.

    `TraceStep.citation` is optional in the full schema, so the request copy
    would have been rejected. The documented workaround for an optional field is
    a nullable union, which `citation` already is -- so requiring it costs
    nothing and the full local schema, which still treats it as optional, remains
    the contract.
    """
    safe = api_safe_schema(load_output_schema())
    for obj in _all_objects(safe):
        assert set(obj["required"]) == set(obj["properties"]), (
            f"{sorted(set(obj['properties']) - set(obj.get('required', [])))} "
            "not marked required; strict mode rejects this")


def test_every_object_in_the_request_copy_is_closed():
    """The other strict-mode requirement: additionalProperties false everywhere."""
    safe = api_safe_schema(load_output_schema())
    for obj in _all_objects(safe):
        assert obj.get("additionalProperties") is False


def test_requiring_citation_does_not_change_what_validates_locally():
    """A trace step that omits `citation` must still pass the full schema."""
    output = _valid_output()
    output["trace"] = [{"rule": "bp_staging", "detail": "staged"}]
    jsonschema.Draft7Validator(load_output_schema()).validate(output)

    output["trace"] = [{"rule": "bp_staging", "detail": "staged", "citation": None}]
    jsonschema.Draft7Validator(load_output_schema()).validate(output)


def test_open_weight_provider_sends_max_completion_tokens():
    """Groq documents `max_completion_tokens`, not the deprecated `max_tokens`."""
    provider, captured = _openweight(_valid_json_text())
    run_case(model="openai/gpt-oss-120b", prompt_input=PROMPT, profile=None,
             provider=provider, max_tokens=16000)
    assert captured["body"]["max_completion_tokens"] == 16000
    assert "max_tokens" not in captured["body"]


def test_open_weight_provider_pins_reasoning_effort_when_given():
    """gpt-oss is a reasoning model. Leaving effort unset would mean the
    open-weight arm ran at the host's default while the frontier arm ran at a
    pinned one -- an unrecorded variable across the two arms being compared."""
    provider, captured = _openweight(_valid_json_text(), effort="high")
    run_case(model="openai/gpt-oss-120b", prompt_input=PROMPT, profile=None,
             provider=provider)
    assert captured["body"]["reasoning_effort"] == "high"


def test_open_weight_provider_omits_reasoning_effort_when_not_set():
    """Hosts serving non-reasoning models reject the parameter."""
    provider, captured = _openweight(_valid_json_text(), effort=None)
    run_case(model="m", prompt_input=PROMPT, profile=None, provider=provider)
    assert "reasoning_effort" not in captured["body"]


def test_groq_is_a_known_host():
    from runner.providers import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider.for_host(
        "groq", "openai/gpt-oss-120b", api_key="k")
    assert provider.base_url.endswith("/openai/v1")


def test_open_weight_model_is_priced():
    """The pilot reports cost; the first live call recorded `None` because this
    model was absent from the table."""
    from runner.run_case import _cost_usd

    assert _cost_usd("openai/gpt-oss-120b", 1_000_000, 0) == pytest.approx(0.15)
    assert _cost_usd("openai/gpt-oss-120b", 0, 1_000_000) == pytest.approx(0.60)


def test_open_weight_provider_records_reasoning_tokens_when_offered():
    from runner.providers import OpenAICompatibleProvider

    captured: dict = {}
    payload = _chat_payload(_valid_json_text())
    payload["usage"]["completion_tokens_details"] = {"reasoning_tokens": 2600}
    provider = OpenAICompatibleProvider(
        "m", base_url="https://x.test/v1", api_key="k",
        transport=_fake_transport(payload, captured))
    result = run_case(model="m", prompt_input=PROMPT, profile=None,
                      provider=provider)
    assert result.transcript["usage"]["reasoning_tokens"] == 2600


# ---------------------------------------------------------------------------
# The two-schema design's standing obligation
# ---------------------------------------------------------------------------

def test_every_stripped_constraint_is_stated_in_the_prompt():
    """A constraint we strip from the request but still enforce locally is a
    hidden rule unless the prompt restates it.

    Found live: `trace` carries `minItems: 1`, which structured outputs rejects,
    so it was stripped -- and the system prompt never mentioned `trace` at all.
    Two models happened to comply; a third returned `trace: []` on all three
    attempts and scored as malformed output for breaking a rule it was never
    given. That measures guessing, not guideline concordance.
    """
    from runner.run_case import DEFAULT_SYSTEM

    full = load_output_schema()

    def non_empty_arrays(node, path=()):
        if isinstance(node, dict):
            if node.get("type") == "array" and node.get("minItems", 0) >= 1:
                yield path[-1] if path else "<root>"
            for key, value in node.items():
                yield from non_empty_arrays(value, path + (key,))
        elif isinstance(node, list):
            for value in node:
                yield from non_empty_arrays(value, path)

    required_non_empty = set(non_empty_arrays(full))
    assert required_non_empty, "fixture assumption: some array requires minItems"
    for field in required_non_empty:
        assert field in DEFAULT_SYSTEM, (
            f"{field!r} must be non-empty per the full schema, but the API copy "
            "cannot say so and the prompt never mentions it")


def test_the_conditional_abstain_rule_is_stated_in_the_prompt():
    """The other stripped rule: abstain_reason required exactly on abstain."""
    from runner.run_case import DEFAULT_SYSTEM

    assert "abstain_reason" in DEFAULT_SYSTEM
    assert "null otherwise" in DEFAULT_SYSTEM


def test_an_empty_trace_is_still_rejected_locally():
    """Stating the rule in the prompt does not relax the contract."""
    bad = _valid_output()
    bad["trace"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(load_output_schema()).validate(bad)


def test_the_open_weight_arm_model_is_priced():
    """The first DeepSeek call recorded a null cost; the pilot reports cost."""
    from runner.run_case import _cost_usd

    assert _cost_usd("deepseek-ai/DeepSeek-V4-Pro-0813", 1_000_000, 0) == pytest.approx(1.32)
    assert _cost_usd("deepseek-ai/DeepSeek-V4-Pro-0813", 0, 1_000_000) == pytest.approx(3.96)


def test_prompt_states_the_averaging_convention_the_renderer_relies_on():
    """HC-101: `hard` states the individual BP readings and never their average.

    The evaluator scores `sbp`/`dbp` against the mean of those readings
    (`renderer.display_bp` of the profile value, which the readings are built to
    average to exactly). So "report the mean of multiple readings" is a rule the
    model is judged against -- and the prompt otherwise pushes the other way,
    telling it to use null for anything "not stated", which the average
    literally is not.

    Left undisclosed, a level-over-level extraction drop would measure whether
    the model can guess our summary convention rather than whether it can read.
    That is exactly the HC-100 defect -- scoring against a vocabulary never
    given -- reappearing in a new place, and the same reason `trace` had to be
    spelled out after the prompt-v0 retirement.
    """
    from renderer import render
    from runner.run_case import DEFAULT_SYSTEM

    profile = {
        "SEQN": "12345", "age": 68.0, "sex": "female", "sbp": 154.0, "dbp": 91.0,
        "bp_context": "chronic", "bp_n_readings": 3.0, "potassium": 4.8,
        "on_bp_meds": True, "med_classes": ["dhp_ccb"], "contraindications": [],
    }
    text = render(profile, "hard", seed=5)
    assert "154/91" not in text, "fixture assumption: hard withholds the average"

    lowered = DEFAULT_SYSTEM.lower()
    assert "average" in lowered or "mean" in lowered, (
        "the renderer can state several readings without their average, so the "
        "prompt must say which number to report")
    assert "reading" in lowered, "the convention must name what it applies to"


def test_openai_provider_call_timeout_is_overridable_and_defaults_unchanged(monkeypatch):
    """HC-103: the per-call ceiling has to be settable without editing code.

    The 900s client timeout is deliberate and documented, but `run_pilot` wraps
    each call in `api_retries=3`, so the *effective* ceiling is ~45 minutes --
    which is what a hung socket actually cost during the HC-101 measurement:
    two stalls, 3h14m and 73m, both silent. Each layer is reasonable alone;
    nobody multiplied them.

    Lowering it is a transport decision, not a model one. A timed-out call
    writes no record and the resume refills it, so nothing about what a model
    answered depends on this number. The default stays where it was so an
    unset environment behaves exactly as before.
    """
    import importlib

    import runner.providers as providers
    importlib.reload(providers)
    assert providers.DEFAULT_CALL_TIMEOUT == 900.0, "default must not move silently"

    monkeypatch.setenv("PILOT_CALL_TIMEOUT", "180")
    importlib.reload(providers)
    assert providers.DEFAULT_CALL_TIMEOUT == 180.0

    monkeypatch.delenv("PILOT_CALL_TIMEOUT")
    importlib.reload(providers)
    assert providers.DEFAULT_CALL_TIMEOUT == 900.0
