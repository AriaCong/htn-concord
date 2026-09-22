# Handoff — make `hard` actually hard, then re-test K2

**Written 2026-09-22.** Operational handoff. English only (the project docs are
EN/CN pairs; this is internal tooling).

---

## 0. Your mission

The HC-80 pilot returned **GO-NARROWED**: one kill criterion fired, **K2 — the
difficulty ladder is inert**. Your job is to fix that and measure whether the fix
worked. Two steps:

1. Make the `hard` rendering level genuinely harder to extract from, without
   changing the decision-relevant information it carries.
2. Re-run a scoped pilot and check whether `extraction_f1` now drops at `hard`.

**This blocks the pre-registration freeze.** Per Experiment Design §11 the order
is pilot → freeze → full runs, and the pilot found a corpus defect. Freezing now
would freeze it in.

---

## 1. Where things are

The repo was reorganised on 2026-09-22 into two sibling folders:

| | |
|---|---|
| `~/Documents/PhD GenAI/htn-concord-main/` | the main checkout, holds `.git`, `Data/` (60 GB), the built corpus and the venv |
| `~/Documents/PhD GenAI/htn-concord-pilot-gate/` | a linked git worktree from the pilot work |

Everything is merged to `main` (PRs #7–#12, 616 tests green). **Branch off the
latest `main`**; never commit to it directly. If you take a new worktree, note
that `htn-concord/data`, `.venv` and `references` are symlinks into the main
checkout — recreate them or your tests will skip and your runs will fail.

Python is **uv-managed and pinned to 3.12.13** by `htn-concord/.python-version`.
There is no `pip` inside the venv; use `uv pip install`. It drifted to 3.13 once
during a directory move and nobody noticed because the tests still passed — don't
repeat that.

Credentials live in `htn-concord/.env` (gitignored). Both arms are configured and
working.

---

## 2. What `hard` does now, and why it fails

`renderer/render.py`, the `else:  # hard` branch, does exactly two things:

```python
rng.shuffle(order)      # shuffle the four prose sections
paragraphs = [...]      # interleave inert filler
```

The filler is visit logistics: *"The patient arrived on time and was seen after a
short wait."*, *"A follow-up appointment was arranged before discharge."* The
code's own comment concedes `hard` is currently only "harder to extract from".

**The pilot shows it is not even that.** Every fact is stated in the same
sentence, with the same label and the same units, at all three levels. Reordering
paragraphs and adding logistics costs a language model nothing:

| | simple | moderate | hard |
|---|---|---|---|
| `decision_concordance` (frontier) | 0.850 | 0.850 | 0.850 |
| `extraction_f1` (frontier) | 0.918 | 0.918 | 0.918 |

Identical to three decimal places, with identical per-level failure-mode counts.

---

## 3. The constraint you may not break

**All three levels must carry provably identical decision-relevant information.**
This is enforced by `tests/test_renderer.py::test_every_level_carries_every_decision_relevant_value`
and it is what licenses reading a level-over-level drop as *extraction* rather
than as information loss. If you weaken that test to make your change pass, you
have destroyed the thing the levels exist to measure.

Difficulty must change **what it costs to recover a value**, never **whether the
value is recoverable**.

---

## 4. The trap that will waste your afternoon

**BMI is not an extracted field.** Neither is HbA1c, cholesterol, HDL, UACR or
creatinine-as-such. The evaluator scores extraction against exactly these twelve:

```
age  sex  sbp  dbp  on_bp_meds  med_classes
diabetes  ckd_albuminuria  clinical_cvd  egfr  potassium  contraindications
```

So the obvious idea — "state weight and height instead of BMI, make them compute
it" — **cannot move `extraction_f1` at all**. Verify any mechanism you invent
against this list before you build it.

---

## 5. Mechanisms worth trying, ranked

**(a) Give the readings, not the average — highest yield.** `sbp`/`dbp` are
extracted fields and are currently pre-averaged for the reader: *"167/66 mmHg
from 3 readings, averaged across outpatient visits"*. Give the three readings
instead and make the model do the averaging.

Two things to get right: HC-23 settled that the **mean** is correct (not the last
reading, not the second-and-third); and `renderer.display_bp` **floors** the mean
for display, with `evaluator` importing that same function so the two cannot
drift. Your raw readings must average to the same floored value the evaluator
compares against. Pin it with a test.

**(b) Temporal decoys on `potassium` and `egfr`.** A clearly-older value beside
the current one: *"potassium was 5.9 in March; today 4.0"*. The decision-relevant
value is unchanged; a careless reader takes the wrong number. **Make the decoy
provably non-decision-relevant** — the engine's value is always the one labelled
as current, and the decoy never crosses a threshold that would change the label.
Conservative call, and it needs a test asserting the engine label is unchanged.

**(c) Unit variation.** Creatinine in µmol/L, etc. Careful: creatinine is not an
extracted field, so this only helps where it touches `egfr` or `potassium`.

**(d) Burying values in narrative.** *"her pressure had been running in the 160s,
and today's average of three readings was no different at 167/66"*. Cheap to add,
probably weakest effect. Worth including but don't rely on it alone.

**Not yours: HC-51.** The hand-authored distractor library — *"her father took
lisinopril"* must **not** set a medication flag, *"stopped lisinopril after
angioedema"* must set a contraindication flag — is a separate ticket, is marked
**(Aria)**, and needs clinical judgement. It is what turns `hard` from "harder to
read" into "harder to reason about". Do not improvise it. `render()` already
takes a `distractors=` seam for it.

**Aria has no clinical background.** If you hit a question needing clinical
judgement, do not ask her to settle it: make the conservative call, write the
reasoning into the code, flag it for HC-49, and keep going.

---

## 6. Rebuilding the corpus invalidates the HC-57 signature

**Read this before you rebuild anything.**

HC-57 — the human facts-only gate — was signed on 2026-09-22, and the sign-off is
deliberately **bound to a specific build**: `docs/signoffs/HC-57_facts-only_spotcheck_signoff.md`
records the spot-check sheet's SHA-256 **and** the corpus manifest checksums,
and both were verified to match at signing.

Change the renderer and those checksums change. The signature no longer covers
the corpus you are running.

What that means in practice:

- the engine labels, splits and patient rows are **unchanged** — the engine reads
  the structured row, never the vignette — so only the vignette text moves;
- **the human read must be re-run on the levels you changed.** Regenerate the
  sheet with `tasks.spotcheck.build_spotcheck` (pass `profiles=` — without it the
  sheet silently skips contraindication coverage and prints a warning saying so),
  and take Aria a scoped re-read of the changed level rather than all 75 again;
- until she re-signs, your numbers are **provisional**, and the report generator
  will say so on its own — it reads the sign-off form rather than hardcoding the
  word.

Also: the build is **gated** on the leakage audit, not merely reported by it. A
corpus that fails is not written. Unit conversions and reworded values must not
introduce a forbidden token — run the suite, and read
`tasks/README.md` on the three checks before you touch the builder.

---

## 7. Step 2 — the measurement

Scope it tight. You are testing one thing: **does `extraction_f1` drop at `hard`?**

- **frontier arm only.** The open-weight arm abstained on 299/300 calls in the
  pilot, so it cannot inform an extraction question. `scripts/run_pilot.py run
  --only frontier` exists for exactly this.
- **k = 2, not 5.** One of 120 case-cells varied across five replicates in the
  pilot, so k = 5 buys nothing here. Decision D2 says "raise k if the pilot's SD
  is large"; the measurement says the opposite.
- 20 patients × 3 levels × 1 model × 2 replicates = **120 calls, roughly $6 and
  40 minutes** at the pilot's observed rates.

**Start a fresh record file.** `data/pilot/pilot_calls.jsonl` holds the completed
600-call run; appending a different corpus to it would silently mix two corpora
into one denominator. Move it aside, as the earlier retirements did — there is
precedent and a README convention in `data/pilot/`.

### What counts as success

K2's threshold, pre-registered and unchanged: it fires when `|simple − hard|` is
**< 5 pp on both** `decision_concordance` **and** `extraction_f1`. You want the
extraction spread to clear 5 pp. `experiments/kill_criteria.py` evaluates this as
code — **do not edit the thresholds**; they were signed before any result was
seen, and moving one to make a run pass is the precise failure the
pre-registration exists to prevent.

Be willing to report that your change did not work. A mechanism that moves
nothing is a real result and the next mechanism is cheap.

### What not to read

`citation_support` and `trace_concordance` are **not interpretable** — the model
is never told the anchor vocabulary or the rule names, so both measure guessing.
Filed as **HC-100**. Do not use them to judge your change, and do not put them in
a write-up.

---

## 8. Standing rules you inherit

- **You do not touch `engine/rules/`.** Aria hand-writes the guideline rules;
  everything else is built around them.
- **The hidden structured row never enters a request.** `ScriptedProvider`
  records every request so a test can assert it.
- **Two schemas, on purpose.** The API gets a stripped copy; validation is always
  against the full `llm_output.schema.json`. And note the standing obligation
  this run discovered the hard way: **any constraint stripped from the request
  copy must be restated in the prompt**, or you are scoring a model against a
  rule it was never given. `test_every_stripped_constraint_is_stated_in_the_prompt`
  enforces it; HC-100 is the same defect in the citation vocabulary.
- **Tests before implementation.** Watch them fail first.
- **Docs are bilingual pairs** — edit the `_zh` twin in the same commit. English
  wins on conflict.
- **Two synced trackers** — the Linear board `Generative AI in Medical` (`GAI-n`
  carrying `HC-n` in the title) and the Notion database `HTN-Concord — Progress
  Tracker`. Update both on every piece of progress. Notion rejects writes
  containing shell-command-looking strings; reword rather than retry.
- **Never hardcode test counts in documentation.** Write "run the suite".
- Search the backlog by symptom before filing a ticket — HC-96 was filed as a
  duplicate of HC-24 because that step was skipped.

---

## 9. Start here

1. Run the suite on the latest `main`. Confirm green.
2. Read `renderer/README.md` and the `hard` branch of `renderer/render.py`.
3. Read §4 again — check every mechanism you are considering against the twelve
   extracted fields before writing code.
4. Write the failing tests: the invariant test must still pass, and add one that
   pins whatever new indirection you introduce.
5. Implement (a), and (b) if (a) alone looks weak.
6. Rebuild the corpus. Regenerate the spot-check sheet with `profiles=` and take
   Aria a scoped re-read (§6).
7. Run the 120-call measurement (§7). Report the extraction spread against K2's
   5 pp threshold, plainly, including if it did not move.

---

## 10. Definition of done

`extraction_f1` at `hard` is measurably below `simple` by more than 5 pp on the
frontier arm — or a clear, measured statement that the mechanisms tried did not
achieve it and what the numbers were. Either way: the corpus rebuilt, the human
gate re-run on the changed levels, both trackers updated, and the kill criteria
untouched.
