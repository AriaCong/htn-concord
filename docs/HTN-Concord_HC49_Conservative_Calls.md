# HC-49 — conservative calls made while building the MIMIC-IV arm

**Status:** agenda for clinician face-validity review and adjudication (HC-49).
**Written 2026-09-20**, covering HC-56, HC-97, HC-98, HC-26, HC-20, HC-27, HC-15,
HC-16, HC-17, HC-18, HC-19.
**Companion (中文):** `HTN-Concord_HC49_Conservative_Calls_zh.md`.

---

## 0. Why this document exists, and how to read it

The engineer who built the MIMIC arm has **no clinical training**, and neither does
the project owner. Every decision below needed clinical judgement that neither of
them was entitled to exercise. The standing rule was therefore: **make the
conservative call, implement it, write down the reasoning, and flag it here** —
never guess, and never stall waiting for an answer.

"Conservative" is not one direction. It depends on what a wrong answer does:

- Where a wrong value would produce a **wrong treatment label**, the conservative
  choice is the one that makes the engine **abstain**.
- Where a wrong value would produce an **unsafe recommendation** (treating a
  contraindication as absent), the conservative choice is the one that **flags the
  contraindication**, even at the cost of losing cases.
- Where a choice is between two defensible conventions with no safety asymmetry,
  the conservative choice is the one that keeps the **NHANES and MIMIC arms
  identical**, because a difference between arms confounds the headline comparison.

**What we need from the reviewer.** For each item: accept, reject, or amend. An
item marked *accepted* becomes a pre-registered methods statement. An item marked
*rejected* needs a rule we can implement deterministically — not a judgement to be
applied case by case, because there is no clinician in the labelling loop by
design.

**What this document is not.** It is not a list of bugs, and it is not a list of
everything the pipeline does. It is only the decisions where a competent clinician
might reasonably have chosen otherwise.

---

## 1. Decisions that change who is in the cohort

### 1.1 Pregnancy is flagged across the whole obstetric code chapter

**What we did.** Any ICD-10 chapter-O code, plus `Z33`/`Z34`, and any ICD-9 code
in 630–679 plus `V22`/`V23`, sets the pregnancy flag.

**Why.** Pregnancy is a *scope gate*: it makes the engine abstain rather than
choosing a drug. Over-flagging costs benchmark items. Under-flagging labels a
pregnant patient `INITIATE` as ground truth — which is exactly the safety defect
HC-24 found and fixed in the NHANES arm. Given that asymmetry we flag broadly.

**Known cost, and we would like a ruling on it.** This also flags:
- **630–639** — ectopic and abortive outcomes, i.e. a pregnancy that has *ended*.
- **Delivery codes at the index encounter** — a patient who may be *postpartum*
  rather than pregnant at the decision point.

Billing codes alone cannot separate "pregnant now" from "was pregnant recently".
**Question: is postpartum status a reason to abstain from antihypertensive
decisions in this benchmark, or should it be treated as non-pregnant?** Observed
prevalence in the decision cohort: **52 patients**.

### 1.2 Secondary hypertension is excluded entirely

**What we did.** ICD-9 `405` and ICD-10 `I15*` exclude a patient from the cohort;
they can never act as an anchor, and they never set a comorbidity flag.

**Why.** The benchmark measures *primary* hypertension management. Secondary
hypertension is a different decision problem — treat the cause, not the number.

**Confidence: high.** Flagged only because an earlier draft of the data dictionary
wrongly listed `I15*` as *included*, so we want the correct reading confirmed once
on the record. No question outstanding unless the reviewer disagrees.

### 1.3 The index encounter requires a medication reconciliation

**What we did.** A patient enters the decision cohort only if their earliest
HTN-anchor admission has a medication reconciliation at its own emergency-department
stay. This cuts 28,530 → 9,492 (ED-linked) → **8,921**.

**Why.** The reconciliation is the only record of what the patient was taking
*before* the decision. Discharge medications are the answer we are testing, and
inpatient orders are written after admission. Without a reconciliation there is no
way to tell *start a drug* from *add a drug*, which is the decision being measured.

**Known cost.** This selects for patients who arrive through the emergency
department rather than electively — a real selection bias, in the opposite
direction to the bias introduced by requiring prior outpatient readings. Both are
reported in the attrition waterfall.

**Question: is an ED-arriving hypertensive population different enough from a
general hypertensive population that the concordance result should be qualified?**

### 1.4 Blood pressure must come from ≥2 outpatient readings on separate days

**What we did.** ≥2 readings on distinct dates within 365 days strictly before the
index admission. Same-day readings, and readings on the admission date itself, do
not qualify.

**Why.** The guideline asks for an average of ≥2 readings on ≥2 occasions. Three
readings at one visit are one occasion. A reading on the admission date is at or
after the decision point and may be an acute presentation rather than the patient's
usual pressure.

**Question: is 365 days the right window for "usual" blood pressure, or is it too
long for a patient whose treatment may have changed within it?** A 730-day window
is pre-registered as a sensitivity analysis.

