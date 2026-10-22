# HC-101 — rebuilding the difficulty ladder: measured result

**Run 2026-09-23.** Frontier arm only (`gpt-6-astra`), 20 patients × 3 levels × 2
replicates = **120 calls, 120/120 schema-valid**, no refusals, no truncations.

> **PROVISIONAL.** No signed facts-only sign-off names this corpus build. The
> `hard` re-read (`docs/signoffs/HC-101_hard-level_rereview_signoff.md`) is
> prepared but unsigned. The report generator determines this itself by matching
> the corpus SHA-256 against the sign-off forms; it is not a label anyone has to
> remember to apply.

---

## 1. The headline: the mechanisms did not work

**Extraction F1 is identical at all three levels, to four decimal places.**

| | simple | moderate | hard |
|---|---|---|---|
| `extraction_f1` | **0.9182** | **0.9182** | **0.9182** |
| `decision_concordance` | 0.8500 | 0.8750 | 0.8500 |

**K2 spread, `|simple − hard|`: 0.00 pp on extraction.** The pre-registered
threshold is 5 pp. **K2 fired again.** Verdict: **GO-NARROWED**, unchanged.

`experiments/kill_criteria.py` was not modified. Nothing about the threshold was
touched, and this result is reported as it came out.

## 2. The mechanisms were present and were handled perfectly

This is not a case of a change that failed to reach the corpus. Both mechanisms
were in every `hard` vignette the model saw, and the model handled both without
a single error.

| vignette stated | correct mean | model answered |
|---|---|---|
| 137/83, 127/82, 123/75 | 129/80 | **129/80** ✓ |
| 152/95, 142/96, 153/88 | 149/93 | **149/93** ✓ |
| potassium 4.4 today, up from 5.3 | 4.4 | **4.4** ✓ |

Per-field, at `hard`: **sbp 40/40, dbp 40/40, potassium 38/38.** Zero misses on
every field either mechanism targeted, at every level.

The corpus itself was verified independently of the model run: across all 4,796
`hard` vignettes carrying a readings sentence, **zero** fail to average to the
displayed value and **zero** print the mean as one of the readings; across all
4,538 carrying a potassium decoy, **zero** cross the hyperkalemia threshold.

## 3. Per-field, all three levels

| field | simple | moderate | hard |
|---|---|---|---|
| age | 40/40 · 1.000 | 40/40 · 1.000 | 40/40 · 1.000 |
| sex | 40/40 · 1.000 | 40/40 · 1.000 | 40/40 · 1.000 |
| **sbp** | 40/40 · 1.000 | 40/40 · 1.000 | **40/40 · 1.000** |
| **dbp** | 40/40 · 1.000 | 40/40 · 1.000 | **40/40 · 1.000** |
| **potassium** | 38/38 · 1.000 | 38/38 · 1.000 | **38/38 · 1.000** |
| egfr | 38/38 · 1.000 | 38/38 · 1.000 | 38/38 · 1.000 |
| ckd_albuminuria | 38/38 · 1.000 | 38/38 · 1.000 | 38/38 · 1.000 |
| med_classes | 40/40 · 1.000 | 40/40 · 1.000 | 40/40 · 1.000 |
| contraindications | 40/40 · 1.000 | 40/40 · 1.000 | 40/40 · 1.000 |
| on_bp_meds | 36/40 · 0.900 | 36/40 · 0.900 | 36/40 · 0.900 |
| diabetes | 6/38 · 0.158 | 6/38 · 0.158 | 6/38 · 0.158 |

The per-field counts are **identical across levels**, exactly as in the HC-80
pilot. Nine of eleven fields are at ceiling everywhere. The two that are not —
`diabetes` and `on_bp_meds` — fail *level-invariantly* and for reasons unrelated
to difficulty; `diabetes` is **HC-102** (the vignette never states a negative
finding while the evaluator scores it).

## 4. What this actually establishes

The HC-80 pilot showed the ladder was flat. It was reasonable to read that as
"the manipulations were too weak." This run rules that reading out for the
strongest manipulations available within the renderer.

**Presentation-only difficulty does not create an extraction burden for a
frontier model.** Making it average three three-digit integers and bind a value
to the label "today" cost it exactly nothing: 118 of 118 scored opportunities.
The bottleneck was never how the fact is packaged. It is that *no repackaging of
a stated fact is hard for this model*.

That is a stronger and more useful finding than "we need bigger filler", because
it says where the remaining budget should not go. Mechanisms (c) unit variation
and (d) narrative burying are weaker than what was just tried, on the same axis,
against a model that scored 100% on that axis. They should not be attempted.

