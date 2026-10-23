"""JSON-mode model runner (HC-60) — the only stage in the system that calls an LLM.

Everything upstream (pipelines, engine) is a pure deterministic function; everything
downstream (evaluator, metrics) is a pure function of this stage's output. Keeping
the LLM boundary in one module is what makes the rest of the system reproducible.

Public surface:
    run_case(model, prompt_input, profile, provider=...) -> RunResult
    replay(transcript) -> dict          re-derive the parsed output, no network
    api_safe_schema(schema) -> dict     request-side copy of llm_output.schema.json

Three failure modes, deliberately distinct (HC-61): RefusalError (the model
declined — a result, not a parse failure), TruncatedOutputError (our max_tokens
ceiling, not the model's formatting), MalformedOutputError (the only one that is
a malformed-output rate).
"""
from __future__ import annotations

from runner.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    ProviderRequest,
    ProviderResponse,
    ReplayProvider,
    ScriptedProvider,
)
from runner.run_case import (
    MalformedOutputError,
    RefusalError,
    RunResult,
    TruncatedOutputError,
    TRANSCRIPT_VERSION,
    api_safe_schema,
    load_output_schema,
    replay,
    run_case,
)

__all__ = [
    "AnthropicProvider",
    "MalformedOutputError",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "ProviderRequest",
    "RefusalError",
    "ProviderResponse",
    "ReplayProvider",
    "RunResult",
    "ScriptedProvider",
    "TRANSCRIPT_VERSION",
    "TruncatedOutputError",
    "api_safe_schema",
    "load_output_schema",
    "replay",
    "run_case",
]
