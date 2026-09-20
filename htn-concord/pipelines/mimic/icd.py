"""HC-16 -- ICD-9/10 crosswalk: diagnosis rows to per-subject comorbidity flags.

``icd_sets`` owns the code predicates. This module owns the frame-level
crosswalk and, more importantly, the **absence semantics** -- which is the
label-validity call for the whole MIMIC arm and is not derivable from the code.

    A billed code present                      -> True
    Code absent, patient HAS billed rows       -> False
    Patient has NO billed diagnosis rows       -> NA

The middle rule is the load-bearing one. It mirrors the complete-inventory
argument already used for NHANES ``med_classes``: absence inside an enumeration
that exists is a negative, not a gap, and it is the standard EHR-phenotyping
reading. The third rule is what keeps it honest -- where no enumeration exists,
absence carries no information at all, and asserting a negative there is exactly
the guess the ABSTAIN contract forbids.

**Known bias and its direction.** Where coding is incomplete, the middle rule
reads unknown as negative and biases toward **under-treatment** -- the unsafe
direction. The alternative, absence -> NA always, would abstain nearly the whole
Stage-1 cohort and yield no benchmark items. The cost is accepted with two
mandatory mitigations, neither optional:

1. Both readings are reported, by passing different ``prior_hadms`` /
   ``index_hadms`` sets, and the difference is carried into the manuscript
   rather than averaged away. On the decision cohort it is large: 71.4% vs
   90.2% resolvable, because three of four patients are first seen at the index
   encounter (HC-98 gate, spec 6.3).
2. Flagged for HC-49 clinician adjudication as a named assumption.

**Why the two time readings exist.** ``prior_hadms`` are admissions strictly
before the index ``admittime`` -- leakage-safe, and what the cleaning convention
"comorbidities are time-bounded before admittime" literally says.
``index_hadms`` adds the index encounter's own codes, which is what the approved
spec describes; those are assigned at discharge, so they are only partly
pre-decision. Callers choose; this module never picks silently.
"""
from __future__ import annotations

import pandas as pd

import vocab

from . import icd_sets


def _classified(dx: pd.DataFrame) -> pd.DataFrame:
    """Attach a flag set to each diagnosis row.

    Classifies the distinct (code, version) pairs once and maps back: MIMIC's
    diagnosis table is long but its code vocabulary is small, so this is far
    cheaper than classifying row-wise and gives the identical result.
    """
    pairs = dx[["icd_code", "icd_version"]].drop_duplicates()
    pairs = pairs.assign(flags=[
        icd_sets.classify(c, v)
        for c, v in zip(pairs["icd_code"], pairs["icd_version"])
    ])
    return dx.merge(pairs, on=["icd_code", "icd_version"], how="left")


def crosswalk(
    dx: pd.DataFrame,
    cohort: pd.DataFrame,
    prior_hadms: set,
    index_hadms: set,
) -> pd.DataFrame:
    """One row per cohort subject: the five flags as nullable booleans.

    ``dx`` is raw ``hosp/diagnoses_icd`` rows. ``cohort`` supplies subject_id.
    Only diagnoses from ``prior_hadms | index_hadms`` are counted; see the module
    docstring for why the caller chooses that set.

    Every flag column is ``boolean`` dtype, never object. An object column would
    let a stray ``1`` read as True and a ``NaN`` read as low-risk downstream,
    which is the failure three-valued logic exists to prevent.
    """
    subjects = cohort["subject_id"].drop_duplicates().reset_index(drop=True)
    in_scope = prior_hadms | index_hadms

    dx = dx[dx["subject_id"].isin(set(subjects))]
    dx = _classified(dx)
    scoped = dx[dx["hadm_id"].isin(in_scope)]

    # "Has an enumeration" means the patient has at least one billed diagnosis
    # row IN SCOPE -- not anywhere in their history. A patient whose only coding
    # sits outside the time window has no enumeration at the decision point.
    enumerated = set(scoped["subject_id"])

    out = pd.DataFrame({"subject_id": subjects})
    for flag in icd_sets.FLAGS:
        positive = set(
            scoped.loc[scoped["flags"].apply(lambda s: flag in s), "subject_id"]
        )
        out[flag] = pd.array(
            [True if s in positive else (False if s in enumerated else None)
             for s in subjects],
            dtype="boolean",
        )
    out["has_any_dx"] = pd.array(
        [s in enumerated for s in subjects], dtype="boolean"
    )
    return out


def contraindications_from_flags(flags: pd.DataFrame) -> pd.Series:
    """The engine's contraindication list, from the crosswalked flags.

    Positive-only, and deliberately so: only a recorded code sets a flag, so an
    unascertained pregnancy or angioedema history never reads as *absent*. The
    list is the schema's contraindications array, which is why the names must
    stay inside ``vocab.CONTRAINDICATION_FLAGS``.

    Hyperkalemia is NOT assembled here -- it comes from a potassium value, not a
    code, and is added by the profile builder.
    """
    coded = [f for f in ("pregnancy", "angioedema_hx")
             if f in vocab.CONTRAINDICATION_FLAGS and f in flags.columns]

    # Comparisons stay vectorised and NA-safe. Row-wise `value == True` on a
    # nullable column returns pd.NA for a missing flag, and pd.NA in a boolean
    # context raises -- the exact three-valued-logic trap this module is about.
    positive = {
        f: flags[f].astype("boolean").fillna(False).to_numpy(dtype=bool)
        for f in coded
    }
    rows = [
        sorted(f for f in coded if positive[f][i])
        for i in range(len(flags))
    ]
    return pd.Series(rows, index=flags.index, name="contraindications")
