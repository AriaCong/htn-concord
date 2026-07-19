"""JSON-mode model runner (HC-60) — the only stage in the system that calls an LLM.

Everything upstream (pipelines, engine) is a pure deterministic function; everything
downstream (evaluator, metrics) is a pure function of this stage's output. Keeping
the LLM boundary in one module is what makes the rest of the system reproducible.

Public surface:
    run_case(model, prompt_input, profile, provider=...) -> RunResult
    replay(transcript) -> dict          re-derive the parsed output, no network
    api_safe_schema(schema) -> dict     request-side copy of llm_output.schema.json
"""
from __future__ import annotations

from runner.providers import (
    AnthropicProvider,
    ProviderRequest,
    ProviderResponse,
    ReplayProvider,
    ScriptedProvider,
)
from runner.run_case import (
    MalformedOutputError,
    RunResult,
    TRANSCRIPT_VERSION,
    api_safe_schema,
    load_output_schema,
    replay,
    run_case,
)

__all__ = [
    "AnthropicProvider",
    "MalformedOutputError",
    "ProviderRequest",
    "ProviderResponse",
    "ReplayProvider",
    "RunResult",
    "ScriptedProvider",
    "TRANSCRIPT_VERSION",
    "api_safe_schema",
    "load_output_schema",
    "replay",
    "run_case",
]
