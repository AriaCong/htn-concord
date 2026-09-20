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
from typing import Any, Mapping, Sequence

import jsonschema

from runner.providers import Provider, ProviderRequest, _prompt_blob

TRANSCRIPT_VERSION = "1.1"

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "llm_output.schema.json"

# Keywords structured outputs does not accept. Stripped from the request copy only.
_UNSUPPORTED = frozenset({
    "if", "then", "else", "allOf", "not",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern",
    "minItems", "maxItems", "uniqueItems",
})

# USD per token, transcribed from the published price list (cached 2026-06-24).
# An unlisted model records a null cost rather than a wrong one, so this table
# being incomplete degrades to "no cost" — but the pilot is supposed to report a
# cost, so the models it runs must be here. Re-check before quoting in a paper.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10e-6, 50e-6),
    "claude-mythos-5-1": (10e-6, 50e-6),
    "claude-fable-5": (10e-6, 50e-6),
    "claude-opus-5": (5e-6, 25e-6),
    "claude-opus-4-8": (5e-6, 25e-6),
    "claude-opus-4-7": (5e-6, 25e-6),
    "claude-opus-4-6": (5e-6, 25e-6),
    "claude-sonnet-5": (2e-6, 10e-6),
    "claude-sonnet-4-6": (3e-6, 15e-6),
    "claude-haiku-4-5": (1e-6, 5e-6),
    # OpenAI (frontier arm from 2026-09-20). Short-context tier: the published
    # table prices long-context variants higher, and Task B vignettes are ~1-2k
    # tokens, so the short-context rate is the applicable one. Re-check before
    # quoting in a paper, and re-check if an input ever grows.
    "gpt-6-astra": (10e-6, 50e-6),
    "gpt-5.6-sol": (4e-6, 20e-6),
    "gpt-5.6-terra": (2e-6, 12e-6),
    "gpt-5.6-luna": (0.2e-6, 1.2e-6),
    "gpt-5.5": (5e-6, 30e-6),
    "gpt-5.4": (2.5e-6, 15e-6),
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

    def __init__(self, message: str, raw_text: str, attempts: int,
                 attempt_log: Sequence[Mapping[str, Any]] = ()) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.attempts = attempts
        self.attempt_log = list(attempt_log)


class TruncatedOutputError(MalformedOutputError):
    """Every attempt stopped at `max_tokens`.

    This is our ceiling being too low, not the model formatting badly, and the
    two must not land in the same rate. Thinking tokens count against
    `max_tokens`, so a value chosen before adaptive thinking was on will truncate
    good answers and inflate the malformed-output rate with our own defect.
    """


