"""HC-13 — MIMIC chronic-HTN cohort feasibility gate (COUNTING ONLY, no modeling).

Answers: how many subjects survive each cohort rule? Requiring >=2 outpatient OMR
BP readings *before* the earliest anchor HTN encounter compounds attrition (many
patients' first MIMIC appearance IS the HTN encounter). This reports the attrition
waterfall so we can decide the v1 rule (365d / >=2) vs the fallback (730d / >=1)
BEFORE building the cohort. No profiles are produced here.

    python -m pipelines.mimic.feasibility
"""
from __future__ import annotations

import json
import re

import pandas as pd

from . import cohort, config, ed

_BP_RE = re.compile(r"^\s*\d{2,3}\s*/\s*\d{2,3}")  # "120/80"-ish


# The anchor, index-encounter and ED-linkage rules live in cohort.py, which is
# the single home of the cohort definition. They are re-exported here rather
# than reimplemented: the attrition waterfall has to justify the cohort the
# profile builder actually produces, and two copies would eventually disagree.
_anchor_subject_hadms = cohort.anchor_subject_hadms
_earliest_anchor_admit = cohort.earliest_anchor_admit
ed_linked_hadms = cohort.ed_linked_hadms
hadms_with_medrecon = cohort.hadms_with_medrecon


def _edstays() -> pd.DataFrame:
    """[subject_id, hadm_id, stay_id] for ED visits that reached an admission."""
    return ed.load_edstays(config.ED / "edstays.csv.gz")


