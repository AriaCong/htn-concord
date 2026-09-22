# HC-101 — `hard`-level re-read: scoped sign-off form

**Ticket:** HC-101 (Linear `GAI-` board / Notion progress tracker) · **Gate:**
Phase-4 acceptance, human half, re-run for one changed level · **Reviewer:** Aria
Cong · **Prepared:** 2026-09-22 · **Language:** English only — internal working
form, not one of the bilingual project documents

**Supersedes, for the `hard` level only:**
`docs/signoffs/HC-57_facts-only_spotcheck_signoff.md` (signed 2026-09-22).

---

## Why you are being asked again

HC-57 was signed against a specific corpus build, and the signature is bound to
its checksums on purpose. The HC-80 pilot then fired kill criterion **K2**: the
difficulty ladder was inert — extraction F1 was 0.918 at `simple`, `moderate`
*and* `hard`, to three decimals, with identical per-field counts at every level.
`hard` reordered paragraphs and added visit-logistics filler, which costs a
reader nothing while every fact stays in the same sentence with the same label
and units.

HC-101 changed the `hard` renderer to fix that. The corpus was rebuilt, so
`task_b_inputs.jsonl` now hashes differently and your previous signature no
longer covers what the experiment will run against.

**Engine labels, splits and patient rows did not move.** The engine reads the
hidden structured row and never sees a vignette, so only vignette text changed.
The rebuild confirms it: `task_b_labels.jsonl` hashes to `f9bd3589…` exactly as
before, and the decision distribution and split sizes are unchanged.

## This re-read is 25 vignettes, not 75

Only the `hard` level changed. That is machine-verified, not assumed: rendering
all **4,806** patients under the previous renderer and the current one gives
**byte-identical** `simple` and `moderate` text for every single patient, and
differing `hard` text for 4,805 of them. (The one unchanged `hard` vignette is
patient 100963, who has a single BP reading and no potassium, so both new
mechanisms correctly fall back to the old wording.)

Your `simple` and `moderate` marks from HC-57 therefore still stand and are
carried over. **Read only the `hard` vignette for each of the 25 patients.**

## The sheet

```
htn-concord/data/tasks/task_b/spotcheck_hc101_2026-09-22.md
```

Not in git, and **must not be committed, pasted into Notion, or uploaded**: it
holds patient-level rows and the hidden answer key side by side. Read it in a
local editor.

Generated with `profiles=` supplied, so the contraindication stratum is included
(the sheet says so in its own header when it is; it prints a warning when it is
not).

## What changed in `hard`, in plain terms

Two things, both of which put a number on the page that is *not* the number the
answer key holds. Both are deliberate.

**1. Blood pressure is given as the individual readings, not the average.**

- before: `Blood pressure was 155/66 mmHg from 3 readings, averaged across …`
- now: `Blood pressure was measured 3 times at outpatient clinic visits over the
  past year: 150/69, 158/69, and 157/60 mmHg.`

The readings always average to exactly the value the other two levels state.
**You do not need to check that arithmetic** — it is pinned by tests that run on
every build, and separately verified across the whole corpus.

**2. An older potassium is stated beside the current one.**

- before: `potassium 4.3 mmol/L`
- now: `potassium 4.3 mmol/L today, up from 3.3 mmol/L when last checked in the
  spring`

The current value is always the one labelled `today`.

## What to check, per `hard` vignette

Exactly the same standard as HC-57 — this gate is still only *does the vignette
give the answer away?* A vignette fails if it:

- names a **BP stage** ("stage 2 hypertension", "hypertensive", "elevated blood pressure");
- states or implies a **treatment decision**;
- names a **drug class** as a recommendation (a drug the patient already takes,
  by name, is a fact and is fine);
- says anything that **implies the answer**, including through ordering, emphasis,
  or a clinician-sounding aside.

**Two things to look at specifically this time**, because they are new wording:

