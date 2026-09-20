"""HC-17 -- pre-index medication reconciliation. The bottleneck of the MIMIC arm.

``on_bp_meds`` is the single variable separating *initiate* from *intensify*,
which is the decision this benchmark measures. Everything about this module
follows from where that variable is allowed to come from.

**Home meds come only from ``ed/medrecon``, at the index stay.**

* **Never discharge medications.** They are literally the label -- the decision
  we are asking the model to make, written down after it was made.
* **Never inpatient ``prescriptions`` by default.** Those orders are written
  after admission, so they cannot establish what the patient arrived on. A
  ``prescriptions`` fallback is acceptable only if restricted to orders started
  within 24 h of ``admittime`` AND pre-registered as a sensitivity analysis; it
  is not part of the primary definition and is not implemented here.
* **Never a later visit's reconciliation.** Binding a subsequent admission's
  medication list would import a post-decision fact into the hidden label.

**Absence is NA, never False.** A subject with no reconciliation at the index
stay has an unknown medication history. Recording that as "not on BP meds" would
relabel every *intensify* case in that group as *initiate* -- a wrong label,
silently, at scale, which is worse than an abstention. The HC-26 cohort rule
already requires a reconciliation for the decision cohort, so this case should
be empty there; it is handled correctly anyway, because the same function serves
the OMR-only and text cohorts, where it is common.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import ed


def pre_index_meds(
    medrecon: Any,
    edstays: Any,
    cohort: pd.DataFrame,
) -> pd.DataFrame:
    """One row per cohort subject:
    [subject_id, med_classes, on_bp_meds, statin_use, has_medrecon].

    ``cohort`` must carry ``subject_id`` and the index ``hadm_id``. Only the ED
    stay belonging to that admission is consulted.

    ``med_classes`` is always a list, never null, because the schema requires an
    array. An unknown medication history is expressed by ``on_bp_meds`` being
    null -- not by ``med_classes`` being null, which would fail contract
    validation and would also read as "no antihypertensives" to anything that
    checked its length.
    """
    stays = ed.load_edstays(edstays)
    # Restrict to the ED stay of the INDEX admission, by (subject, hadm) pair.
    index_pairs = cohort[["subject_id", "hadm_id"]].drop_duplicates()
    stays = stays.merge(index_pairs, on=["subject_id", "hadm_id"], how="inner")
    index_stay_ids = set(stays["stay_id"])

    per_stay = ed.med_classes_by_stay(medrecon)
    per_stay = per_stay[per_stay["stay_id"].isin(index_stay_ids)]

    # A subject could in principle have two ED stays on one admission; union
    # their class sets rather than letting an arbitrary one win.
    per_subject = (
        per_stay.groupby("subject_id", as_index=False)
        .agg(
            med_classes=("med_classes", lambda g: sorted({c for cs in g for c in cs})),
            statin_use=("statin_use", "any"),
            n_medrecon_rows=("n_medrecon_rows", "sum"),
        )
    )

    out = cohort[["subject_id"]].drop_duplicates().reset_index(drop=True)
    out = out.merge(per_subject, on="subject_id", how="left")

    has_rec = out["n_medrecon_rows"].notna()
    out["has_medrecon"] = pd.array(has_rec.to_numpy(dtype=bool), dtype="boolean")

    # Empty list, not null: the schema requires an array, and "unknown" is
    # carried by on_bp_meds instead.
    out["med_classes"] = [
        cs if isinstance(cs, list) else [] for cs in out["med_classes"]
    ]

    on = pd.array([None] * len(out), dtype="boolean")
    any_bp = [len(cs) > 0 for cs in out["med_classes"]]
    for i, present in enumerate(has_rec.to_numpy(dtype=bool)):
        if present:
            on[i] = bool(any_bp[i])
    out["on_bp_meds"] = on

    # statin_use feeds PREVENT, where a wrong False is a wrong risk score.
    # Unknown stays unknown.
    statin = pd.array([None] * len(out), dtype="boolean")
    raw = out["statin_use"].to_numpy(dtype=object)
    for i, present in enumerate(has_rec.to_numpy(dtype=bool)):
        if present:
            statin[i] = bool(raw[i]) if pd.notna(raw[i]) else False
    out["statin_use"] = statin

    return out[["subject_id", "med_classes", "on_bp_meds", "statin_use", "has_medrecon"]]
