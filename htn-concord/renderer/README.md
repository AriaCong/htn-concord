# `renderer/` — vignette renderer (HC-50)

```python
from renderer import render
render(profile, level="moderate", seed=2026) -> str
```

Turns a hidden `PatientProfile` into facts-only clinical prose at three difficulty
levels. Deterministic and templated; no LLM is involved at any point.

## The three levels

| level | form | what makes it harder |
|---|---|---|
| `simple` | labelled lines, canonical order | nothing — every fact is handed over directly |
| `moderate` | one prose paragraph | facts embedded in sentences |
| `hard` | three paragraphs, seeded section order, inert filler | facts scattered and must be located |

**Difficulty changes presentation, never information.** All three levels carry the
same decision-relevant facts. This is deliberate and tested
(`test_every_level_carries_every_decision_relevant_value`): if `hard` withheld a
fact, a level-over-level accuracy drop would partly measure "the vignette did not
say", and the per-level breakdown the pilot (HC-80) turns on would be
uninterpretable. As built, a drop localizes to extraction.

## Facts-only

Rendered: BP, creatinine, eGFR, potassium, UACR, HbA1c, lipids, BMI, named drugs,
history, pregnancy, the angioedema *event*.

Never rendered: `bp_stage`, `prevent_10yr`, `ckd_albuminuria`, or any
`contraindications` flag as a flag. Those are engine determinants; the model must
re-derive them. Nothing becomes unanswerable, because every raw input is present —
PREVENT's inputs are rendered individually, and hyperkalemia arrives as a potassium
number.

Every call self-checks against `leakage.scan` before returning, so a template edit
that introduces a label-bearing token fails at render time.

## Two details that are correctness, not style

**Drug names.** A profile records `med_classes: ["acei"]`, never a prescription.
The vignette may not say "an ACE inhibitor" (that is the recommendation
vocabulary), so it names a drug: "lisinopril". Every exemplar in
`phrasing.CLASS_EXEMPLARS` classifies back through `vocab.classify_drug` to exactly
its own class, which makes the substitution lossless. Drug choice is seeded off the
*case*, not the level, so one patient does not take ramipril in the simple vignette
and lisinopril in the hard one.

**BP is floored, not rounded.** NHANES BP is a mean, so profiles carry values like
`131.667`. Rounding would be a correctness bug: 129.6 rounds to 130 and crosses the
Stage-1 threshold, showing the model a BP one stage above its own hidden label. On
the real corpus, rounding would have corrupted **93 of 4,806 profiles**. Flooring
corrupts zero, and provably cannot: every staging threshold is an integer, and no
integer lies in `(floor(v), v]`.

> **Handoff to HC-70:** extraction scoring must compare a model's extracted SBP to
> the *displayed* (floored) value, not the raw profile float, or every case with a
> fractional mean counts as an extraction miss.

## Not built here

The `hard` filler is clinically inert (visit logistics only). Decision-relevant
traps — "stopped lisinopril after angioedema" vs "her father took lisinopril" — are
**HC-51**, hand-authored and clinician-validated, and plug in via a `distractors=`
hook. Until then, `hard` is *harder to extract from*, not *harder to reason about*.
