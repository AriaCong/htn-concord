"""Model providers — the seam between the runner and any actual LLM.

`run_case` depends only on the Provider protocol, so the test suite runs entirely
on ScriptedProvider/ReplayProvider: no API key, no network, no nondeterminism in CI.
AnthropicProvider is the one class that talks to a real model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


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
    """Raw model output plus the accounting the transcript needs."""
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None


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
            stop_reason="end_turn",
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

    Determinism note (HC-61): there is no temperature/top_p/top_k and no seed to
    pin — those parameters are rejected on current frontier models. Run-to-run
    reproducibility therefore comes from the stored transcript (ReplayProvider),
    not from sampling control. `effort` is pinned because it changes answer
    quality and so must be recorded and held fixed across a benchmark freeze.
    """

    name = "anthropic"

    def __init__(self, client: Any = None, effort: str = "high") -> None:
        if client is None:
            import anthropic  # imported lazily: not needed for tests or CI

            client = anthropic.Anthropic()
        self._client = client
        self.effort = effort

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "output_config": {
                "format": {"type": "json_schema", "schema": dict(request.output_schema)},
                "effort": self.effort,
            },
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.system is not None:
            kwargs["system"] = request.system

        message = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
        usage = getattr(message, "usage", None)
        return ProviderResponse(
            text=text,
            model=getattr(message, "model", request.model),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            stop_reason=getattr(message, "stop_reason", None),
        )
