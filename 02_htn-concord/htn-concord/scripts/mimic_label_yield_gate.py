"""HC-98 / B2a -- the MIMIC label-yield gate. COUNTING ONLY.

Produces no PatientProfile rows and no labels. It answers one question before
the profile emitter is written: can the post-HC-26 decision cohort yield
decision labels at all, and how many carry each contraindication?

Corpus audit finding F2 was caught on NHANES only AFTER the corpus was built,
where it invalidated a co-primary outcome -- 9 of 4,806 patients carry any
contraindication, all hyperkalemia, none pregnancy, none angioedema. The same
class of failure is fully available here, and this gate exists to find it while
it is still cheap.

    python scripts/mimic_label_yield_gate.py

Writes data/mimic/qa/label_yield_projection.json.

Two things this script does NOT do, deliberately:
  * It does not write a profile. If it ever does, it has stopped being a gate.
  * It does not reuse a module from pipelines/mimic/ for the lab pass, because
    labs.py belongs to HC-15, which is downstream of this gate. The chunked read
    here is minimal and is superseded by HC-15.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import vocab  # noqa: E402
from pipelines.common import derive  # noqa: E402
from pipelines.mimic import config, feasibility, icd_sets, omr_bp  # noqa: E402

# PREVENT needs these five measured inputs on top of age/sex/BP/flags. Chol and
# HDL are the scarce ones in an inpatient EHR; creatinine drives eGFR.
_PREVENT_LABS = ("total_chol", "hdl", "creatinine")


def decision_cohort() -> pd.DataFrame:
    """[subject_id, hadm_id, index_admit] for the post-HC-26 decision cohort.

    HC-26's rule, in code: the earliest HTN-anchor admission that BOTH carries a
    medication reconciliation at its own ED stay AND has >=2 OMR BP readings on
    distinct dates within 365 d strictly before admittime. One row per subject.

    Note the linkage is to an actual medrecon, not merely to an ED stay. 9,492
    index encounters are ED-linked but only 8,921 of those stays carry a
    reconciliation, and a stay without one cannot establish on_bp_meds -- which
    is the entire reason the ED linkage is required. Requiring the reconciliation
    reproduces the figure recorded for HC-26 exactly.
    """
    idx = feasibility._earliest_anchor_admit()
    idx = idx[idx["hadm_id"].isin(feasibility.hadms_with_medrecon())]

    bp = omr_bp.load_omr_bp(config.HOSP / "omr.csv.gz")
    j = bp.merge(idx, on="subject_id", how="inner")
    days = (j["index_admit"] - j["chartdate"]).dt.days
    # STRICTLY before the index admission: days >= 1, never 0 or negative. A
    # same-day or later reading is at or after the decision point.
    j = j[(days >= 1) & (days <= config.WINDOW_PRIMARY_DAYS)]

    dates = j.groupby("subject_id")["chartdate"].nunique()
    keep = set(dates[dates >= config.MIN_READINGS_PRIMARY].index)
    return idx[idx["subject_id"].isin(keep)].reset_index(drop=True), j[
        j["subject_id"].isin(keep)
    ]


def bp_summary(readings: pd.DataFrame) -> pd.DataFrame:
    """Per-subject BP and stage from the qualifying pre-index OMR readings.

    MEAN, not median. HC-23 was resolved 2026-08-08 against the guideline source:
    the 2025 AHA/ACC text specifies the average of >=2 readings throughout and
    never specifies a median. NHANES already computes the mean, so this keeps the
    two arms identical -- which is the whole point of the shared derivation core.
    """
    agg = readings.groupby("subject_id")[["sbp", "dbp"]].mean().reset_index()
    agg["bp_n_readings"] = (
        readings.groupby("subject_id")["chartdate"].nunique().values
    )
    agg["bp_stage"] = derive.bp_stage(agg["sbp"], agg["dbp"])
    return agg


def med_status(cohort: pd.DataFrame) -> pd.DataFrame:
    """on_bp_meds / statin_use from ed/medrecon at the INDEX visit only.

    Home meds come only from medrecon. Discharge meds are literally the label and
    inpatient prescriptions are written after the decision, so neither can
    establish whether the patient arrived already treated.

    No reconciliation for the index visit -> NA, never False. Defaulting to False
    would systematically mislabel intensify cases as initiate.
    """
    ed = feasibility._edstays()
    stays = ed.merge(cohort[["subject_id", "hadm_id"]], on=["subject_id", "hadm_id"])

    rec = pd.read_csv(
        config.ED / "medrecon.csv.gz",
        usecols=["subject_id", "stay_id", "name", "gsn", "etcdescription"],
        dtype={"stay_id": "Int64", "name": "string", "etcdescription": "string"},
    )
    rec = rec[rec["stay_id"].isin(set(stays["stay_id"].dropna().astype(int)))]
    # Dedupe as the spec requires, so a repeated reconciliation row cannot make a
    # single drug look like several.
    rec = rec.drop_duplicates(subset=["subject_id", "name", "gsn"])

    rec["_classes"] = rec["name"].map(vocab.classify_drug)
    rec["_statin"] = rec["name"].map(vocab.is_statin)

    per = rec.groupby("subject_id").agg(
        n_rows=("name", "size"),
        any_bp_med=("_classes", lambda g: any(len(c) > 0 for c in g)),
        statin_use=("_statin", "any"),
    ).reset_index()

    out = cohort[["subject_id"]].merge(per, on="subject_id", how="left")
    has_rec = out["n_rows"].notna()
    out["on_bp_meds"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out.loc[has_rec, "on_bp_meds"] = out.loc[has_rec, "any_bp_med"].astype("boolean")
    out["statin_use"] = out["statin_use"].astype("boolean")
    out["has_medrecon"] = has_rec
    return out[["subject_id", "on_bp_meds", "statin_use", "has_medrecon"]]


def icd_flags(cohort: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Comorbidity / contraindication / smoking flags under BOTH time readings.

    Returns (prior_only, prior_plus_index).

    The spec's approved absence rule reads a missing code as False whenever the
    patient has any billed diagnosis row, which is the standard EHR-phenotyping
    reading but biases toward under-treatment where coding is incomplete. The
    spec makes a both-ways sensitivity mandatory, so the gate reports both rather
    than picking one silently:

      prior_only        -- diagnoses from admissions STRICTLY BEFORE the index
                           admittime. Leakage-safe, and what cleaning rule 6
                           ("time-bounded before admittime") literally says.
      prior_plus_index  -- also counts the index encounter's own codes, which is
                           what spec 4.2 describes. Those codes are assigned at
                           discharge, so they are only partly pre-decision.

    If the two differ materially, that gap is a finding for HC-49, not something
    to average away.
    """
    adm = pd.read_csv(
        config.HOSP / "admissions.csv.gz",
        usecols=["subject_id", "hadm_id", "admittime"],
        parse_dates=["admittime"],
    )
    adm = adm[adm["subject_id"].isin(set(cohort["subject_id"]))]
    adm = adm.merge(cohort[["subject_id", "index_admit"]], on="subject_id", how="inner")

    prior_hadms = set(adm.loc[adm["admittime"] < adm["index_admit"], "hadm_id"])
    index_hadms = set(cohort["hadm_id"])

    dx = pd.read_csv(
        config.HOSP / "diagnoses_icd.csv.gz",
        usecols=["subject_id", "hadm_id", "icd_code", "icd_version"],
        dtype={"icd_code": "string", "icd_version": "Int64"},
    )
    dx = dx[dx["subject_id"].isin(set(cohort["subject_id"]))]

    # Classify distinct (code, version) pairs once, then map back -- cheap.
    pairs = dx[["icd_code", "icd_version"]].drop_duplicates()
    pairs["flags"] = [
        icd_sets.classify(c, v) for c, v in zip(pairs["icd_code"], pairs["icd_version"])
    ]
    dx = dx.merge(pairs, on=["icd_code", "icd_version"], how="left")

    def _build(hadms: set) -> pd.DataFrame:
        sub = dx[dx["hadm_id"].isin(hadms)]
        out = pd.DataFrame({"subject_id": cohort["subject_id"]})
        enumerated = set(sub["subject_id"])
        for f in icd_sets.FLAGS:
            pos = set(sub.loc[sub["flags"].apply(lambda s: f in s), "subject_id"])
            # Present -> True. Absent but the patient HAS billed rows -> False.
            # No billed rows at all -> NA: the enumeration does not exist, so
            # absence carries no information (spec 4.2).
            out[f] = [
                True if s in pos else (False if s in enumerated else pd.NA)
                for s in out["subject_id"]
            ]
            out[f] = out[f].astype("boolean")
        out["has_any_dx"] = out["subject_id"].isin(enumerated)
        return out

    return _build(prior_hadms), _build(prior_hadms | index_hadms)