- **The prior-potassium clause.** It should read as a bare previous measurement.
  Flag it if it reads as a *comment* on the patient — anything trending,
  reassuring, or concerning ("improved", "still elevated", "down to a safer
  level"), rather than a value and a date.
- **The readings sentence.** Flag it if it singles out one reading as the
  important one, or otherwise hints which number matters.

> **If a phrasing makes you hesitate, flag it.** The hesitation is the finding —
> don't try to decide whether it is "really" leakage.
>
> You do **not** need to judge whether any value is clinically plausible or
> whether the hidden label is clinically right. That is HC-49, not this gate.
> The choice to put a prior potassium on the page at all, and the bounds it is
> generated within, were a conservative call recorded in the code and referred to
> HC-49 — not something this form asks you to ratify.

---

## Per-patient record — `hard` only

`OK` = facts only. `FLAG` = something to look at (then write it below).

| # | hard | note |
|---|---|---|
| 1 | ☐ | |
| 2 | ☐ | |
| 3 | ☐ | |
| 4 | ☐ | |
| 5 | ☐ | |
| 6 | ☐ | |
| 7 | ☐ | |
| 8 | ☐ | |
| 9 | ☐ | |
| 10 | ☐ | |
| 11 | ☐ | |
| 12 | ☐ | |
| 13 | ☐ | |
| 14 | ☐ | |
| 15 | ☐ | |
| 16 | ☐ | |
| 17 | ☐ | |
| 18 | ☐ | |
| 19 | ☐ | |
| 20 | ☐ | |
| 21 | ☐ | *supplementary — rare abstain mechanism* |
| 22 | ☐ | *supplementary — rare abstain mechanism* |
| 23 | ☐ | *supplementary — contraindication flag* |
| 24 | ☐ | *supplementary — contraindication flag* |
| 25 | ☐ | *supplementary — contraindication flag* |

## Flagged phrasings

| # | phrase | why it made you hesitate |
|---|---|---|
| 5 vignettes (patients 96754, 101393, 100388, 95492, 102866) | "She also takes a statin for cholesterol." | the sheet's header said a vignette fails if it "names a drug *class*", and `statin` is a class rather than a drug name |

### Adjudication of the `statin` flag — resolved PASS, 2026-09-23

**The reviewer was right to stop, and the sheet was wrong.** Two artifacts stated
two different standards:

| | wording |
|---|---|
| this form | "names a drug class **as a recommendation** (a drug the patient already takes, by name, is a fact and is fine)" |
| the generated sheet | "nothing … names a drug *class*" — the qualifier was dropped |

The reviewer read the sheet. Against that wording the corpus provably cannot
pass, because five vignettes must say `statin`.

**Resolved: `statin` is not leakage, on three independent grounds.**

1. **It is not in the recommendation vocabulary.** `vocab.MED_CLASSES` is nine
   antihypertensive classes (thiazide, acei, arb, dhp_ccb, nondhp_ccb,
   beta_blocker, loop_diuretic, mra, alpha_blocker). `recommendation.drug_classes`
   is schema-bound to those, so the engine can never recommend a statin and
   naming one cannot disclose the answer.
2. **It is a required input.** `statin_use` is a PREVENT term (`statin` and
   `non_hdl_x_statin`). Withholding it would make the 10-year risk incomputable
   and every Stage-1 case unanswerable — a worse failure than the one being
   guarded against.
3. **The scanner agrees**: 0 token hits across all 14,418 cases.

The contrast is the point: the vignette says "lisinopril" rather than "an ACE
inhibitor" *because* ACEI is recommendation vocabulary. "A statin" is safe for
exactly the reason ACEI is not.

**Fixed at source**, so no future reviewer hits this: the sheet generator now
states the same standard as this form, pinned by
`test_sheet_states_the_same_drug_class_standard_as_the_signoff_form`. The sheet
already read was deliberately **not** regenerated, so its checksum below still
matches what was reviewed.

**The reviewer's other two calls are confirmed correct** and needed no change:

- **Pregnancy** ("currently pregnant, in the second trimester", patients 96497
  and 93929) — PASS. It is a raw patient fact, and the renderer states the
  *event* rather than its interpretation by design. Withholding it would make
  the pregnancy rule path untestable, which is the same failure as (2) above.
- **Visit logistics** ("a follow-up appointment was arranged", "routine
  follow-up", "outside records were requested") — PASS. Clinically inert by
  construction and distributed across decision groups, so it cannot be
  specifically informative.

**Outcome: 25/25 PASS, no leakage found.**

---

## Sign-off

> I have read the 25 `hard` vignettes on the sheet named above and confirm that
> each states only raw facts, with every hesitation recorded in the table above.
> I understand that my HC-57 marks for `simple` and `moderate` are carried over
> unchanged, on the verified basis that neither level's text moved.

- **Signed:**
- **Date:**
- **Sheet checksum:**
  `cf31e5a69322916a36518d88046cad8c078a4acaeb2843e0a839bae6ae8a7b6b`
  (generated deterministically; if your copy's SHA-256 differs, it is not the
  sheet this form signs off)
- **Corpus this signature binds to:** `task_b_inputs.jsonl`
  `4adfe54c70ba7e142ea5fe8c121fec2f6bd411e4f8db872ef7c011444f283f14`,
  `task_b_labels.jsonl`
  `f9bd3589fceab13eabe672f8a09179d1594fee8349c1b363c1a6fe6dadabe125`,
  14,418 records each
- **Outcome:** ☐ pass, no flags ☐ pass with flags recorded ☐ fail — corpus needs a renderer fix

**Reviewer's statement:**

>

---

## Status until this is signed

**Every HC-101 measurement number is provisional and labelled so.** The report
generator reads the sign-off form rather than hardcoding the word, so this is
not a thing anyone has to remember to do by hand.