---

## 2. Decisions that change what we believe about a patient

### 2.1 An absent diagnosis code counts as a negative — the biggest call here

**What we did.**
- Code present → **true**.
- Code absent, but the patient has other billed diagnoses in the time window →
  **false**.
- Patient has no billed diagnoses at all in the window → **unknown**, and the
  engine abstains.

**Why.** This is the standard electronic-health-record phenotyping reading, and it
mirrors the argument already used for NHANES medication lists: absence inside an
inventory that exists is a negative, not a gap. The alternative — treating absence
as unknown always — would abstain on nearly the entire Stage-1 cohort and leave no
benchmark.

**Known bias, and its direction is the unsafe one.** Where coding is incomplete,
this reads *unknown* as *no comorbidity*, which removes a treatment trigger and
biases toward **under-treatment**.

**Mitigation already in place.** Every result is produced under **both** readings
and both are reported:

| Reading | Resolvable cases | Abstain share |
|---|---:|---:|
| Prior admissions only (leakage-safe) | 6,372 of 8,919 (71.4%) | 28.6% |
| Including the index encounter's codes | 8,041 of 8,919 (90.2%) | 9.8% |

The gap is large because **6,688 of 8,919 patients (75%) have no prior admission
at all** — their comorbidity record does not exist before the index encounter.

**Questions.** (a) Is "absence within an existing problem list means absent"
acceptable as a pre-registered assumption? (b) Diagnoses billed at the index
encounter are assigned at discharge — is it legitimate to use them as though they
described the patient at admission?

### 2.2 Smoking status is inferred from diagnosis codes

**What we did.** Nicotine-dependence and personal-history-of-smoking codes set
current-smoker.

**Why.** MIMIC has **no structured smoking field anywhere**, and the PREVENT risk
score requires smoking status. Without this, the risk score is uncomputable for
every patient and every Stage-1 patient without diabetes, kidney disease or
established cardiovascular disease abstains.

**Explicitly rejected alternative: extracting smoking from the discharge note.**
That note is the model-facing input for the text task, so a label derived from it
would be scored against itself.

**Known cost.** A personal-history code does not distinguish *current* from
*former* smoker, and coded smoking is coarser than NHANES's self-report. **The two
arms' risk scores are therefore not pooled.**

**Question: is a history-of-nicotine-dependence code acceptable as a proxy for
current smoking in a risk score, or should it be treated as former (non-)smoker?**

### 2.3 Four real antihypertensive classes are invisible to the benchmark

**What we did.** Direct renin inhibitors, central alpha-2 agonists (clonidine,
methyldopa), direct vasodilators (hydralazine, minoxidil) and non-aldosterone
potassium-sparing diuretics (amiloride, triamterene) map to **nothing**.

**Why.** The engine's medication vocabulary cannot express them. They are left
unmapped rather than assigned to an approximate neighbour, because calling
clonidine an alpha-blocker or amiloride a mineralocorticoid antagonist would be
*wrong*, not merely coarse.

**Known cost.** A patient on hydralazine alone appears to be on no antihypertensive.

**Question: how often does that matter in practice, and should any of these four be
added to the vocabulary before the benchmark is frozen?**

### 2.5 A coded-negative comorbidity plus a missing lab resolves to *unknown*

**What we did.** Diabetes is `coded diabetes OR HbA1c ≥6.5%`, and kidney disease
is `eGFR <60 OR albumin-creatinine ratio ≥30`. Both use three-valued (Kleene)
logic: true if either limb is true, false only if **both** limbs are known false,
unknown otherwise.

**Why.** It matches NHANES exactly, which is the property the shared derivation
core exists to guarantee, and it refuses to assert a negative from an incomplete
picture.

**The consequence is much larger in MIMIC than in NHANES, and we did not expect
it.** NHANES asks everyone about diabetes, so a "no" is a real answer and the
unknown case is rare. In MIMIC the first limb is *absence of a billed code* — a
weaker negative — and HbA1c is missing for 59.7% of the cohort. The two combine
so that:

| Field | Unknown in the decision cohort |
|---|---:|
| diabetes | **48.5%** |
| kidney disease (eGFR or albuminuria) | **60.2%** |
| 10-year risk score | **75.9%** |

Because diabetes is an input to the risk score, its unknowns propagate: the score
is computable for far fewer patients than the pre-build projection suggested.

**There is a tension here with §2.1 that we are deliberately not resolving
ourselves.** §2.1 says an absent code within an existing problem list is a
negative. This rule then takes that negative, combines it with a missing lab, and
returns it to unknown. Both behaviours are individually defensible; together they
mean the absence decision is partly undone for exactly the two comorbidities that
matter most for treatment.

**Question: when a patient has a problem list that does not mention diabetes and
no HbA1c was drawn, should they be treated as non-diabetic, or as unknown?** The
answer changes the size of the usable benchmark substantially. The same question
applies to kidney disease with a normal eGFR and no urine albumin.

