# Handoff — the pilot gate: HC-57 → HC-61 → HC-80

**Written 2026-09-20.** Operational handoff. English only (the five project docs are
EN/CN pairs; this is internal tooling).

Runs in parallel with `2026-09-20-mimic-block.md`. Different files, no shared
dependencies, no coordination needed beyond both trackers.

---

## 0. Your mission

Get the project to its own go/no-go decision. Three tickets:

| | | Size | Who |
|---|---|---|---|
| **HC-57** | Human facts-only read of 20 vignettes | S | **Aria signs. You prepare.** |
| **HC-61** | Make a real model call work, twice (frontier + open-weight) | S | You |
| **HC-80** | Pilot spike + kill criteria → go/no-go | M | You, Aria signs criteria |

All three dependencies are already satisfied: the corpus (HC-53), the runner
(HC-60) and the metrics (HC-70) are built and green. **Nothing is blocking this
path.** It has simply never been run.

---

## 1. Why this path matters more than its size suggests

The experiment design, §11, is explicit:

> The pilot (HC-80) runs only C1, moderate level, 20 patients × 2 models. It exists
> to terminate early when the benchmark lacks discrimination (all difficulties near
> ceiling, or frontier ≈ open-weight everywhere). **Before the pilot proves the
> corpus discriminates between models, no ladder condition after C1 is worth
> building.**

Everything else in the backlog — the drug-class rules, the retrieval condition, the
tool condition, the entire MIMIC arm — sits downstream of a question nobody has
asked yet: **does this corpus tell two models apart?**

If the answer is no, the honest move is to stop, and the project says so in writing.
Your job is to make that answer obtainable.

---

## 2. What the project is (short version)

HTN-Concord measures whether LLMs follow the 2025 AHA/ACC hypertension guideline when
deciding whether to **start or intensify** antihypertensive therapy.

- The answer key is a **hand-written deterministic rule engine** — not LLM-generated,
  not per-case expert annotation, not physician behaviour.
- Scoring is **deterministic pure functions**. No LLM-as-judge anywhere.
- The same patient is rendered at three difficulty levels carrying **provably identical
  decision-relevant information**, enforced by a test on every corpus build.

Frozen corpus: 4,806 NHANES patients → **14,418 cases**, split at patient level
(train 2,914 / dev 940 / test 952 patients, zero overlap), leakage audit clean.

**Six principles you may not violate** (Master Plan §0): deterministic gold standard
without clinicians; Aria hand-writes guideline rules and you build everything around
them (**you do not touch `engine/rules/`**); one `PatientProfile` schema with no
source branching downstream; anti-leakage discipline — the structured row is the
hidden label and never enters a request; reproducible pipelines; one module per
guideline, disagreements reported never merged.

---

## 3. Aria has no clinical background

When you hit a question needing clinical judgement, **do not ask her to settle it.**
Make the conservative call, implement it, write the reasoning into the code, flag it
explicitly for **HC-49** (clinician adjudication), and keep going. Do not block.

Two questions in this block *are* hers, because they are methodological rather than
clinical, and she must answer them before you proceed:

- the **kill criteria** for HC-80 (§6);
- **which open-weight model** is the second arm (decision D3, §5).

---

## 4. HC-57 — you prepare, Aria signs

This is the **human half** of the Phase-4 acceptance gate. The mechanical half (the
forbidden-token scanner) already runs on every case and passes with zero hits. A
scanner only catches tokens it was told about; only a reader catches a vignette that
gives the answer away in wording nobody thought to ban.

**It is a sign-off, not a task you can complete.** Do not mark it done yourself.

What you do:

1. Run `tasks.spotcheck.build_spotcheck(corpus_dir)`. It already exists and already
   does the right thing: the sample is **stratified by engine decision** and shows
   **all three levels of each patient**, so abstentions and contraindication-positive
   cases are oversampled rather than drowned in `lifestyle_only` (which is 51.5% of
   the test split).
