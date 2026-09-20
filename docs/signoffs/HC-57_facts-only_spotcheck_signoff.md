# HC-57 — human facts-only spot-check: sign-off form

**Ticket:** HC-57 (Linear `GAI-` board / Notion progress tracker) · **Gate:** Phase-4
acceptance, human half · **Reviewer:** Aria Cong · **Prepared:** 2026-09-20 · **Language:** English only — this is an internal
working form, not one of the five bilingual project documents

---

## What this gate is

The corpus build already runs a mechanical leakage audit on all 14,418 cases and
passes with zero hits. **A scanner only catches the tokens it was told about.** This
gate catches a vignette that gives the answer away in wording nobody thought to ban —
which only a reader can see.

Until this form is signed, **every pilot number is provisional** and must be labelled
so wherever it appears.

## The sheet

Open the generated sheet locally:

```
htn-concord/data/tasks/task_b/spotcheck_hc57_2026-09-20.md
```

It is **not** in git and **must not be committed, pasted into Notion, or uploaded
anywhere**: it contains patient-level rows *and* the hidden answer key side by side.
It is the one artifact in the project that deliberately shows both. Read it in a
local editor.

**25 patients × 3 difficulty levels = 75 vignettes.** Each patient appears once, with
its `simple`, `moderate` and `hard` rendering shown together.

| Stratum | Patients | Why it is on the sheet |
|---|---|---|
| Decision | 20 | 4 per engine decision, so abstentions are oversampled instead of drowned in `lifestyle_only` (51.5% of the test split) |
| Abstain mechanism | 2 | `abstain` is one word covering three rule paths; the two rare ones render prose the common one never produces |
| Contraindication | 3 | pregnancy and hyperkalemia flags live on the hidden row, not in the labels file — nothing else can sample for them |

## What to check, per vignette

Read each vignette and confirm it **states only raw facts**. A vignette fails if it:

- names a **BP stage** ("stage 2 hypertension", "hypertensive", "elevated blood pressure");
- states or implies a **treatment decision** ("needs treatment", "should be started on…",
  "management was escalated", "no treatment indicated");
- names a **drug class** as a recommendation (a drug the patient *already takes* by
  name is a fact and is fine — "he takes metoprolol 50 mg daily" is allowed,
  "a beta-blocker would be appropriate" is not);
- says anything that **implies the answer** — including a hint carried by ordering,
  emphasis, or a clinician-sounding aside.

**The three levels must describe the same patient with the same facts.** `hard`
adds irrelevant sentences and reorders; it must not add, drop, or change a
decision-relevant value.

> **If a phrasing makes you hesitate, flag it.** A hesitation is the finding. Do not
> try to decide whether it is "really" leakage — write it down and it gets triaged
> into `leakage.py` as a candidate forbidden token.
>
> You do **not** need to judge whether the hidden label is clinically right. That is
> HC-49 (clinician adjudication), not this gate. This gate is only: *does the
> vignette give the answer away?*

---

## Per-patient record

Mark each row. `OK` = facts only. `FLAG` = something to look at (then write it below).

| # | simple | moderate | hard | note |
|---|---|---|---|---|
| 1 | ☐ | ☐ | ☐ | |
| 2 | ☐ | ☐ | ☐ | |
| 3 | ☐ | ☐ | ☐ | |
| 4 | ☐ | ☐ | ☐ | |
| 5 | ☐ | ☐ | ☐ | |
| 6 | ☐ | ☐ | ☐ | |
| 7 | ☐ | ☐ | ☐ | |
| 8 | ☐ | ☐ | ☐ | |
| 9 | ☐ | ☐ | ☐ | |
| 10 | ☐ | ☐ | ☐ | |
| 11 | ☐ | ☐ | ☐ | |
| 12 | ☐ | ☐ | ☐ | |
| 13 | ☐ | ☐ | ☐ | |
| 14 | ☐ | ☐ | ☐ | |
| 15 | ☐ | ☐ | ☐ | |
| 16 | ☐ | ☐ | ☐ | |
| 17 | ☐ | ☐ | ☐ | |
| 18 | ☐ | ☐ | ☐ | |
| 19 | ☐ | ☐ | ☐ | |
| 20 | ☐ | ☐ | ☐ | |
| 21 | ☐ | ☐ | ☐ | *supplementary — rare abstain mechanism* |
| 22 | ☐ | ☐ | ☐ | *supplementary — rare abstain mechanism* |
| 23 | ☐ | ☐ | ☐ | *supplementary — contraindication flag* |
| 24 | ☐ | ☐ | ☐ | *supplementary — contraindication flag* |
| 25 | ☐ | ☐ | ☐ | *supplementary — contraindication flag* |

## Flagged phrasings

Quote the phrase and give its patient number and level. Each one becomes a candidate
addition to `leakage.py`'s forbidden-token list (or a renderer fix).

| # / level | phrase | why it made you hesitate |
|---|---|---|
| | | |

---

## Sign-off

> I have read all 75 vignettes on the sheet named above and confirm that each states
> only raw facts, with every hesitation recorded in the table above.

- **Signed:** ______________________
- **Date:** ______________________
- **Sheet checksum:** `442323c11b5d5baebaf5bf5e4242a391dc9cb3e038724d9348959fc411f214a0`
  (the sheet is generated deterministically; if your copy's SHA-256 differs, it is not the sheet this form signs off)
- **Outcome:** ☐ pass, no flags ☐ pass with flags recorded ☐ fail — corpus needs a renderer fix

**On sign-off:** set HC-57 to Done on the Linear board *and* in the Notion progress
tracker, and drop the "provisional" label from pilot numbers that were read after
this date.
