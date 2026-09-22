# HTN-Concord — HC-80 pilot results and go/no-go verdict

**Run 2026-09-22. 600/600 calls completed, zero harness failures.**
**Verdict: GO-NARROWED.** Criteria pre-registered and signed 2026-09-20, before
any call — `HTN-Concord_Pilot_Kill_Criteria.md`. **Chinese pair:**
`HTN-Concord_Pilot_Results_2026-09-22_zh.md`.

HC-57 (human facts-only gate) was signed 2026-09-22, so these numbers are **not
provisional** on that account. They remain a smoke test for gross failure: the
analysis unit is the patient, n = 20, and the 95% CI half-width is roughly
±18 pp. "No kill" means no gross failure was detected, not that the benchmark
discriminates.

---

## 1. What was run

| | |
|---|---|
| Condition | C1 — rendered vignette, parametric memory, model's own arithmetic |
| Patients | 20, test split, stratified by engine decision (120 cases per decision class) |
| Levels | simple / moderate / hard |
| Frontier arm | `gpt-6-astra`, `reasoning_effort=high` |
| Open-weight arm | `deepseek-ai/DeepSeek-V4-Pro-0813` on Together, `reasoning_effort=high` |
| Replicates | k = 5 |
| Calls | **600/600 completed** |
| Cost | **$15.20** ($14.67 frontier, $0.53 open-weight) |
| Model time | 157 minutes |

---

## 2. Headline

Every concordance figure carries its majority-class baseline, per audit F1.

| model | level | concordance | baseline | staging | extraction F1 |
|---|---|---|---|---|---|
| gpt-6-astra | simple | **0.850** | 0.200 | — | 0.918 |
| gpt-6-astra | moderate | **0.850** | 0.200 | — | 0.918 |
| gpt-6-astra | hard | **0.850** | 0.200 | — | 0.918 |
| gpt-6-astra | *all* | **0.850** | 0.200 | 0.950 | 0.918 |
| DeepSeek-V4-Pro | simple | 0.200 | 0.200 | — | 0.923 |
| DeepSeek-V4-Pro | moderate | 0.190 | 0.200 | — | 0.932 |
| DeepSeek-V4-Pro | hard | 0.200 | 0.200 | — | 0.888 |
| DeepSeek-V4-Pro | *all* | **0.197** | 0.200 | 0.590 | 0.914 |

**Safety, reported separately and never folded into the headline:**
`unsafe_recommendation_rate` **0.000 on both arms**. Contraindication recall
1.000 (frontier) and 0.600 (open-weight), both **n = 15** — thin, exactly as
audit F2 predicted, and not a number to quote without that denominator.

---

## 3. ⚠️ The open-weight arm is degenerate, and it qualifies K3

**DeepSeek-V4-Pro answered `abstain` on 299 of 300 calls.** Its one other answer
was `lifestyle_only`.

Its 0.197 concordance is therefore not 20% of the task solved — it is the
fraction of cases where the engine *also* abstained (120/600 by construction of
the stratified sample). Correct-abstention 0.983, **over-abstention 1.000**: it
abstained on *every* case the engine answered.

This matters for what K3 established. K3 asks whether the corpus separates
models, and it did not fire — a 65 pp gap. But **the gap is between a model that
attempts the task and a model that declines it**, not between two models of
graded capability. The corpus demonstrably detects a non-participating model;
that is weaker evidence than a demonstration that it ranks two genuine attempts.

**The verdict is not adjusted for this.** The criteria were pre-registered
precisely so that results cannot move the thresholds, and K3's rule is a
point-estimate gap that did not fire. The caveat is recorded here instead, and
it carries one concrete action: **the full runs need a second arm that actually
attempts answers** before any claim about cross-model replication is made.

Worth noting: the extraction numbers show this is not incapacity. DeepSeek's
extraction F1 is **0.914**, statistically indistinguishable from the frontier
arm's 0.918. It reads the vignettes correctly and then declines to commit. Its
stated reasons ask for dose optimisation and compelling indications before
choosing an add-on class — it is answering "which drug class" when the task asks
"should therapy be intensified".

---

## 4. Failure modes

The pilot's own classifier, **not HC-71** — derived from evidence the evaluator
already produces so the pilot need not wait on a ticket it does not depend on.

| model | level | correct | correct but unsupported | extraction | reasoning | n |
|---|---|---|---|---|---|---|
| gpt-6-astra | simple | 15 | **70** | 15 | 0 | 100 |
| gpt-6-astra | moderate | 15 | **70** | 15 | 0 | 100 |
| gpt-6-astra | hard | 15 | **70** | 15 | 0 | 100 |
| gpt-6-astra | *all* | 45 | 210 | 45 | **0** | 300 |
| DeepSeek-V4-Pro | *all* | 0 | 59 | 162 | 79 | 300 |

> ### ⚠️ Correction — the `correct` / `correct but unsupported` split is not interpretable
>
> **Withdrawn 2026-09-22, after the table above was first written.**
>
> The split rests on `citation_support`, and that metric is not measuring what
> its name claims. **The model is never told the anchor vocabulary.** The system
> prompt does not mention citations at all, and the schema supplies exactly one
> example — `AHA-ACC-2025:stage2-initiate`.
>
> `gpt-6-astra` cited that one string **47 times and nothing else**. Those 47 are
> the entire `n` behind `citation_hallucination_rate`. The engine's other anchors
> (`bp-categories`, `bp-goal-130-80`, `normal-lifestyle`, …) are undisclosed, so
> the model had no way to produce them.
>
> `trace_concordance` (0.436) has the same defect. The engine uses four rule
> names (`bp_staging`, `initiation`, `intensification`, `scope`); the schema shows
> one (`bp_staging`); the model used that one on all 300 calls and invented the
> rest (`ckd_assessment`, `treatment_decision`, …).
>
> **Both metrics measure whether a model can guess an undisclosed vocabulary**,
> not whether it can support its answer or reproduce a reasoning path. This is
> the same class of defect as the `trace: minItems` one found earlier in this
> run: a contract enforced in scoring and never disclosed to the model.
>
> **So: the 210 "right but unsupported" is an artefact, not a finding.** For this
> run the frontier arm's table collapses to **correct 255 / extraction 45 /
> reasoning 0** out of 300, and the citation dimension is *not measurable*.
>
> **The verdict is unaffected.** K2 is defined on `decision_concordance` and
> `extraction_f1`, both of which are measurable; no criterion reads citation or
> trace. Fixing this is HC-38 / HC-44 (anchor registry and binding) plus
> disclosing the vocabulary to the model — filed as **HC-100**.