def labs(cohort: pd.DataFrame) -> pd.DataFrame:
    """Most recent value per analyte STRICTLY BEFORE admittime, within 365 d.

    HC-27, exercised in counting form. The old "nearest the index encounter"
    wording is bidirectional and would let a creatinine or potassium drawn DURING
    the index admission set eGFR and the hyperkalemia flag -- a post-decision
    value that plausibly reflects the therapy being evaluated.

    No qualifying value -> NA -> the engine abstains. Never carried forward.
    """
    wanted_ids = {i: a for a, ids in config.LAB_ITEMIDS.items() for i in ids}
    subs = set(cohort["subject_id"])

    frames = []
    reader = pd.read_csv(
        config.HOSP / "labevents.csv.gz",
        usecols=["subject_id", "itemid", "charttime", "valuenum", "valueuom"],
        dtype={"subject_id": "Int64", "itemid": "Int64",
               "valuenum": "float64", "valueuom": "string"},
        parse_dates=["charttime"],
        chunksize=config.LAB_CHUNK_ROWS,
    )
    for n, chunk in enumerate(reader, 1):
        hit = chunk[chunk["itemid"].isin(wanted_ids) & chunk["subject_id"].isin(subs)]
        # valuenum, never value: the text column may hold the deid token "___".
        hit = hit[hit["valuenum"].notna()]
        if len(hit):
            frames.append(hit)
        print(f"    labevents chunk {n}: kept {len(hit):,}", flush=True)

    lab = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["subject_id", "itemid", "charttime", "valuenum", "valueuom"]
    )
    lab["analyte"] = lab["itemid"].map(wanted_ids)
    lab = lab.merge(cohort[["subject_id", "index_admit"]], on="subject_id", how="inner")

    delta = (lab["index_admit"] - lab["charttime"]).dt.total_seconds()
    lab = lab[(delta > 0) & (delta <= config.LAB_LOOKBACK_DAYS * 86400)]

    lab = lab.sort_values(["subject_id", "analyte", "charttime"])
    latest = lab.drop_duplicates(subset=["subject_id", "analyte"], keep="last")
    wide = latest.pivot(index="subject_id", columns="analyte", values="valuenum")

    out = cohort[["subject_id"]].merge(
        wide.reset_index(), on="subject_id", how="left"
    )
    for a in config.LAB_ITEMIDS:
        if a not in out.columns:
            out[a] = pd.NA
    return out