class RefusalError(RuntimeError):
    """The model declined to answer (`stop_reason == "refusal"`).

    A refusal is a *result*, not a parse failure: on a clinical benchmark, "the
    model would not answer this" is a finding, and it has to be reported as its
    own outcome with its own denominator rather than folded into a
    malformed-output rate. It is never retried — the same request earns the same
    refusal, and paying for it twice tells us nothing.
    """

    def __init__(self, message: str, *, category: str | None = None,
                 raw_text: str = "", stop_details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.raw_text = raw_text
        self.stop_details = dict(stop_details) if stop_details else None


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
    """Build the request-side copy: strip what the API rejects, inline every ref.

    Everything removed here is still enforced locally against the full schema,
    which is the actual contract.

    **Refs are inlined and `definitions` dropped.** The full schema is draft-07
    and spells its ref target `#/definitions/...`; the structured-output
    documentation names `$ref`/`$defs`. Rather than bet the first live call on
    whether the API resolves draft-07's spelling, the request copy carries no
    refs at all. `$schema` and `$id` go for the same reason: they are not part of
    the output contract and only give the API more to reject.
    """
    definitions = dict(schema.get("definitions") or {})
    out = _strip(schema, definitions)
    for key in ("$schema", "$id", "definitions"):
        out.pop(key, None)
    return out


def _strip(node: Any, definitions: Mapping[str, Any], _depth: int = 0) -> Any:
    """Recursive half of `api_safe_schema`. `_depth` guards a cyclic ref."""
    if not isinstance(node, Mapping):
        if isinstance(node, list):
            return [_strip(v, definitions, _depth) for v in node]
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/definitions/"):
        if _depth > 16:
            raise ValueError(f"cyclic or too-deeply nested $ref: {ref}")
        target = definitions.get(ref.rsplit("/", 1)[-1])
        if target is None:
            raise ValueError(f"unresolvable $ref in output schema: {ref}")
        merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        return _strip(merged, definitions, _depth + 1)

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _UNSUPPORTED:
            continue
        if key == "properties" and isinstance(value, Mapping):
            out[key] = {k: _strip(v, definitions, _depth) for k, v in value.items()}
        else:
            out[key] = _strip(value, definitions, _depth)
    return out


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
    max_tokens: int = 16000,
) -> RunResult:
    """Run one benchmark case and return the validated output plus its transcript.

    `profile` is the hidden structured row. It is hashed for linkage and never
    sent to the model.

    Three failures are distinguished rather than pooled, because the pilot reports
    a failure-mode table and pooling them would make it unreadable:

    * `RefusalError` — the model declined. Not retried.
    * `TruncatedOutputError` — every attempt hit `max_tokens`. Our ceiling, not
      the model's formatting.
    * `MalformedOutputError` — the model produced text that is not schema-valid
      JSON. This is the only one of the three that is a malformed-output rate.

    `max_tokens` defaults to 16000 because thinking tokens count against it; the
    old 4096 was set before adaptive thinking was on by default and would have
    charged our own configuration to the model's formatting.
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

    attempt_log: list[dict[str, Any]] = []
    last_text = ""
    started = time.monotonic()

    effort = getattr(provider, "effort", None)
    thinking = getattr(provider, "thinking", None)

    for attempt in range(1, max_attempts + 1):
        response = provider.complete(request)
        last_text = response.text

        # A refusal is an answer, and retrying it buys the same answer again.
        if response.stop_reason == "refusal":
            details = response.stop_details or {}
            said = (details.get("refusal") or details.get("explanation")
                    or "no explanation given")
            raise RefusalError(
                "model declined to answer "
                f"(category={details.get('category')!r}): {said}",
                category=details.get("category") or details.get("finish_reason"),
                raw_text=response.text,
                stop_details=response.stop_details,
            )

        if response.stop_reason == "max_tokens":
            attempt_log.append({
                "attempt": attempt, "outcome": "truncated",
                "detail": f"stopped at max_tokens={max_tokens}",
            })
            continue

        try:
            candidate = _extract_json(response.text)
        except (json.JSONDecodeError, ValueError) as exc:
            attempt_log.append({
                "attempt": attempt, "outcome": "invalid_json",
                "detail": f"{type(exc).__name__}: {exc}",
            })
            continue

        try:
            validator.validate(candidate)
        except jsonschema.ValidationError as exc:
            attempt_log.append({
                "attempt": attempt, "outcome": "schema_violation",
                "detail": f"{exc.message} at {'/'.join(str(p) for p in exc.absolute_path)}",
            })
            continue

        attempt_log.append({"attempt": attempt, "outcome": "ok", "detail": None})
        latency_ms = int((time.monotonic() - started) * 1000)
        malformed = [a for a in attempt_log if a["outcome"] != "ok"]
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
                "effort": effort,
                "thinking": dict(thinking) if thinking else None,
            },
            "response": {
                "raw_text": response.text,
                "parsed": candidate,
                "stop_reason": response.stop_reason,
            },
            "attempts": attempt,
            "attempt_log": attempt_log,
            "malformed_attempts": len(malformed),
            "malformed_detail": [f"attempt {a['attempt']}: {a['outcome']}: {a['detail']}"
                                 for a in malformed],
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                # Billed as output and absent from the reply; a run that ignores
                # them understates its own cost.
                "reasoning_tokens": response.reasoning_tokens,
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

    summary = "; ".join(f"attempt {a['attempt']}: {a['outcome']}: {a['detail']}"
                        for a in attempt_log)
    error = (TruncatedOutputError
             if attempt_log and all(a["outcome"] == "truncated" for a in attempt_log)
             else MalformedOutputError)
    raise error(
        f"no schema-valid JSON after {max_attempts} attempt(s): {summary}",
        raw_text=last_text,
        attempts=max_attempts,
        attempt_log=attempt_log,
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
