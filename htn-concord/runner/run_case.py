"""run_case — one model call, strictly validated, fully recorded.

Contract: the model sees only `prompt_input`. The hidden PatientProfile is hashed
into the transcript for linkage and never serialized into the request, which is the
runner's half of the anti-leakage discipline.

Two schemas, deliberately: the API is sent a *stripped* copy of
`schemas/llm_output.schema.json` because structured outputs rejects `if`/`then`,
numeric bounds, and length constraints; the response is then validated against the
*full* schema locally. The API constrains what it can; the local validator is the
contract. Never validate against the stripped copy — that is what would let an
`abstain` with no reason through.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from runner.providers import Provider, ProviderRequest, _prompt_blob

TRANSCRIPT_VERSION = "1.0"

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "llm_output.schema.json"

# Keywords structured outputs does not accept. Stripped from the request copy only.
_UNSUPPORTED = frozenset({
    "if", "then", "else", "allOf", "not",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern",
    "minItems", "maxItems", "uniqueItems",
})

# USD per token. Verify against current pricing before quoting a cost in the paper;
# an unlisted model records a null cost rather than a wrong one.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10e-6, 50e-6),
    "claude-opus-4-8": (5e-6, 25e-6),
    "claude-opus-4-7": (5e-6, 25e-6),
    "claude-sonnet-5": (3e-6, 15e-6),
    "claude-haiku-4-5": (1e-6, 5e-6),
}

DEFAULT_SYSTEM = (
    "You are answering a hypertension management question. Reply with a single "
    "JSON object conforming to the provided schema and nothing else. Report only "
    "facts stated in the input; use null for anything not stated rather than "
    "guessing. Set decision to \"abstain\" with an abstain_reason when a "
    "determinant you need is unknown."
)


class MalformedOutputError(RuntimeError):
    """The model never produced schema-valid JSON within the retry budget."""

    def __init__(self, message: str, raw_text: str, attempts: int) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.attempts = attempts


@dataclass(frozen=True)
class RunResult:
    output: dict[str, Any]          # validated ModelRecommendation
    transcript: dict[str, Any]      # the durable record (HC-47 persists it)
    attempts: int
    malformed_attempts: int


def load_output_schema() -> dict[str, Any]:
    """The canonical LLMOutput contract (HC-5)."""
    return json.loads(_SCHEMA_PATH.read_text())


def api_safe_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Strip keywords the structured-outputs API rejects, recursively.

    Everything removed here is still enforced locally against the full schema.
    """
    if isinstance(schema, Mapping):
        out: dict[str, Any] = {}
        for key, value in schema.items():
            if key in _UNSUPPORTED:
                continue
            if key == "properties" and isinstance(value, Mapping):
                out[key] = {k: api_safe_schema(v) for k, v in value.items()}
            elif isinstance(value, Mapping):
                out[key] = api_safe_schema(value)
            elif isinstance(value, list):
                out[key] = [api_safe_schema(v) if isinstance(v, Mapping) else v
                            for v in value]
            else:
                out[key] = value
        return out
    return dict(schema)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the model's reply, tolerating a markdown fence around it.

    Fence tolerance is recovery, not laxity: the object inside still has to pass
    full schema validation.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        body = stripped.split("```")[1] if "```" in stripped[3:] else stripped[3:]
        if body.startswith("json"):
            body = body[4:]
        stripped = body.strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = _PRICES.get(model)
    if price is None:
        return None
    return input_tokens * price[0] + output_tokens * price[1]


def run_case(
    model: str,
    prompt_input: str,
    profile: Mapping[str, Any] | None,
    provider: Provider,
    *,
    system: str | None = DEFAULT_SYSTEM,
    case_id: str | None = None,
    task: str | None = None,
    max_attempts: int = 3,
    max_tokens: int = 4096,
) -> RunResult:
    """Run one benchmark case and return the validated output plus its transcript.

    `profile` is the hidden structured row. It is hashed for linkage and never
    sent to the model.
    """
    full_schema = load_output_schema()
    validator = jsonschema.Draft7Validator(full_schema)
    request_schema = api_safe_schema(full_schema)

    request = ProviderRequest(
        model=model,
        system=system,
        user=prompt_input,
        output_schema=request_schema,
        max_tokens=max_tokens,
    )

    malformed: list[str] = []
    last_text = ""
    started = time.monotonic()

    for attempt in range(1, max_attempts + 1):
        response = provider.complete(request)
        last_text = response.text
        try:
            candidate = _extract_json(response.text)
            validator.validate(candidate)
        except (json.JSONDecodeError, ValueError, jsonschema.ValidationError) as exc:
            malformed.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            continue

        latency_ms = int((time.monotonic() - started) * 1000)
        transcript = {
            "transcript_version": TRANSCRIPT_VERSION,
            "case_id": case_id,
            "task": task,
            "model": response.model,
            "provider": getattr(provider, "name", type(provider).__name__),
            "prompt": {
                "system": system,
                "user": prompt_input,
                "prompt_sha256": _sha256(_prompt_blob(system, prompt_input)),
            },
            "request": {
                "output_schema_sha256": _sha256(_canonical(full_schema)),
                "max_tokens": max_tokens,
            },
            "response": {
                "raw_text": response.text,
                "parsed": candidate,
                "stop_reason": response.stop_reason,
            },
            "attempts": attempt,
            "malformed_attempts": len(malformed),
            "malformed_detail": malformed,
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            },
            "cost_usd": _cost_usd(response.model, response.input_tokens,
                                  response.output_tokens),
            "latency_ms": latency_ms,
            "profile_sha256": _sha256(_canonical(dict(profile))) if profile else None,
        }
        return RunResult(
            output=candidate,
            transcript=transcript,
            attempts=attempt,
            malformed_attempts=len(malformed),
        )

    raise MalformedOutputError(
        f"no schema-valid JSON after {max_attempts} attempt(s): " + "; ".join(malformed),
        raw_text=last_text,
        attempts=max_attempts,
    )


def replay(transcript: Mapping[str, Any]) -> dict[str, Any]:
    """Re-derive the parsed output from a stored transcript, with no model call.

    This is the HC-60 acceptance gate. It re-parses and re-validates the archived
    raw text rather than trusting the stored `parsed` block, so a transcript that
    was edited after the fact fails instead of round-tripping.
    """
    validator = jsonschema.Draft7Validator(load_output_schema())
    raw = transcript["response"]["raw_text"]
    try:
        parsed = _extract_json(raw)
        validator.validate(parsed)
    except (json.JSONDecodeError, ValueError, jsonschema.ValidationError) as exc:
        raise MalformedOutputError(
            f"stored transcript does not reproduce: {exc}",
            raw_text=raw,
            attempts=1,
        ) from exc
    return parsed