def prevent_computable(cohort, bp, meds, flags, lb) -> pd.Series:
    """Whether PREVENT could actually be computed for each subject.

    Deliberately NOT proxied by the smoking flag. A proxy that answers "do we
    know they smoke?" overstates computability whenever cholesterol or creatinine
    is missing, and overstating computability makes the gate report a healthier
    cohort than exists -- the one direction a go/no-go gate must never fail in.

    Mirrors pipelines.common.prevent.PreventInputs.complete() plus its 30-79 age
    window. Age uses anchor_age, which is a topcoded approximation at the
    patient's anchor year, not at the index admission; it is adequate for a count
    and is replaced by the properly offset age in HC-18.
    """
    df = (
        cohort[["subject_id", "age"]]
        .merge(bp[["subject_id", "sbp"]], on="subject_id", how="left")
        .merge(meds[["subject_id", "on_bp_meds", "statin_use"]], on="subject_id", how="left")
        .merge(flags[["subject_id", "diabetes", "current_smoker"]], on="subject_id", how="left")
        .merge(lb[["subject_id", "total_chol", "hdl", "creatinine"]], on="subject_id", how="left")
    )
    have = (
        df["age"].between(30, 79)
        & df["sbp"].notna()
        & df[list(_PREVENT_LABS)].notna().all(axis=1)
        & df["on_bp_meds"].notna()
        & df["diabetes"].notna()
        & df["current_smoker"].notna()
        & df["statin_use"].notna()
    )
    return pd.Series(have.fillna(False).to_numpy(), index=df.index, name="prevent_computable")


