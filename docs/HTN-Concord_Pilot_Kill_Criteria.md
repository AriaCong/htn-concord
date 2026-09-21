# HTN-Concord — HC-80 pilot kill criteria (pre-registered)

**Written 2026-09-20, BEFORE any pilot result existed.** Nothing in this document
was chosen after seeing a number. That is the whole point of it: a gate whose
criteria are written afterwards is not a gate, because whatever came out can be
rationalised into a pass.

**Status:** ✅ **signed by Aria 2026-09-20**, approved as written, before any pilot
call was made. **Chinese pair:** `HTN-Concord_Pilot_Kill_Criteria_zh.md`.

**Companions:** `HTN-Concord_Experiment_Design.md` §11 (order of execution), §4.4
(replicates), §9 (open decisions D2/D3), `HTN-Concord_Backlog.md` HC-80.

---

## 1. What the pilot is for

One question: **does this corpus tell two models apart?**

Everything downstream — the drug-class rules, retrieval (C2), tools (C3), the
guideline graph (C3g), the whole MIMIC arm (C4) — is worth building only if the
answer is yes. The pilot exists to make "no" cheap to discover, and the project
has committed in writing to acting on a "no".

**Pilot numbers are not results.** They inform a go/no-go and nothing else. They
do not go into a paper, a figure, or a Notion page without the word
*provisional* attached.

> **HC-57 closed 2026-09-22.** Aria reviewed all 75 vignettes and signed:
> *"PASS: 75/75 vignettes reviewed; no vignette explicitly states or implies the
> hidden BP stage, treatment decision, or recommended antihypertensive drug
> class."* No flags, so no new forbidden tokens and no renderer fix. Verified at
> sign-off that the sheet still hashes to the value on the sign-off form and that
> the corpus manifest is unchanged, so the signature binds to the exact build the
> pilot runs against. The Phase-4 acceptance gate is now closed on both halves —
> the scanner (zero hits on 14,418 cases) and the human read. Pilot numbers
> remain provisional in the ordinary sense (they are a smoke test, §6), but no
> longer *doubly* so.

---

## 2. Scope, resolved

Two project documents disagreed, and the conflict is resolved here in favour of
the backlog. See §7 for the reasoning and the doc changes.