def project_label_yield(primary: pd.DataFrame, flags: pd.DataFrame) -> dict:
    """Project how many Primary-cohort subjects could receive a NON-ABSTAIN label.

    This is a PROJECTION, not an engine run: it reproduces only the three
    abstention gates that dominate, using columns available at counting time.
    It exists to answer one question before the profile emitter is built --
    can this cohort yield decision labels at all?

    Gates modelled, in the engine's order, each counted exactly once so the
    reasons sum to the abstentions:

      1. on_bp_meds unknown  -> med_status_unknown (initiate vs intensify is
         undecidable; medrecon is the only leakage-safe source)
      2. bp_stage unknown    -> staging_indeterminate
      3. stage1 with no high-risk trigger and no computable PREVENT
                             -> stage1_risk_indeterminate

    A subject missing from ``flags`` has unknown comorbidity, which must not
    resolve a Stage-1 case: missing is not False, and False is not a trigger.
    The merge leaves NA and the trigger test treats NA as "no trigger", which
    abstains -- the conservative direction.

    Pregnancy is NOT modelled here: it is a scope gate that precedes staging and
    its MIMIC prevalence is counted separately.
    """
    df = primary.merge(flags, on="subject_id", how="left")

    def _bool(col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        return df[col].astype("boolean").fillna(False).astype(bool)

    med_unknown = df["on_bp_meds"].isna()
    stage_unknown = df["bp_stage"].isna() & ~med_unknown

    trigger = _bool("diabetes") | _bool("clinical_cvd") | _bool("prevent_computable")
    stage1_indet = (
        (df["bp_stage"] == "stage1") & ~trigger & ~med_unknown & ~stage_unknown
    )

    n = int(len(df))
    n_med = int(med_unknown.sum())
    n_stage = int(stage_unknown.sum())
    n_s1 = int(stage1_indet.sum())
    resolvable = n - n_med - n_stage - n_s1

    return {
        "n": n,
        "resolvable": resolvable,
        "abstain_med_status_unknown": n_med,
        "abstain_staging_indeterminate": n_stage,
        "abstain_stage1_risk_indeterminate": n_s1,
        "abstain_share": round((n - resolvable) / n, 4) if n else 0.0,
    }


def _omr_bp() -> pd.DataFrame:
    """Outpatient OMR blood-pressure rows with a parseable value and a date."""
    omr = pd.read_csv(
        config.HOSP / "omr.csv.gz",
        usecols=["subject_id", "chartdate", "result_name", "result_value"],
        dtype={"result_name": "string", "result_value": "string"},
        parse_dates=["chartdate"],
    )
    bp = omr[omr["result_name"].str.startswith("Blood Pressure", na=False)].copy()
    bp = bp[bp["result_value"].str.match(_BP_RE, na=False)]
    return bp[["subject_id", "chartdate"]]


def build_waterfall() -> dict:
    patients = pd.read_csv(
        config.HOSP / "patients.csv.gz", usecols=["subject_id", "anchor_age"]
    )
    n_subjects = patients["subject_id"].nunique()
    n_adults = patients.loc[patients["anchor_age"] >= config.MIN_AGE, "subject_id"].nunique()

    idx = _earliest_anchor_admit()                     # anchor subjects + index date
    n_anchor = idx["subject_id"].nunique()

    bp = _omr_bp()
    n_any_omr_bp = bp["subject_id"].nunique()

    # OMR-only cohort (no HTN ICD required): subjects with >=2 distinct BP dates.
    omr_dates = bp.groupby("subject_id")["chartdate"].nunique()
    n_omr_only_ge2 = int((omr_dates >= config.MIN_READINGS_PRIMARY).sum())

    # Anchor patients with qualifying PRIOR OMR (before index, within a window).
    j = bp.merge(idx, on="subject_id", how="inner")
    j["days_before"] = (j["index_admit"] - j["chartdate"]).dt.days
    prior = j[j["days_before"] > 0]                    # strictly before index
    n_anchor_any_prior = prior["subject_id"].nunique()

    def _qualify(window_days: int, min_reads: int) -> int:
        w = prior[prior["days_before"] <= window_days]
        distinct = w.groupby("subject_id")["chartdate"].nunique()
        return int((distinct >= min_reads).sum())

    n_primary = _qualify(config.WINDOW_PRIMARY_DAYS, config.MIN_READINGS_PRIMARY)
    n_fallback = _qualify(config.WINDOW_FALLBACK_DAYS, config.MIN_READINGS_FALLBACK)

    # --- HC-26: ED linkage, the real decision-cohort constraint ---------------
    # PRIMARY counts subjects surviving the BP rules only. But on_bp_meds must
    # come from ed/medrecon (never discharge meds, which ARE the answer), so a
    # subject whose index encounter has no ED stay cannot be labelled at all.
    # 28,530 is a staging/Task-C cohort; it is not the decision cohort.
    primary_ids = set(
        prior[prior["days_before"] <= config.WINDOW_PRIMARY_DAYS]
        .groupby("subject_id")["chartdate"].nunique()
        .pipe(lambda s: s[s >= config.MIN_READINGS_PRIMARY]).index
    )
    ed_hadms = ed_linked_hadms()
    idx_primary = idx[idx["subject_id"].isin(primary_ids)]
    n_primary_ed = int(
        idx_primary[idx_primary["hadm_id"].isin(ed_hadms)]["subject_id"].nunique()
    )
    # Having an ED stay is necessary for medrecon but not sufficient: the
    # reconciliation may be absent for that particular visit. Counted separately,
    # stay-level, so the decision-cohort number is not quietly optimistic.
    rec_hadms = hadms_with_medrecon()
    n_primary_ed_rec = int(
        idx_primary[idx_primary["hadm_id"].isin(rec_hadms)]["subject_id"].nunique()
    )

    return {
        "all_subjects": int(n_subjects),
        "adults_ge18": int(n_adults),
        "with_htn_anchor_dx": int(n_anchor),
        "anchor_with_any_prior_omr_bp": int(n_anchor_any_prior),
        "PRIMARY_anchor_ge2_within_365d": int(n_primary),
        "PRIMARY_ed_linked_DECISION_COHORT": n_primary_ed,
        "PRIMARY_ed_linked_share": (
            round(n_primary_ed / n_primary, 4) if n_primary else 0.0
        ),
        "PRIMARY_ed_linked_with_medrecon": n_primary_ed_rec,
        "FALLBACK_anchor_ge1_within_730d": int(n_fallback),
        "any_omr_bp_subjects": int(n_any_omr_bp),
        "OMR_only_cohort_ge2_dates": int(n_omr_only_ge2),
        "params": {
            "primary": f">={config.MIN_READINGS_PRIMARY} distinct dates within {config.WINDOW_PRIMARY_DAYS}d before index",
            "fallback": f">={config.MIN_READINGS_FALLBACK} reading within {config.WINDOW_FALLBACK_DAYS}d before index",
        },
    }


def main() -> int:
    w = build_waterfall()
    print("MIMIC-IV chronic-HTN cohort — attrition waterfall (counting only)\n")
    order = [
        ("All subjects (hosp)", "all_subjects"),
        ("  Adults >=18", "adults_ge18"),
        ("  With HTN anchor dx (earliest anchor encounter)", "with_htn_anchor_dx"),
        ("    ...with ANY prior OMR BP", "anchor_with_any_prior_omr_bp"),
        ("    PRIMARY: >=2 OMR BP on distinct dates <365d before index", "PRIMARY_anchor_ge2_within_365d"),
        ("    PRIMARY + ED-linked = DECISION COHORT (HC-26)", "PRIMARY_ed_linked_DECISION_COHORT"),
        ("      ...and with an actual medrecon", "PRIMARY_ed_linked_with_medrecon"),
        ("    FALLBACK: >=1 OMR BP <730d before index", "FALLBACK_anchor_ge1_within_730d"),
        ("OMR-only cohort: any OMR BP", "any_omr_bp_subjects"),
        ("  OMR-only: >=2 distinct BP dates (undiagnosed capture)", "OMR_only_cohort_ge2_dates"),
    ]
    for label, key in order:
        print(f"{w[key]:>8,}  {label}")
    out = config.QA / "feasibility_waterfall.json"
    out.write_text(json.dumps(w, indent=2))
    print(f"\nsaved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
