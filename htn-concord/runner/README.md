# `runner/` — JSON-mode model runner (HC-60)

The only stage in the system that calls an LLM. Everything upstream (pipelines,
engine) and downstream (evaluator, metrics) is a pure function, so confining the
model boundary to this module is what keeps the rest of the project reproducible.

```python
from runner import run_case, OpenAIProvider

result = run_case(
    model="gpt-6-astra",
    prompt_input=vignette_text,     # the ONLY thing the model sees
    profile=hidden_row,             # hashed for linkage, never sent
    provider=OpenAIProvider(),
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

`api_safe_schema()` also **inlines every `$ref` and drops `definitions`,
`$schema` and `$id`**. The full schema is draft-07 and spells its ref target
`#/definitions/...`, while the structured-output documentation names
`$ref`/`$defs` — rather than bet the first live call on whether the API resolves
draft-07's spelling, the request copy carries no refs at all. The full schema
keeps them; `jsonschema` resolves them locally.

## Three failure modes, never pooled (HC-61)

A benchmark that reports one "failure rate" cannot be read. These are separate,
with separate denominators, and `run_case` raises a different error for each:

| outcome | what happened | whose fault |
|---|---|---|
| `RefusalError` | `stop_reason == "refusal"` — the model declined | **a result.** On a clinical benchmark "the model would not answer" is a finding, not a formatting problem. Never retried: the same request earns the same refusal. |
| `TruncatedOutputError` | every attempt hit `max_tokens` | **ours.** The ceiling was too low. |
| `MalformedOutputError` | text that is not schema-valid JSON | **the model's.** This — and only this — is the malformed-output rate. |

Each attempt is tagged in the transcript's `attempt_log` as `ok` /
`invalid_json` / `schema_violation` / `truncated`, which is what feeds the
pilot's failure-mode table.

`max_tokens` defaults to **16000**. It was 4096, chosen before adaptive thinking
was on by default — and thinking tokens count against the ceiling, so the old
value would have truncated good answers and charged our own configuration to the
model's formatting. That number is precisely the one HC-61 exists to measure.

## Inference parameters: what is pinned, and why

`effort` is pinned (`high` by default) and recorded per call. Adaptive thinking
is declared explicitly rather than left to the model default, because the default
differs between model generations and thinking is the work this benchmark
measures.

**No server-side refusal fallback.** The API can silently re-route a refused
request to another model. Model identity is a crossed factor in this design and
is recorded per call, so a substituted answer would be a number attributed to the
wrong model. A refusal must surface as a refusal.

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

What *is* pinned and recorded: model ID **as the host reported it** (not as we
asked for it), prompt text and its SHA-256, the output schema SHA-256, `effort`,
`thinking`, `max_tokens`, the per-attempt outcome log, token usage, cost, and
latency.

## The two arms (HC-61, decision D3)

| arm | class | model |
|---|---|---|
| **frontier** | `OpenAIProvider` | `gpt-6-astra` (override with `FRONTIER_MODEL`) |
| open-weight | `OpenAICompatibleProvider` | a large open-weight model on a hosted OpenAI-compatible endpoint (Together / Fireworks / Groq / OpenRouter) |
| *(retained)* | `AnthropicProvider` | still built and tested; select it with `FRONTIER_MODEL=claude-opus-5` |

**The frontier arm changed from Claude to OpenAI on 2026-09-20**, at Aria's
request. That is a change to what the experiment compares — not a transport
detail — so it is recorded as a pre-call amendment in the signed
`docs/HTN-Concord_Pilot_Kill_Criteria.md`. `AnthropicProvider` is kept rather
than deleted: it is covered by tests, costs nothing to keep, and preserves the
option of a third arm.

The open-weight arm exists because the design only reports a failure mode as a
finding if it replicates across models, and that needs a genuinely different
model rather than a smaller sibling. Open weights also add a reproducibility
property no API model has: they can be pinned by version and re-run later.

All three providers normalize onto one outcome vocabulary (`end_turn` /
`max_tokens` / `refusal`), so the pilot's failure-mode table means the same thing
per model.

### What differs per provider, and why it matters

Each of these would have broken or silently corrupted a first live call. All are
taken from the installed SDKs' own type definitions, not from memory.

| | Anthropic | OpenAI | OpenAI-compatible hosts |
|---|---|---|---|
| output ceiling | `max_tokens` | **`max_completion_tokens`** — `max_tokens` is deprecated and *rejected by reasoning models* | `max_tokens` |
| effort knob | `effort` (in `output_config`) | **`reasoning_effort`** | none; `temperature` exists and is deliberately not sent |
| reasoning | `thinking: {type: "adaptive"}`, counted inside `output_tokens` | on by default; `reasoning_tokens` reported separately and **billed as output** | n/a |
| refusal | `stop_reason == "refusal"` + `stop_details` | **`message.refusal`, with `content: null`** | `finish_reason == "content_filter"` |

The OpenAI refusal shape is the sharpest trap: reading only `message.content`
yields an empty string, which parses as malformed JSON — scoring a declined
clinical question as a formatting failure. On a clinical benchmark that is the
difference between a finding and a bug.

### ⚠️ The frontier arm cannot be fully version-pinned

`gpt-6-astra` publishes **no dated snapshot id** — the floating name is the only
id there is. The model behind it can therefore change without the string
changing, which is precisely the failure mode this project's pinning discipline
exists to prevent, and it cannot be prevented here.

The mitigation is partial and should be described as partial: every call records
the model id the API reports back, plus the full transcript, so a change is
**detectable after the fact** rather than preventable. If a dated snapshot is
published later, pin it and note the switch. This is a limitation of the arm, not
of the harness, and it belongs in the manuscript's reproducibility section beside
the archival-vs-sampling distinction.

## Verification status

The provider seam is fully covered by hermetic tests (`ScriptedProvider`,
`ReplayProvider`, and fakes for both live providers), so `pytest` needs no API
key and CI stays offline and deterministic. The pilot harness
(`experiments/pilot.py`) and the signed kill criteria
(`experiments/kill_criteria.py`) are covered the same way, and the whole pipeline
has been dry-run end to end against the **real** corpus with a scripted model.

⚠️ **No provider here has been executed against a live API** —
`OpenAIProvider`, `AnthropicProvider` and `OpenAICompatibleProvider` alike. No
credential existed on the machine when they were written (2026-09-20): no
`OPENAI_API_KEY`, no `ANTHROPIC_API_KEY`, no `ANTHROPIC_AUTH_TOKEN`, no `ant`
CLI, no OAuth profile. The request shapes are pinned by test against mocks and derived
from the current API reference rather than from memory — but a shape that passes
a mock is a shape no server has accepted yet.

**Therefore the malformed-output rate is still unmeasured**, and it is one of the
numbers the pilot is required to report. Do not quote it, and do not let a table
imply it exists. To close this: put `OPENAI_API_KEY` in `htn-concord/.env` (gitignored) and
run `python scripts/run_pilot.py smoke` — one case, end to end, validated against
the *full* schema. The first live call is also the first real test of whether the
API accepts the stripped schema.
