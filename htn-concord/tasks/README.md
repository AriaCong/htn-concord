# `tasks/` — benchmark task builders (E4)

Built: **Task B (HC-53)**. Not built: Task A (HC-52), Task C (HC-54), Task D (HC-55).

```python
from tasks import load_profiles_csv, build, verify

profiles = load_profiles_csv("data/nhanes/processed/nhanes_profiles_J.csv")
manifest = build(profiles, "data/tasks/task_b", seed=2026)   # renders, labels, audits, freezes
verify("data/tasks/task_b")                                   # re-check checksums + audit
```

## What Task B is

One `PatientProfile` produces three cases (simple / moderate / hard). The model sees
only the rendered vignette; the label is the engine's decision on the **hidden**
structured row. The engine runs on the profile and never sees the vignette; the
renderer produces the vignette and never sees the label.

## Physical separation (Master Plan principle 4)

| file | contents | model-facing |
|---|---|---|
| `task_b_inputs.jsonl` | `case_id`, `level`, `split`, `patient_id`, `vignette` | **yes** — the only file a runner is given |
| `task_b_labels.jsonl` | `case_id`, `decision`, `bp_stage`, `triggers`, `abstain_reason`, `citations`, `trace` | no |
| `task_b_manifest.json` | counts, split sizes, decision distribution, audit result, SHA-256 per file | no |

Joined only on `case_id`. Nothing answer-shaped shares a file with anything a model
reads, so a wrong path in a later script yields a missing key rather than a silent
leak.

## The leakage audit is a gate, not a report

`build()` refuses to write a corpus that fails. A leaked benchmark sitting on disk
will eventually be used by something, so the failure mode has to be "no corpus"
rather than "a corpus plus a warning". Three independent checks:

1. **no forbidden token** in any vignette (`leakage.scan` — leaked prose);
2. **no label column** on a model-facing record (leaked schema);
3. **inputs and labels align 1:1** on `case_id` — a silent join error would pair a
   vignette with someone else's answer and read as model failure.

## Splits are patient-level and growth-stable

`splits.assign_split` is a pure function of the patient identity and a salt.

*Patient-level*: one patient's three levels come from one structured row. Splitting
per case would put their simple vignette in train and their hard one in test, so a
model memorizing patients would score as generalizing. `assert_disjoint` enforces
this at build time.

*Growth-stable*: assignment is `hash(patient) < threshold`, not shuffle-and-slice, so
adding NHANES cycles or the MIMIC cohort leaves every existing patient where it was.
A shuffle would silently repartition the whole benchmark the first time `N` changed,
invalidating any result already reported against it.

## Frozen corpus, as built

NHANES cycle J, `seed=2026`, salt `htn-concord-v1` — see
`benchmarks/task_b_manifest.json` (committed; `data/` is gitignored because these are
patient-level rows).

- 4,806 patients → **14,418 cases**
- splits: 2,914 train / 940 dev / 952 test patients
- labels: 7,635 lifestyle_only · 2,571 intensify · 2,253 initiate · 1,527 at_goal_continue · 432 abstain
- **leakage audit: passed, 0 token hits, 0 label-column hits across all 14,418**

Rebuilding from the same inputs must reproduce those checksums; `verify()` asserts it.

## `profiles.py` — the CSV seam

`pipelines/nhanes` writes profiles to CSV, where everything is a string, and the
engine is deliberately strict about types (`vocab.bp_stage_scalar` raises on a string
SBP rather than mis-comparing it). `load_profiles_csv` coerces using
`schemas/patient_profile.schema.json` as the type source, so a new column picks up
the right type instead of arriving as a string and failing downstream.

## Remaining gate

The mechanical audit passes. The Phase-4 acceptance gate also requires **a human
confirming 20 rendered vignettes state only facts** — a scanner only catches the
tokens it was told about. Generate the sheet with:

```python
from tasks.spotcheck import build_spotcheck
build_spotcheck("data/tasks/task_b", "data/tasks/task_b/spotcheck_20.md")
```

It is stratified by engine decision (4 patients per decision, all three levels), so
the read is weighted toward abstentions and contraindication-positive cases rather
than a uniform draw dominated by `lifestyle_only`.