**The implication for the design: HC-51 is the critical path, not an
enhancement.** The distinction that matters is not *how much work to recover a
stated fact*, but *what has to be judged*. "Her father took lisinopril" must not
set a medication flag; "stopped lisinopril after angioedema" must set a
contraindication flag. Those change what the reader must decide, not how far
they must read. HC-51 is hand-authored and clinician-validated by design
(Aria's), and this result is the evidence that it is load-bearing.

**RQ2a and RQ2b remain unanswerable on this corpus**, as the HC-80 report
already stated, and the pre-registration freeze (HC-94) remains blocked on the
same grounds: Experiment Design §11 orders pilot → freeze → full runs, and the
corpus defect is not repaired.

## 5. What is nonetheless kept

The renderer work is not wasted even though it moved no number:

- **The `hard` level is now genuinely non-trivial to read**, and it will matter
  for any weaker model. The open-weight arm's extraction already fell 0.923 →
  0.888 across levels in the HC-80 pilot, so the levels are not inert for every
  model — only for this one.
- **The information invariant is now checked in a stronger form.** BP moved from
  a substring proxy to `test_bp_is_exactly_recoverable_at_every_level`, which
  recomputes the mean of the stated readings and asserts it equals the engine's
  displayed value. That catches a class of defect the substring check never could.
- **The averaging convention is disclosed in the prompt**, closing an HC-100-class
  hole before it produced an uninterpretable number rather than after.
- **The human gate is now bound to the corpus it signs.** `hc57_signed` asked only
  whether a signed marker existed, so a signed form plus a rebuilt corpus read as
  "gate closed". Confirmed live: against this corpus the old check still returned
  `True`. It is replaced by `human_gate_closed`, and the PROVISIONAL banner at the
  top of this document is that fix working.

## 6. Comparability

Absolute rates here are **not comparable** to the HC-80 pilot's. Two frozen
artifacts changed: the corpus (`task_b_inputs.jsonl` `6bf0fa69…` → `4adfe54c…`)
and the system prompt. Per Experiment Design §2, a change to a frozen artifact
retires every run made under it; the 600-call HC-80 record file was retired to
`data/pilot/retired_hc80-pilot-corpus-v1.jsonl` with its reasons.

K2 is a **within-run** comparison — simple vs hard under one corpus and one
prompt — which is preserved, and is what this document reports.

That extraction F1 came out at 0.9182 here and 0.918 in HC-80 is a coincidence
worth explaining rather than leaning on: nine of eleven fields sit at ceiling in
both runs, and the same two level-invariant fields fail in both, so the same
patients produce the same number. It is not evidence of comparability, and
should not be quoted as a before/after pair.

## 7. Recommendations

1. **Do not spend further budget on presentation-level difficulty.** Measured:
   the highest-yield mechanisms available moved the metric 0.00 pp.
2. **Promote HC-51 to the blocking item for RQ2a/RQ2b.** It is the only
   remaining mechanism that changes what must be judged rather than how much must
   be read, and it needs a clinician.
3. **Fix HC-102 before quoting any absolute extraction number.** `diabetes=False`
   is never rendered but is scored, costing ~7.6 pp at every level. It does not
   affect K2, which is a difference, but it makes the absolute figure an
   understatement of the model.
4. **Keep the freeze blocked.** The corpus defect K2 names is not repaired.
5. **Finish HC-103.** Two silent stalls (3h14m, then 73m) cost most of a day on a
   40-minute measurement. The per-call timeout is now bounded; the run loop still
   has no heartbeat.

---

## Appendix — run provenance

- corpus: `task_b_inputs.jsonl` `4adfe54c70ba7e142ea5fe8c121fec2f6bd411e4f8db872ef7c011444f283f14`,
  `task_b_labels.jsonl` `f9bd3589fceab13eabe672f8a09179d1594fee8349c1b363c1a6fe6dadabe125`
  (labels **unchanged** from the HC-80 build), 14,418 records each
- leakage audit at build: passed, 0 token hits, 0 label-column hits, 14,418 cases
- spec: `PilotSpec(n_patients=20, levels=3, replicates=2, split="test", seed=80)`
- outcomes: 120 ok, 0 refusal, 0 truncated, 0 malformed
- `citation_support` and `trace_concordance` are **not reported**: the model is
  never given the anchor vocabulary or the rule names, so both measure guessing
  (HC-100).