def main() -> int:
    print("HC-98 / B2a label-yield gate -- counting only, no profiles emitted\n")

    print("  building the decision cohort (HC-26 rule)...", flush=True)
    cohort, readings = decision_cohort()
    pts = pd.read_csv(
        config.HOSP / "patients.csv.gz",
        usecols=["subject_id", "gender", "anchor_age"],
    )
    cohort = cohort.merge(pts, on="subject_id", how="left")
    cohort = cohort.rename(columns={"anchor_age": "age"})
    cohort = cohort[cohort["age"] >= config.MIN_AGE]
    print(f"    decision cohort: {len(cohort):,} subjects")

    print("  summarising pre-index OMR BP (mean, per HC-23)...", flush=True)
    bp = bp_summary(readings[readings["subject_id"].isin(set(cohort["subject_id"]))])

    print("  reading ed/medrecon at the index stay...", flush=True)
    meds = med_status(cohort)

    print("  crosswalking diagnoses (both time readings)...", flush=True)
    flags_prior, flags_incl = icd_flags(cohort)

    print("  scanning labevents (itemid-filtered, strictly pre-admittime)...", flush=True)
    lb = labs(cohort)

    report: dict = {
        "generated": "2026-09-20",
        "gate": "HC-98 / B2a",
        "counting_only": True,
        "cohort_rule": (
            "earliest HTN-anchor admission with an index-stay ED medication "
            "reconciliation and >=2 OMR BP on distinct dates within 365 d "
            "strictly before admittime"
        ),
        "bp_summary_statistic": "mean (HC-23 resolved 2026-08-08: the guideline "
                                "specifies the average of >=2 readings)",
        "n_decision_cohort": int(len(cohort)),
    }

    for name, flags in (("prior_only", flags_prior), ("prior_plus_index", flags_incl)):
        pc = prevent_computable(cohort, bp, meds, flags, lb)
        proj_flags = flags.copy()
        proj_flags["prevent_computable"] = pc.to_numpy()
        primary = (
            cohort[["subject_id"]]
            .merge(bp[["subject_id", "bp_stage"]], on="subject_id", how="left")
            .merge(meds[["subject_id", "on_bp_meds"]], on="subject_id", how="left")
        )
        block = feasibility.project_label_yield(primary, proj_flags)
        block["flag_prevalence"] = {
            f: {"true": int((flags[f] == True).sum()),      # noqa: E712
                "false": int((flags[f] == False).sum()),    # noqa: E712
                "unknown": int(flags[f].isna().sum())}
            for f in icd_sets.FLAGS
        }
        block["prevent_computable"] = int(pc.sum())
        report[name] = block

    report["bp_stage_distribution"] = {
        str(k): int(v) for k, v in bp["bp_stage"].value_counts(dropna=False).items()
    }
    report["on_bp_meds_distribution"] = {
        "true": int((meds["on_bp_meds"] == True).sum()),    # noqa: E712
        "false": int((meds["on_bp_meds"] == False).sum()),  # noqa: E712
        "unknown": int(meds["on_bp_meds"].isna().sum()),
    }
    report["lab_coverage"] = {
        a: int(lb[a].notna().sum()) for a in config.LAB_ITEMIDS if a in lb.columns
    }
    # The contraindication counts are the F2 question: hyperkalemia is a lab, the
    # other two are codes. Reported next to NHANES's 9-of-4,806 for comparison.
    k = pd.to_numeric(lb.get("potassium"), errors="coerce")
    report["contraindications"] = {
        "hyperkalemia_k_ge_5_5": int((k >= vocab.K_HYPERKALEMIA).sum()),
        "potassium_measured": int(k.notna().sum()),
        "angioedema_hx": int((flags_incl["angioedema_hx"] == True).sum()),  # noqa: E712
        "pregnancy": int((flags_incl["pregnancy"] == True).sum()),          # noqa: E712
        "nhanes_comparator": "9 of 4,806, all hyperkalemia, zero pregnancy, "
                             "zero angioedema (audit finding F2)",
    }

    out = config.QA / "label_yield_projection.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\nsaved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