| | |
|---|---|
| Condition | **C1 only** (rendered vignette, parametric memory, model's own arithmetic) |
| Patients | **20**, drawn from the **test** split, stratified by engine decision |
| Levels | **all three** — simple, moderate, hard |
| Models | **2** — frontier `gpt-6-astra`, open-weight `openai/gpt-oss-120b` on Groq (D3). Both OpenAI — see the same-lab limitation in §6.4 |
| Replicates | **k = 5** per case per model (design §4.4) |
| Total calls | **20 × 3 × 2 × 5 = 600** |

---

## 3. What is measured

Every number below is `decision_concordance` unless named otherwise, computed by
`evaluator.score` — pure functions, no LLM judging anything.

**Every concordance figure is reported beside its `majority_class_baseline`.**
The aggregation layer emits it in the same dict and it is not stripped when the
table is written. On the test split a model that answers `lifestyle_only`
unconditionally scores **0.515**; a headline of "72%" means nothing without that
number next to it.

> **The pilot's baseline is not 0.515, and that is correct.** The pilot's 20
> patients are *stratified by engine decision*, so the sample is far more balanced
> than the split it is drawn from and its majority-class baseline lands nearer
> 0.2. K4 is evaluated against **the pilot sample's own baseline**, computed from
> the labels actually scored — not against the test split's. Comparing a pilot
> concordance to 0.515 would be comparing it to a baseline from a different
> sample. Verified on a dry run of the real corpus: a constant `lifestyle_only`
> predictor scored 0.167 against a printed baseline of 0.333 and the gate
> correctly returned **STOP**.

Also reported, per model and per level: `extraction_f1`, `staging_correct`, the
two abstention rates over their own denominators, `unsafe_recommendation_rate`
(separately, never folded into the headline), across-replicate SD, and the three
harness outcomes below.

---

## 4. The criteria

Each is a threshold the project could lose on. `pp` = percentage points.
"Both models" means the frontier arm and the open-weight arm.

### K1 — Ceiling: no headroom to measure anything

> Both models score **≥ 0.90** mean `decision_concordance` at **all three** levels.

If every model already answers nine in ten correctly at the hardest level, no
later condition can demonstrate repair — C2 (retrieval) and C3 (tools) exist to
fix errors that would no longer exist. **Consequence: STOP and make the corpus
harder** before building any ladder condition.

### K2 — Flat ladder: difficulty does not do what it was designed to do

> Pooled across models, **|simple − hard| < 5 pp** in `decision_concordance`
> **and** **< 5 pp** in `extraction_f1`.

The three levels are built to carry provably identical decision-relevant
information and differ only in how hard it is to *read out*. If hard is no harder
than simple on either measure, the renderer is not creating an extraction burden
and **RQ2a/RQ2b cannot be answered**. **Consequence: STOP and rebuild the
difficulty ladder** (the extraction measure is the more diagnostic of the two —
if `extraction_f1` is flat, the difficulty is cosmetic).

### K3 — Models indistinguishable

> **|frontier − open-weight| < 5 pp** at **every** level.

This is §11's "frontier ≈ open-weight everywhere". If the corpus cannot separate
two models of very different capability, it is not measuring capability, and the
design's "a failure mode is a finding only if it replicates across models" bar
becomes untestable — there is nothing to replicate. **Consequence: STOP and
diagnose** before scaling.

### K4 — Floor: the task is broken, not hard

> Both models score **≤ majority_class_baseline + 5 pp** at every level.

**§11 does not list this one**, and it should: it is the mirror image of K1 and
equally fatal. A benchmark on which nothing beats answering `lifestyle_only`
unconditionally is not a hard benchmark, it is a broken one — a malformed prompt,
a mis-specified schema, or a task the vignette cannot support. **Consequence:
STOP and debug the instrument.** This is not a corpus-difficulty finding.

### K5 — Instrument unusable (fix first, not a corpus verdict)

> `malformed_output_rate` **> 5%** after retries on either model, **or**
> `refusal_rate` **> 2%**, **or** `truncation_rate` **> 1%**.

These measure *our harness*, not the corpus. A refusal is the model declining a
clinical question — a real finding on a clinical benchmark, and reported as its
own rate rather than pooled into malformed output. Truncation is our `max_tokens`
ceiling and is our defect outright. **Consequence: FIX and re-run the pilot.** K5
does not produce a corpus verdict, and K1–K4 are not read until K5 passes,
because numbers from a broken instrument are not evidence.

### K6 — Replicate variance too high for k = 5 (informs D2)

> Median across-replicate SD of case-level `decision_concordance` **> 0.05**.

Design decision D2 fixes k = 5 provisionally and says to raise it if the pilot's
SD is large. This is the threshold that makes "large" mean something.
**Consequence: raise k for the full runs** and record the new value in the
freeze. Not a stop condition.

---

## 5. The verdict rule, fixed in advance

Read in this order:

1. **K5 fails** → verdict **FIX-FIRST**. Repair the harness, re-run, then read on.
2. **K4 fails** → verdict **STOP (instrument)**.
3. **K1 and K2 both fail** → verdict **STOP (corpus too easy)**.
4. **K3 fails** → verdict **STOP (no discrimination)**.
5. **K1 or K2 fails alone** → verdict **GO, narrowed** — proceed, but the
   affected research question (RQ2a/RQ2b for K2) is reported as unanswerable on
   this corpus rather than quietly dropped.
6. Otherwise → verdict **GO**.

K6 is reported in every case and changes k, not the verdict.

---

## 6. What this pilot cannot do, stated up front

**20 patients cannot support an estimate, only a smoke test.** The analysis unit
is the patient (three levels of one patient are not independent), so the
effective n for any headline is **20**, not 300 and not 600. Around a proportion
of 0.8 the 95% CI half-width at n = 20 is roughly **±18 pp**.

Three consequences, and they are not hedges — they change how the verdict may be
read:

1. **A 5 pp threshold is far inside the noise.** These criteria are written to
   catch **gross** failure — a ladder that is flat, a ceiling that is total, two
   models that are identical. They are deliberately point-estimate rules, not
   significance tests, because a significance test at n = 20 would never fire.
2. **"No kill" means "no gross failure was detected."** It does not mean the
   benchmark discriminates. Only the full runs (HC-81) can establish that.
3. **A kill verdict is the more trustworthy of the two.** If a difference is
   invisible even at this sample size, it is genuinely small. Passing is weak
   evidence; failing is strong evidence. The gate is asymmetric on purpose.

4. **Both arms now come from the same lab, which weakens what a replication
   means.** The frontier arm is `gpt-6-astra` and the open-weight arm is
   `openai/gpt-oss-120b` — both OpenAI. The design reports a failure mode as a
   finding only if it **replicates across models**, and the purpose of that rule
   is to exclude single-model quirks. Two models sharing a lab, and plausibly
   sharing pretraining data and post-training methodology, can share a quirk —
   which would replicate across both arms and read as a mechanism finding when it
   is a lab-level artefact. K3 is affected in the same direction: if the two arms
   agree closely, "the corpus cannot separate models" and "these two models are
   siblings" are not distinguishable from this pilot.

   This does not invalidate the pilot — the capability gap between a frontier
   model and a 120B open-weight model is real, and that gap is what K3 measures.
   But **the cross-model replication bar is not met by this pair**, and any RQ2
   mechanism claim resting on "it replicates across models" needs a third arm
   from a different lab before it can be made. Recorded here rather than
   discovered at review. Different-lab candidates with structured-output support:
   `deepseek-ai/DeepSeek-V4-Pro-0813` (which also carries a dated snapshot),
   `moonshotai/Kimi-K3`, `zai-org/GLM-5.3`.

CIs are reported beside every pilot number (patient-level cluster bootstrap,
B = 2000 per design §4.2–4.3) so this is visible rather than asserted.

---

## 7. The scope conflict, resolved

The backlog said **20 cases × 3 difficulties × 2 models**. Experiment Design §11
said **C1, moderate level only, 20 patients × 2 models**.

**§11 was internally inconsistent**: it specified moderate-only and then stated
the kill criterion as *"all difficulties near ceiling"* — which a moderate-only
run cannot evaluate, because it produces exactly one difficulty. One of the two
statements had to give.

**Resolved in favour of all three levels (the backlog's scope):**

1. The criteria §11 itself states (K1, and the ladder question K2) require more
   than one level to evaluate. Keeping moderate-only would leave the stated gate
   unevaluable — the document would define a test it had made impossible to run.
2. The pilot's purpose is to decide whether the *difficulty ladder* works.
   Running one rung cannot answer that, and the ladder is what RQ2a/RQ2b rest on.
3. The cost is not the constraint. Three levels is 600 calls rather than 200 —
   tens of dollars, against the alternative of discovering after the freeze that
   the ladder is flat and re-running everything.

§11's moderate-only wording is corrected in the same commit as this document,
together with `HTN-Concord_Backlog.md` HC-80 and both `_zh` twins.

---

## 8. Sign-off

Signing means: these criteria are the ones the pilot will be judged against, and
the verdict they produce will be accepted — **including if it is *stop***.

- **Criteria approved by:** Aria Cong
- **Date:** 2026-09-20 — before the first pilot call
- **Approved:** as written, including the §6 framing that this pilot is a smoke
  test for gross failure and that "no kill" does **not** mean the benchmark
  discriminates
- **Frontier arm:** `gpt-6-astra`. Changed from `claude-opus-5` on 2026-09-20
  (see the change log below); the change was made before any pilot call, and
  altered no criterion, threshold or verdict rule
- **Open-weight arm (D3):** `openai/gpt-oss-120b` served by Groq, chosen by Aria
  2026-09-22. Reasoning effort pinned at `high` and recorded per call, matching
  the frontier arm. The decision to use a *hosted frontier-class open-weight*
  model rather than a small local one is Aria's, taken so that K3 is a real test
  rather than one a weak model passes trivially. **Known limitation of this
  specific pairing: both arms are OpenAI models — see §6.4**
- **Deviations agreed at sign-off:** none

*Any change to this document after the first pilot call is made must be recorded
here with its reason and its date, not edited silently.*

| Date | Change | Reason |
|---|---|---|
| 2026-09-20 | Created | Pre-registration before any call |
| 2026-09-20 | Signed by Aria, approved as written; D3 resolved to a hosted open-weight arm | Sign-off obtained before any pilot call, per HC-80 |
| 2026-09-22 | **Open-weight arm set to `openai/gpt-oss-120b` on Groq.** Aria's choice. Pre-call. Reasoning effort pinned at `high` to match the frontier arm, since leaving it at a host default would have made this arm the only unrecorded variable in the comparison. **Limitation recorded in §6.4 rather than absorbed: both arms are now OpenAI models, so the design's "replicates across models" bar is not met by this pair** — a lab-level quirk would replicate across both and read as a mechanism finding. A third arm from a different lab is needed before any such claim | Requested choice of the second arm |
| 2026-09-20 | **Frontier arm changed from Claude (`claude-opus-5`) to OpenAI (`gpt-6-astra`).** Aria's request. **Pre-call amendment — no pilot call had been made**, so this is not a protocol deviation. No threshold, criterion or verdict rule changed; K3 still compares the frontier arm against the open-weight arm. Two consequences recorded rather than absorbed silently: (a) the frontier arm **publishes no dated snapshot id**, so it cannot be version-pinned — the id the API reports is recorded per call, which makes a silent model change detectable after the fact but not preventable, and this belongs in the manuscript's reproducibility section; (b) the pinned effort knob is now `reasoning_effort=high` rather than Anthropic's `effort=high` — comparable in role, not identical in meaning, so it is recorded per call as before | Requested change of what the experiment compares |
