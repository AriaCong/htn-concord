"""Model providers — the seam between the runner and any actual LLM.

`run_case` depends only on the Provider protocol, so the test suite runs entirely
on ScriptedProvider/ReplayProvider: no API key, no network, no nondeterminism in CI.
AnthropicProvider is the one class that talks to a real model.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol


#: Per-call wall-clock ceiling, in seconds (HC-103).
#:
#: 900s is generous on purpose: a reasoning model at high effort can spend
#: minutes on one case, and a benchmark that gives up early records a timeout
#: where there was an answer. But `run_pilot` wraps each call in
#: `api_retries=3`, so the *effective* ceiling is ~45 minutes, and a hung socket
#: cost 3h14m and then 73m of silent stall during the HC-101 measurement.
#:
#: Overridable so a long run can be tightened without editing code. Lowering it
#: is a transport decision, not a model one: a timed-out call writes no record
#: and the resume refills it, so nothing a model answered depends on this value.
DEFAULT_CALL_TIMEOUT = float(os.environ.get("PILOT_CALL_TIMEOUT", "900"))


@dataclass(frozen=True)
class ProviderRequest:
    """One model call. `output_schema` is the API-safe schema (see run_case)."""
    model: str
    system: str | None
    user: str
    output_schema: Mapping[str, Any]
    max_tokens: int


@dataclass(frozen=True)
class ProviderResponse:
    """Raw model output plus the accounting the transcript needs.

    `stop_reason` is load-bearing, not bookkeeping: it is what separates a model
    that declined to answer (`refusal`) and a reply our own token ceiling cut off
    (`max_tokens`) from a model that genuinely emitted bad JSON. Collapsing the
    three would report all of them as a malformed-output rate.
    """
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    #: Thinking/reasoning tokens. Billed as output and invisible in the reply, so
    #: a cost or a token budget that ignores them understates the run.
    reasoning_tokens: int = 0
    stop_reason: str | None = None
    stop_details: Mapping[str, Any] | None = None


class Provider(Protocol):
    """Anything that can turn a ProviderRequest into a ProviderResponse."""
    name: str

    def complete(self, request: ProviderRequest) -> ProviderResponse: ...


@dataclass
class ScriptedProvider:
    """Returns canned responses in order. The workhorse of the test suite.

    Records every request in `calls` so tests can assert on what was actually sent —
    notably that the hidden PatientProfile never reaches the model.
    """
    responses: list[str]
    name: str = "scripted"
    input_tokens: int = 100
    output_tokens: int = 50
    stop_reason: str = "end_turn"
    stop_details: Mapping[str, Any] | None = None
    calls: list[ProviderRequest] = field(default_factory=list)
    _next: int = 0

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if self._next >= len(self.responses):
            raise RuntimeError(
                f"ScriptedProvider exhausted after {self._next} response(s); "
                "the runner asked for one more than the script provides"
            )
        text = self.responses[self._next]
        self._next += 1
        return ProviderResponse(
            text=text,
            model=request.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            stop_reason=self.stop_reason,
            stop_details=self.stop_details,
        )


@dataclass
class ReplayProvider:
    """Serves the stored response from a transcript instead of calling a model.

    This is what makes an archived run re-runnable end-to-end offline. It refuses
    to serve a stored answer when the prompt has changed, so a reproduction can
    never silently pass against a prompt that was edited after the fact.
    """
    transcript: Mapping[str, Any]
    name: str = "replay"

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        from runner.run_case import _sha256  # local import: avoids a cycle

        stored = self.transcript["prompt"]["prompt_sha256"]
        incoming = _sha256(_prompt_blob(request.system, request.user))
        if stored != incoming:
            raise ValueError(
                "ReplayProvider: prompt does not match the transcript "
                f"(stored {stored[:12]}..., got {incoming[:12]}...). "
                "Replaying a stored response against a changed prompt would be a "
                "fabricated result, not a reproduction."
            )
        usage = self.transcript.get("usage") or {}
        return ProviderResponse(
            text=self.transcript["response"]["raw_text"],
            model=self.transcript["model"],
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            stop_reason=self.transcript["response"].get("stop_reason"),
        )


def _prompt_blob(system: str | None, user: str) -> str:
    """Canonical prompt serialization — the thing that gets hashed."""
    return json.dumps({"system": system, "user": user}, sort_keys=True,
                      ensure_ascii=False)


class AnthropicProvider:
    """Calls a real Claude model in strict JSON mode.

    **Determinism (HC-64).** There is no temperature/top_p/top_k and no seed to
    pin — those parameters are rejected on current frontier models. Run-to-run
    reproducibility comes from the stored transcript (`ReplayProvider`), not from
    sampling control. What *is* pinned and recorded is `effort` and `thinking`:
    both change answer quality, so a benchmark that leaves them to whatever the
    API defaults to this month is not comparing like with like.

    **Thinking is on, deliberately.** Adaptive thinking is what the model uses to
    do the multi-step work this benchmark measures — stage, stratify risk, check
    contraindications, choose. Turning it off would measure a different system.
    It is declared explicitly rather than left to the model default, because the
    default differs between model generations.

    **No server-side refusal fallback, deliberately.** The API can silently
    re-route a refused request to another model. Model identity is a crossed
    factor in this design and is recorded per call, so a substituted answer would
    be a result attributed to the wrong model. A refusal must surface as a
    refusal — see `RefusalError`.
    """

    name = "anthropic"

    DEFAULT_THINKING: Mapping[str, Any] = MappingProxyType({"type": "adaptive"})

    def __init__(self, client: Any = None, effort: str = "high",
                 thinking: Mapping[str, Any] | None = None) -> None:
        if client is None:
            import anthropic  # imported lazily: not needed for tests or CI

            client = anthropic.Anthropic()
        self._client = client
        self.effort = effort
        self.thinking = dict(self.DEFAULT_THINKING if thinking is None else thinking)

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "output_config": {
                "format": {"type": "json_schema", "schema": dict(request.output_schema)},
                "effort": self.effort,
            },
            "thinking": dict(self.thinking),
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.system is not None:
            kwargs["system"] = request.system

        message = self._client.messages.create(**kwargs)

        # Only text blocks. A response may also carry thinking blocks, and feeding
        # those to the JSON parser would turn a good answer into a parse failure.
        text = "".join(b.text for b in message.content
                       if getattr(b, "type", None) == "text")
        usage = getattr(message, "usage", None)
        details = getattr(message, "stop_details", None)
        return ProviderResponse(
            text=text,
            model=getattr(message, "model", request.model),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            stop_reason=getattr(message, "stop_reason", None),
            stop_details=_as_mapping(details),
        )


def _as_mapping(value: Any) -> dict[str, Any] | None:
    """Normalize the SDK's stop_details object (or dict, or None) to a dict."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    for attr in ("model_dump", "to_dict", "dict"):
        dumper = getattr(value, attr, None)
        if callable(dumper):
            try:
                return dict(dumper())
            except Exception:  # pragma: no cover - defensive against SDK drift
                pass
    return {k: v for k, v in vars(value).items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# The open-weight arm (HC-61, decision D3)
# ---------------------------------------------------------------------------

#: Sent on every raw-HTTP request. A benchmark should say what it is.
USER_AGENT = "htn-concord-runner/1.0 (research benchmark)"

#: Hosted endpoints that speak the OpenAI-compatible chat-completions shape.
#: The *provider* is configuration; the *model version* is an experimental
#: variable and must be written out in full, never as a floating alias like
#: "-latest", because a floating alias silently changes what a "same" run ran.
OPENAI_COMPATIBLE_ENDPOINTS: Mapping[str, str] = MappingProxyType({
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
})


class OpenAICompatibleProvider:
    """The second arm: an open-weight model behind an OpenAI-compatible endpoint.

    **Why open weights are the second arm** (decision D3, resolved 2026-09-20).
    The design requires a failure mode to replicate across models before it is
    reported as a finding. That bar needs a second model that is *genuinely
    different* — a different lab, different data, different training — rather than
    a smaller sibling of the first. Open weights add a reproducibility property
    the frontier arm cannot have: the weights can be pinned by version and
    re-run years later, whereas an API model may be withdrawn or silently updated.

    **Raw HTTP on purpose.** The chat-completions wire shape is small, stable and
    identical across the endpoints above; adding a vendor SDK would pin a
    dependency whose surface is not part of the experiment. The request is
    written out in full here so the recorded wire shape *is* the code.

    **Structured-output support varies by host.** `json_schema` is requested when
    `structured_outputs=True` and `json_object` otherwise. Either way the reply is
    validated locally against the full `llm_output.schema.json` — the local
    validator is the contract, exactly as for the Anthropic arm.

    ⚠️ **Never executed against a live endpoint.** Pinned by hermetic test only,
    with no credential available at the time of writing. Treat its malformed-
    output rate as unmeasured until a real call has been made — the same warning
    `AnthropicProvider` carried, and it is repeated rather than quietly dropped.
    """

    name = "openai_compatible"

    def __init__(self, model_label: str, *, base_url: str, api_key: str,
                 temperature: float | None = None,
                 effort: str | None = None,
                 structured_outputs: bool = True,
                 timeout: float = 600.0,
                 transport: Callable[[str, Mapping[str, Any], Mapping[str, str], float],
                                     Mapping[str, Any]] | None = None) -> None:
        self.model_label = model_label
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.temperature = temperature
        self.effort = effort
        self.structured_outputs = structured_outputs
        self.timeout = timeout
        self._transport = transport or _post_json

    @classmethod
    def for_host(cls, host: str, model_label: str, *, api_key: str, **kwargs: Any
                 ) -> "OpenAICompatibleProvider":
        try:
            base_url = OPENAI_COMPATIBLE_ENDPOINTS[host]
        except KeyError:
            raise ValueError(
                f"unknown host {host!r}; known: "
                f"{', '.join(sorted(OPENAI_COMPATIBLE_ENDPOINTS))}. "
                "Pass base_url= directly for anything else."
            ) from None
        return cls(model_label, base_url=base_url, api_key=api_key, **kwargs)

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        messages: list[dict[str, Any]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.user})

        body: dict[str, Any] = {
            "model": self.model_label,
            # `max_tokens` is the deprecated spelling and reasoning models reject
            # it; the ceiling also has to cover reasoning tokens.
            "max_completion_tokens": request.max_tokens,
            "messages": messages,
        }
        # Pinned and recorded when the served model is a reasoning model. Leaving
        # it unset would run this arm at the host's default while the frontier arm
        # ran at a pinned effort -- an unrecorded variable between the two arms
        # the whole comparison rests on. Omitted when None, because hosts serving
        # non-reasoning models reject the parameter.
        if self.effort is not None:
            body["reasoning_effort"] = self.effort
        if self.structured_outputs:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "llm_output", "strict": True,
                                "schema": dict(request.output_schema)},
            }
        else:
            body["response_format"] = {"type": "json_object"}
        # Open-weight hosts *do* accept temperature. Sending it is a deliberate
        # choice recorded in the transcript, not a default: leaving it unset means
        # the host's default applies, which is exactly the unrecorded variable
        # HC-64 is about.
        if self.temperature is not None:
            body["temperature"] = self.temperature

        payload = self._transport(
            f"{self.base_url}/chat/completions",
            body,
            {"Authorization": f"Bearer {self._api_key}",
             "Content-Type": "application/json",
             # Identify the client. Some hosts sit behind a CDN that rejects
             # urllib's default UA outright (Cloudflare 1010), which surfaces as
             # a 403 with no useful body.
             "User-Agent": USER_AGENT},
            self.timeout,
        )

        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        usage = payload.get("usage") or {}
        # Some hosts break reasoning tokens out the way OpenAI does; they are
        # billed as output either way, so record them when they are offered.
        details = usage.get("completion_tokens_details") or {}
        finish = choice.get("finish_reason")

        # A structured-output refusal may arrive in its own field here too.
        refusal = message.get("refusal")
        return ProviderResponse(
            text=text,
            model=payload.get("model") or self.model_label,
            input_tokens=usage.get("prompt_tokens", 0) or 0,
            output_tokens=usage.get("completion_tokens", 0) or 0,
            reasoning_tokens=details.get("reasoning_tokens", 0) or 0,
            # Normalized to the vocabulary run_case branches on, so one chain of
            # outcome handling covers every arm.
            stop_reason=("refusal" if refusal
                         else _NORMALIZED_FINISH.get(finish, finish)),
            stop_details=({"finish_reason": finish, "refusal": refusal}
                          if refusal else
                          {"finish_reason": finish} if finish else None),
        )