2. Produce the sheet in a form Aria can read and mark up.
3. Give her the instruction plainly: *read each vignette and confirm it states only
   raw facts — no stage name, no decision verb, no drug-class name, and nothing that
   implies the answer. If a phrasing makes you hesitate, flag it.*
4. Record the sign-off, and record any flagged phrasings as candidate additions to
   `leakage.py`.

**Why it gates everything after it:** per the backlog, *any pilot number read before
this gate closes is provisional.* So run HC-57 first, or at minimum in parallel with
HC-61 — not after the pilot.

---

## 5. HC-61 — the real state is worse than "not started"

`AnthropicProvider` exists in `runner/providers.py` and looks plausible. **It has
never been executed against a real API.** Verified 2026-09-20:

- `anthropic` SDK is **not installed** and **not in `requirements.txt`**
- `ANTHROPIC_API_KEY` is **not set**
- therefore the **malformed-JSON rate has never been measured**, and that number is
  something the pilot is supposed to report

Also: the price table in `runner/run_case.py` is **stale**. It lists older model ids
and is missing current ones. The code degrades safely — an unlisted model records a
null cost rather than a wrong one — but the pilot would report null costs.

**Before writing any code, load the `claude-api` skill.** Do not take model ids,
pricing, or API parameter shapes from this document or from memory; get them from the
skill. The provider currently sends `output_config` with a `json_schema` format and an
`effort` field — verify that shape is current.

Your sequence:

1. Load `claude-api`. Confirm current model ids, the structured-output parameter
   shape, and pricing.
2. Add the SDK to `requirements.txt`, **pinned** (the file says "bump deliberately").
3. Get credentials from Aria. **Never commit a key.**
4. **One smoke call.** A single case, end to end, real model. Confirm the response
   validates against the *full* `llm_output.schema.json` — not the stripped copy sent
   to the API. The stripped copy cannot enforce "`abstain_reason` is required exactly
   when `decision == abstain`", which is the rule separating a real abstention from a
   silent one.
5. Update the price table against what the skill says.
6. **Measure the malformed-JSON rate** on a small batch and record it.
7. Add the second arm: **≥1 open-weight model**. This is **decision D3 and it is
   undecided** — propose a candidate with reasoning and get Aria's answer. It
   determines whether the "reproduces across models" bar can be met at all.

