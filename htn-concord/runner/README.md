# `runner/` — JSON-mode model runner (HC-60)

The only stage in the system that calls an LLM. Everything upstream (pipelines,
engine) and downstream (evaluator, metrics) is a pure function, so confining the
model boundary to this module is what keeps the rest of the project reproducible.

```python
from runner import run_case, AnthropicProvider

result = run_case(
    model="claude-opus-4-8",
    prompt_input=vignette_text,     # the ONLY thing the model sees
    profile=hidden_row,             # hashed for linkage, never sent
    provider=AnthropicProvider(),
    case_id="nhanes-12345",
    task="B",
)
result.output       # validated against schemas/llm_output.schema.json
result.transcript   # durable record; HC-47 persists it
```

## Two schemas, on purpose

The structured-outputs API does not accept `if`/`then`/`else`, `allOf`, numeric
bounds, or length/array constraints. `api_safe_schema()` strips those from the
copy sent with the request; the response is then validated against the **full**
`llm_output.schema.json` locally.

Never validate against the stripped copy. The stripped copy cannot enforce
"`abstain_reason` is required exactly when `decision == abstain`" — the rule that
separates a real abstention from a silent one.

## Determinism (read this before quoting reproducibility)

**There is no temperature, top_p, top_k, or seed to pin.** Those parameters are
rejected with a 400 on current frontier Claude models. The Master Plan's
"temperature/seed pinned" is not implementable as written — see **HC-61**.

Reproducibility rests on the **transcript**, not on sampling control:

- `replay(transcript)` re-parses and re-validates the archived raw text with no
  network call. It deliberately ignores the stored `parsed` block, so a
  transcript edited after the fact fails instead of round-tripping.
- `ReplayProvider(transcript)` re-runs the whole pipeline offline, and refuses to
  serve a stored response if the prompt hash changed — replaying an archived
  answer against an edited prompt is a fabricated result, not a reproduction.

What *is* pinned and recorded: model ID, prompt text and its SHA-256, the output
schema SHA-256, `effort`, `max_tokens`, token usage, cost, and latency.

## Verification status

The provider seam is fully covered by hermetic tests (`ScriptedProvider`,
`ReplayProvider`, and a mock client for `AnthropicProvider`), so `pytest` needs
no API key and CI stays offline and deterministic.

⚠️ **`AnthropicProvider` has not been executed against the live API.** The
request shape is pinned by test against a mock, and the schema-stripping list is
derived from the documented structured-outputs limitations — but no real call has
been made from this repo (no SDK, key, or credential was available when it was
written). Before the first real run: `pip install anthropic`, then run one case
and confirm the API accepts the stripped schema. Treat the malformed-JSON rate as
unmeasured until then.

`anthropic` is intentionally **not** in `requirements.txt` — the import is lazy,
so the suite and CI stay dependency-light. Install it when you run real models.