### 2.4 Medication indication is not adjudicated

**What we did.** A drug sets its class regardless of why it was prescribed. A
beta-blocker prescribed after a heart attack counts as an antihypertensive; a
uroselective alpha-blocker prescribed for the prostate does not, because it is
recorded under a prostate therapeutic class — but doxazosin does count, because
NHANES counts it and the two arms must agree.

**Why.** Indication is not recorded in a form we can read, and guessing it per drug
would put unqualified clinical judgement into the reference standard. Consistency
between arms was the tie-breaker.

**Question: is "on an antihypertensive drug class" an acceptable operationalisation
of "on treatment for hypertension", or does indication need to be handled?**

---

## 3. Decisions about laboratory values

### 3.1 Labs are bound strictly before the admission, within 365 days

**What we did.** The most recent value strictly before the admission time, within
365 days. Nothing from during the admission. No value carried forward. No value
older than the window. Missing → unknown → abstain.

**Why.** A creatinine or potassium drawn *during* the index admission is
post-decision and may reflect the very treatment being evaluated. A two-year-old
potassium should not set a contraindication today.

**Question: is 365 days appropriate for kidney function and potassium, given both
can change over months?** 730 days is pre-registered as a sensitivity analysis.
Separately: **lipids are the binding constraint on the risk score** — cholesterol
and HDL are available for only about half the cohort. **Would a longer lookback for
lipids specifically be clinically defensible?**

### 3.2 Hyperkalemia is flagged at ≥5.5 mmol/L and nowhere lower

**What we did.** The avoid-ACE-inhibitor/ARB contraindication fires at ≥5.5. The
5.0–5.4 band is deliberately *not* a contraindication. Observed: **575 patients**.

**Why.** Flagging the 5.0–5.4 band would mark correct model answers as unsafe.

**Question: is ≥5.5 the right threshold for "do not start an ACE inhibitor or ARB",
and should the 5.0–5.4 band trigger anything at all — a caution rather than a
contraindication?**

### 3.3 Unexpected units abort rather than convert

**What we did.** A lab arriving in an unexpected unit raises an error and stops the
build.

**Why.** A creatinine in µmol/L is roughly 88× the same value in mg/dL. It would
pass every plausibility check as "high but possible" and then produce a confident,
wrong kidney-function estimate. **Confidence: high, no question outstanding.**

---

## 4. Decisions about the text task

### 4.1 Silver labels never come from the note

**What we did.** Structured tables only. The code refuses to run if handed note
text.

**Why.** A label extracted from the same text the model is asked to read scores the
task against itself.

**Consequence the reviewer should hold us to:** the text task measures **extraction
fidelity**, not guideline concordance. A fact true in the structured record may
simply not appear in the note, and the model cannot be faulted for failing to
extract what is not there. **Question: what sample size and sampling frame would
make the hand-validation of these silver labels convincing?**

### 4.2 De-identification placeholders are preserved exactly

**What we did.** Redaction tokens are passed through verbatim. Nothing is imputed
across them and nothing that could change clinical meaning is altered.

**Why.** A tidied note is a different document from the one the clinician wrote.
**Confidence: high, no question outstanding.**

---

## 5. One decision that is *not* ours, recorded so it is not re-litigated

**Blood pressure is summarised by the arithmetic mean, not the median.** Checked
against the 2025 AHA/ACC guideline text, which specifies *the average* of ≥2
readings throughout and never specifies a median. Both arms use the mean, so they
agree. The median is retained as a pre-registered sensitivity analysis.

This is recorded here because an earlier project decision said median, and that
decision was reversed against the source. The reviewer may still wish to confirm
that the guideline's "average" is intended as the arithmetic mean.

---

## 6. Summary — what we most need adjudicated

Ranked by how much a wrong answer would cost.

| # | Decision | Why it is first | §
|---|---|---|---|
| 1 | Absent diagnosis code counts as negative | Biases toward under-treatment, the unsafe direction, and moves the abstention rate from 9.8% to 28.6% | 2.1 |
| 2 | Pregnancy flagged across the whole obstetric chapter | Safety flag; over-flagging is intentional but includes ended pregnancies | 1.1 |
| 3 | Coded-negative plus missing lab resolves to unknown | Leaves diabetes unknown for 48.5% and the risk score for 75.9%, and partly undoes the decision in row 1 | 2.5 |
| 4 | Smoking inferred from diagnosis codes | Feeds the risk score, which is the Stage-1 treatment trigger | 2.2 |
| 5 | Hyperkalemia threshold and the 5.0–5.4 band | Directly determines the safety outcome | 3.2 |
| 6 | 365-day lab window | Kidney function and potassium both drift | 3.1 |
| 7 | Medication-reconciliation requirement and its selection bias | Determines who is in the benchmark at all | 1.3 |
| 8 | Four antihypertensive classes unrepresented | Systematically understates treatment | 2.3 |