**One finding the frontier arm makes, and a single accuracy score could not.**

**Zero reasoning failures.** Every one of its 45 errors followed a misread
fact; not one followed a correctly-read one. On this corpus the frontier model's
errors are an *extraction* problem, not a clinical-reasoning problem — which is
the RQ2a/RQ2b question, and the one K2 has just made unanswerable here (§5).

---

## 5. Verdict against the pre-registered criteria

| | criterion | result |
|---|---|---|
| K1 | Both models ≥ 0.90 at all levels → ceiling | **not fired** (0.850 / 0.197) |
| K2 | \|simple − hard\| < 5 pp in concordance *and* extraction F1 | **FIRED** |
| K3 | \|frontier − open-weight\| < 5 pp at every level | **not fired** (65 pp) |
| K4 | Every arm within 5 pp of baseline | **not fired** (frontier +65 pp) |
| K5 | malformed > 5%, refusal > 2%, truncation > 1% | **not fired** (0.000 / 0.000 / 0.000, n = 600) |
| K6 | Median replicate SD > 0.05 | **not fired** (median 0.000) |

### VERDICT: **GO-NARROWED**

Per the rule fixed in advance: K2 fired alone, so proceed — but report the
affected research question as unanswerable on this corpus rather than quietly
dropping it.

**K2 in detail.** The difficulty ladder is flat to the point of being inert:

| | simple → hard, concordance | simple → hard, extraction F1 |
|---|---|---|
| gpt-6-astra | 0.850 → 0.850 (**0.0 pp**) | 0.918 → 0.918 (**0.0 pp**) |
| DeepSeek-V4-Pro | 0.200 → 0.200 (**0.0 pp**) | 0.923 → 0.888 (3.5 pp) |

The frontier arm's per-level failure-mode counts are *identical* across all three
levels (15 / 70 / 15 / 0 at each). The levels carry provably identical
decision-relevant information by design, and a model whose reading is unaffected
by presentation will score identically — which is what happened. **`hard` is not
harder.** RQ2a (how much error is reading rather than reasoning) and RQ2b (does
difficulty localise to extraction) **cannot be answered on this corpus** and must
be reported as such.

---

## 6. Decision D2 — k = 5 is too high

**1 of 120 case-cells varied across five replicates.** The frontier arm was
perfectly stable: 0 of 60 cells. The open-weight arm: 1 of 60.

Raw text differed on every replicate (verified: 86/86 cells byte-different,
identical decisions), so this is genuine run-to-run stability, not a cached
response.

**Recommendation: k = 2 for the full runs**, which retains a variance estimate
at 40% of the cost, with k = 5 kept for any condition where the pilot's stability
does not carry over (retrieval and tool conditions introduce non-determinism this
pilot did not exercise). D2 said "raise k if the pilot's SD is large"; the
measurement says the opposite, so the decision should be re-recorded rather than
left as written.

---

## 7. What this pilot does not establish

1. **n = 20 patients.** 95% CI half-width ≈ ±18 pp. Only gross effects are
   visible. A 65 pp model gap and a 0 pp level gap are both well outside that
   band; nothing else here should be read as an estimate.
2. **K3 rests on a degenerate arm** (§3). The corpus separates a participant from
   a non-participant. It has not been shown to rank two genuine attempts.
3. **Safety is not estimable** — `unsafe_recommendation_rate` is 0.000 on both
   arms, but contraindication recall has n = 15. Audit F2 already routed this to
   the HC-95 stress set; this run adds nothing to it.
4. **One frontier model, one open-weight model, one condition (C1).** No ladder
   delta is measured here.
5. **`citation_support` and `trace_concordance` are not interpretable** in this
   run (§4). Do not carry either row into a write-up until the anchor and
   rule-name vocabularies are disclosed to the model.
6. **The frontier arm cannot be version-pinned** — `gpt-6-astra` publishes no
   dated snapshot, so this run is reproducible from its transcripts but not
   necessarily re-runnable against the same weights.

---

## 8. Recommended next actions

1. **Rebuild the difficulty ladder (K2).** `hard` must impose a real extraction
   burden, or the three levels should collapse to one and RQ2a/RQ2b be dropped
   from the design honestly. This blocks the freeze.
2. **Add a third arm that attempts the task** (§3), from a different lab, before
   any cross-model replication claim.
3. **Re-record D2 at k = 2** (§6).
4. **Do not freeze yet.** §11's order is pilot → freeze → full runs, and the
   pilot has returned a corpus defect. Freezing now would freeze it in.
6. **Disclose the anchor and rule-name vocabularies to the model (HC-100)**, or
   stop reporting `citation_support` and `trace_concordance` entirely. Scoring a
   model against a vocabulary it was never given measures guessing.
7. Carry forward, unchanged: the harness is sound — 600/600 schema-valid on the
   first attempt, zero refusals, zero truncations, zero citation hallucinations.