**Pin `effort` and record it.** There is no temperature, top_p, top_k, or seed to pin —
current frontier models reject them with a 400 (that is ticket HC-64, and the Master
Plan's "temperature/seed pinned" is not implementable as written). Reproducibility
rests on the transcript, not on sampling control. `effort` *does* change answer
quality, so it must be held fixed and recorded.

---

## 6. HC-80 — resolve a documented conflict before you run anything

### The conflict

Two project documents disagree about the pilot's scope:

| Source | Scope |
|---|---|
| Backlog, HC-80 | 20 cases **× 3 difficulties** × 2 models |
| Experiment Design §11 | C1, **moderate level only**, 20 patients × 2 models |

§11 is **internally inconsistent**: it says moderate-only, then states the kill
criterion as "all difficulties near ceiling". **You cannot evaluate all difficulties
having run one.** The backlog scope is the one consistent with the stated criteria.

**Resolve this explicitly, record the decision, and update both documents and both
their `_zh` twins in the same commit.** Do not quietly pick one.

### The repeat count

Experiment design §4.4 sets **k = 5** repeats per case per condition, because current
models cannot be made deterministic and run-to-run variance is a quantity to report
rather than hide. Decision **D2** says k is provisionally 5 and **"raise it if the
pilot's SD is large"** — which means the pilot is *specifically supposed to inform k*.

So the pilot must run repeats. A single pass cannot answer the question it exists to
answer. Budget accordingly: 20 × 3 × 2 × 5 = 600 calls at full scope.

### The freeze does not apply yet

Per §11 the order is: **pilot → freeze → full C0/C1 runs.** So HC-48 (prompt
versioning) and HC-94 (pre-registration freeze) are **not** blockers for the pilot.

The corollary matters: **pilot numbers are not results.** They inform a go/no-go and
nothing else. Do not put them in a paper, a Notion page, or a figure without the word
"provisional" attached.

### Write the kill criteria before you look at anything

This is the part most likely to go wrong. A kill gate whose criteria are written after
the results is not a kill gate — you will rationalise whatever you see.

1. Draft concrete, numeric criteria from the two stated conditions: *all difficulties
   near ceiling*, and *frontier ≈ open-weight everywhere*. Turn each into a threshold
   you could lose on.
2. **Get Aria's sign-off on the criteria before running.**
3. Then run.
4. Then compare, and state the verdict plainly — including if it is "stop".

### Deliverable

A table of results broken down by **failure mode** (extraction / reasoning /
citation), by difficulty, and by model, plus the run-to-run SD, plus the
malformed-JSON rate, plus the explicit go/no-go verdict against the pre-registered
criteria.

**Every concordance number carries `majority_class_baseline` beside it.** The
aggregation layer already enforces this in code — the test split is 51.5%
`lifestyle_only`, so a model that answers that unconditionally scores 51.5%. Do not
strip it when you write the table up.

---

## 7. Traps

1. **Validate against the full schema, never the stripped copy** sent to the API.
2. **The hidden profile never enters a request** — it is hashed into the transcript
   for linkage only. `ScriptedProvider` records every request so a test can assert this.
3. **Abstention is scored, not discarded.** It is reported as *two* rates (failed to
   abstain when it should, abstained when it should not), each with its own
   denominator, never combined. A benchmark that drops abstentions rewards guessing.
4. **Safety is never folded into the headline.** A correct decision that recommends a
   fetotoxic drug is not 90% right; it is right and unsafe, reported separately.
5. **Undefined is dropped, not zeroed** — with an explicit `n_` count so a thin
   denominator stays visible.
6. **Never hardcode test counts in documentation.** Write "run the suite".
7. **Never commit an API key**, and never widen what leaves the machine: only rendered
   vignettes go to a model, never raw rows.
8. Pilot numbers before HC-57 closes are **provisional**. Label them.

---

## 8. Working rules

- **Git:** never commit to `main`. Branch off the latest `main`, and **re-check the
  branch immediately before committing.** The repo is currently on
  `ariacongdev/notion-doc-restructure` with untracked files present.
- **Docs are bilingual pairs.** Master Plan, Backlog, DataDictionary, Walkthrough and
  Experiment Design each have a `_zh.md` twin plus two Notion trees. Edit both in the
  same commit. English wins on conflict.
- **Two synced trackers.** Linear board `Generative AI in Medical` (`GAI-n` carrying
  `HC-n` in the title) and the Notion database `HTN-Concord — Progress Tracker`.
  Update **both** on every piece of progress.
- Notion writes containing shell-command-looking strings are blocked by Cloudflare.
  Reword; do not retry verbatim.
- Tests before implementation. Search the backlog by symptom before filing a new
  ticket — HC-96 was filed as a duplicate of HC-24 because that step was skipped.

---

## 9. Start here

1. Run the test suite. Confirm green.
2. Read `runner/README.md` end to end — it already documents the two-schema rule and
   the determinism position.
3. **HC-57**: generate the spot-check sheet, hand it to Aria, get the sign-off moving.
   It runs on her clock, so start it first even though you cannot finish it.
4. **HC-61**: load `claude-api`, install and pin the SDK, get credentials, one smoke
   call, measure the malformed-JSON rate, refresh the price table, propose the
   open-weight arm for D3.
5. **HC-80**: resolve the scope conflict, decide the repeat count, **write and get
   sign-off on the kill criteria**, then run, then report the verdict.

File a ticket for anything you find that is not already tracked, and mirror it to both
trackers.

---

## 10. Definition of done

A go/no-go verdict exists, measured against criteria that were written and signed off
**before** the results were seen, supported by a failure-mode table with run-to-run
SD and majority-class baselines, with every number labelled provisional until HC-57
closes — and the verdict is stated plainly, including if it is *stop*.