_NORMALIZED_FINISH: Mapping[str, str] = MappingProxyType({
    "stop": "end_turn",
    "length": "max_tokens",
    "content_filter": "refusal",
})


class TransientHTTPError(RuntimeError):
    """A retryable HTTP failure, carrying the host's own advice on when to retry.

    Rate limits are the normal case on a shared endpoint, and a host that sends
    `Retry-After` has told us exactly how long to wait. Guessing a backoff
    instead throws away that information and burns the quota re-asking too soon.
    """

    def __init__(self, message: str, *, status: int,
                 retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _post_json(url: str, body: Mapping[str, Any], headers: Mapping[str, str],
               timeout: float) -> dict[str, Any]:
    """POST JSON with the standard library. No vendor SDK, no new dependency."""
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        message = f"{url} returned HTTP {exc.code}: {detail}"
        if exc.code in (408, 409, 429) or exc.code >= 500:
            raise TransientHTTPError(
                message, status=exc.code,
                retry_after=_retry_after_seconds(exc.headers)) from exc
        raise RuntimeError(message) from exc


def _retry_after_seconds(headers: Any) -> float | None:
    """Parse `Retry-After`, which may be seconds or an HTTP date."""
    if headers is None:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        pass
    from email.utils import parsedate_to_datetime
    try:
        import datetime as _dt

        when = parsedate_to_datetime(raw)
        delta = (when - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


class OpenAIProvider:
    """The frontier arm (2026-09-20 onward): an OpenAI model in strict JSON mode.

    Replaced `AnthropicProvider` as the frontier arm at Aria's request. That is a
    change to *what the experiment compares*, not a transport detail, and it is
    recorded as a pre-call amendment in
    `docs/HTN-Concord_Pilot_Kill_Criteria.md`.

    Three shapes here differ from the OpenAI-compatible arm, and each one would
    have broken or silently corrupted the first live call. All three are taken
    from the installed SDK's own type definitions rather than from memory:

    * **`max_completion_tokens`, never `max_tokens`.** The SDK marks `max_tokens`
      deprecated and *incompatible with reasoning models* — and the flagship is a
      reasoning model. The ceiling also has to cover reasoning tokens, exactly as
      the Anthropic arm's had to cover thinking tokens.
    * **`reasoning_effort`.** The analogue of Anthropic's `effort`, and the thing
      this project pins and records in place of a temperature it cannot pin
      (HC-64). Accepted values on the flagship are `low`…`max`.
    * **`message.refusal`.** On a refusal the API returns `content: null` and puts
      the text in a separate `refusal` field. Reading only `content` yields an
      empty string, which parses as malformed JSON — scoring a declined clinical
      question as a formatting failure. On a clinical benchmark that is the
      difference between a finding and a bug.

    **Version pinning is not fully achievable here, and the limitation is real.**
    The flagship publishes no dated snapshot id — only the floating name — so the
    model behind it can change without the string changing. The mitigation is to
    record the id the API reports back on every call and to keep the transcript;
    that detects a change after the fact but cannot prevent one. Stated in
    `runner/README.md` rather than left for a reviewer to find.

    ⚠️ Never executed against a live API. No credential exists on this machine.
    """

    name = "openai"

    def __init__(self, client: Any = None, effort: str = "high",
                 timeout: float | None = None) -> None:
        timeout = DEFAULT_CALL_TIMEOUT if timeout is None else timeout
        if client is None:
            import openai  # imported lazily: not needed for tests or CI

            # Explicit, and generous: a reasoning model at high effort can spend
            # minutes on one case. The SDK's own default would otherwise decide
            # this silently, and a benchmark that gives up early records a
            # timeout where there was an answer.
            client = openai.OpenAI(timeout=timeout)
        self._client = client
        self.effort = effort
        self.timeout = timeout

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        messages: list[dict[str, Any]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.user})

        completion = self._client.chat.completions.create(
            model=request.model,
            messages=messages,
            # Covers reasoning tokens as well as the visible answer.
            max_completion_tokens=request.max_tokens,
            reasoning_effort=self.effort,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "llm_output", "strict": True,
                                "schema": dict(request.output_schema)},
            },
        )

        choice = completion.choices[0]
        message = choice.message
        refusal = getattr(message, "refusal", None)
        finish = getattr(choice, "finish_reason", None)

        usage = getattr(completion, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        stop_details: dict[str, Any] = {"finish_reason": finish}
        if refusal:
            # Surface it as a refusal even when finish_reason says "stop": the
            # model answered, just not with an answer.
            stop_details["refusal"] = refusal

        return ProviderResponse(
            text=(message.content or ""),
            model=getattr(completion, "model", request.model),
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            reasoning_tokens=getattr(details, "reasoning_tokens", 0) or 0,
            stop_reason=("refusal" if refusal
                         else _NORMALIZED_FINISH.get(finish, finish)),
            stop_details=stop_details,
        )
