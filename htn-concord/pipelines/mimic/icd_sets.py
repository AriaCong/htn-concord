"""ICD-9/10 code-set predicates for MIMIC comorbidity, contraindication and
smoking counting.

These are the sets ``vocab`` does NOT own. ``vocab`` owns the hypertension anchor
sets, because the anchor is a cohort-selection concept shared with the engine's
scope rules; these sets exist only to read ``hosp/diagnoses_icd``, so they live
with the MIMIC pipeline.

DESIGN INVARIANT: an HTN code selects the patient/encounter. It NEVER generates a
label. ``classify`` returns an empty set for every anchor and every secondary-HTN
code, and it does so by an explicit guard rather than by the code sets happening
not to overlap -- so a later edit that accidentally widened a set into the
hypertension range would fail the tests instead of quietly turning the benchmark
into a coding-lookup test.

Smoking is here because MIMIC has no structured smoking field anywhere, and
PREVENT requires it. Without an ICD limb, ``prevent_10yr`` is null for every MIMIC
row and every Stage-1 patient without diabetes/CKD/clinical-CVD abstains.
Extracting smoking from the discharge note is rejected: that note is Task-C
model-facing input, so a label derived from it would be circular.
"""
from __future__ import annotations

import vocab

FLAGS: tuple[str, ...] = (
    "diabetes", "clinical_cvd", "current_smoker", "angioedema_hx", "pregnancy",
)


def _norm(code: str | None) -> str:
    """Uppercase, strip dots and whitespace -- MIMIC stores codes undotted."""
    if not isinstance(code, str):
        return ""
    return code.replace(".", "").replace(" ", "").upper()


# --- ICD-10 prefix sets -----------------------------------------------------
_I10_DIABETES = ("E08", "E09", "E10", "E11", "E13")
_I10_CVD = (
    "I20", "I21", "I22", "I23", "I24", "I25",   # ischaemic heart disease
    "I50",                                      # heart failure
    "I60", "I61", "I62", "I63",                 # cerebrovascular
    "I65", "I66", "I70", "I739",                # atherosclerosis / PAD
)
_I10_SMOKING = ("F17", "Z87891")
_I10_ANGIOEDEMA = ("T783", "D841")
# Whole obstetric chapter (O00-O9A) plus the two Z-codes for a pregnancy recorded
# without a complication. Deliberately broad -- see _PREGNANCY_IS_DELIBERATELY_BROAD.
_I10_PREGNANCY = ("O", "Z33", "Z34")

# --- ICD-9 prefix sets ------------------------------------------------------
_I9_DIABETES = ("250",)
_I9_CVD = (
    "410", "411", "412", "413", "414",   # ischaemic heart disease
    "428",                               # heart failure
    "430", "431", "432", "433", "434",   # cerebrovascular
    "440", "443",                        # atherosclerosis / PAD
)
_I9_SMOKING = ("3051", "V1582")
_I9_ANGIOEDEMA = ("9951",)
# ICD-9 obstetric chapter is 630-679. Enumerated rather than written as a bare
# "63"/"64" prefix, because "64" also matches nothing outside the chapter today
# but would silently widen if a future edit shortened it further.
_I9_PREGNANCY = tuple(str(n) for n in range(630, 680)) + ("V22", "V23")

# Pregnancy is flagged broadly, and that asymmetry is deliberate rather than
# sloppy. The flag is a SCOPE GATE: it makes the engine abstain, it does not
# choose a drug. Over-flagging therefore costs benchmark items; under-flagging
# labels a pregnant patient INITIATE as ground truth, which is exactly the safety
# defect HC-24 found in NHANES. Given a choice between losing a case and shipping
# an unsafe label, lose the case.
#
# Consequences accepted, both flagged for HC-49 clinician adjudication:
#   * 630-639 (ectopic and abortive outcomes) flag a pregnancy that has ended.
#   * A delivery code at the index encounter flags a patient who may be
#     postpartum rather than pregnant at the decision point.
# Neither can be resolved from billing codes alone without a clinical judgement
# this pipeline is not entitled to make.
_PREGNANCY_IS_DELIBERATELY_BROAD = True


def classify(code: str | None, version: int | str) -> frozenset[str]:
    """Return the set of flags a single ICD code contributes. Empty if none.

    Never returns a flag for a hypertension code -- anchor or secondary. Staging
    comes from OMR, and letting a code generate the label would make the
    benchmark a coding-lookup test.

    An unreadable ``version`` yields the empty set rather than defaulting to
    ICD-10: a version we cannot read is missing data, and guessing it would apply
    the wrong code book to a real code.
    """
    c = _norm(code)
    if not c:
        return frozenset()

    try:
        v = int(version)
    except (TypeError, ValueError):
        return frozenset()
    if v not in (9, 10):
        return frozenset()

    # The design invariant, enforced rather than assumed.
    if vocab.is_htn_anchor(c, v) or vocab.is_htn_secondary(c, v):
        return frozenset()

    if v == 10:
        diabetes, cvd = _I10_DIABETES, _I10_CVD
        smoking, angio, preg = _I10_SMOKING, _I10_ANGIOEDEMA, _I10_PREGNANCY
    else:
        diabetes, cvd = _I9_DIABETES, _I9_CVD
        smoking, angio, preg = _I9_SMOKING, _I9_ANGIOEDEMA, _I9_PREGNANCY

    out: set[str] = set()
    if c.startswith(diabetes):
        out.add("diabetes")
    if c.startswith(cvd):
        out.add("clinical_cvd")
    if c.startswith(smoking):
        out.add("current_smoker")
    if c.startswith(angio):
        out.add("angioedema_hx")
    if c.startswith(preg):
        out.add("pregnancy")
    return frozenset(out)
