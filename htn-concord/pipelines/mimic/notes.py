"""HC-19 -- discharge-note selection and Task-C silver labels.

Two jobs that must not be confused with one another.

**1. Note selection.** One discharge summary per index ``hadm_id``, deduplicated
on ``note_id``. The text is passed through **verbatim**: de-identification
placeholders (``___``) are preserved exactly as written, and nothing that could
change clinical meaning is stripped, normalised or "cleaned". A pipeline that
tidied the text would be evaluating a different document from the one the
clinician wrote, and imputing across a redaction would invent a fact.

``note/discharge.csv.gz`` is 1.1 GB, so it is read in chunks and filtered by
``hadm_id`` inside the loop, exactly as the lab pass is filtered by itemid.

**2. Silver labels.** Derived from ``diagnoses_icd`` + ``labevents`` +
``medrecon`` -- **never from the note text**. This is the whole point, and it is
easy to get backwards. If the labels were extracted from the note, the task
would be scored against itself and the result would be circular. Deriving them
from structured tables makes Task C a measure of **extraction fidelity**: can
the model recover, from prose, facts we independently know to be true?

That framing is load-bearing for the manuscript. Task C measures whether the
model reads the chart correctly. It does **not** measure guideline concordance,
because the silver labels are themselves imperfect -- a fact true in the
structured record may simply not appear in the note, and the model cannot be
faulted for failing to extract what is not there. Report it as extraction
fidelity with a hand-validated sample, never as concordance.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

import pandas as pd

from . import config

# Facts a reader could plausibly recover from a discharge summary, and which we
# know independently from structured tables. BP staging is deliberately absent:
# chronic stage comes from outpatient OMR, which the note does not contain.
SILVER_FIELDS: tuple[str, ...] = (
    "age", "sex",
    "diabetes", "clinical_cvd", "ckd_albuminuria", "current_smoker",
    "on_bp_meds", "med_classes",
    "creatinine", "potassium", "egfr",
    "contraindications",
)

_NOTE_COLS = ["note_id", "subject_id", "hadm_id", "note_type", "note_seq",
              "charttime", "text"]


def load_discharge_notes(
    path_or_buf: Any,
    hadm_ids: Iterable[int] | None = None,
    chunk_rows: int = 20_000,
) -> pd.DataFrame:
    """Discharge summaries for the given admissions, one row per note.

    Deduplicated on ``note_id``. The ``text`` column is never modified.
    """
    wanted = None if hadm_ids is None else set(hadm_ids)
    frames: list[pd.DataFrame] = []
    reader = pd.read_csv(
        path_or_buf,
        usecols=_NOTE_COLS,
        dtype={"note_id": "string", "subject_id": "Int64", "hadm_id": "Int64",
               "note_type": "string", "note_seq": "Int64", "text": "string"},
        parse_dates=["charttime"],
        chunksize=chunk_rows,
    )
    for chunk in reader:
        hit = chunk[chunk["hadm_id"].notna()]
        if wanted is not None:
            hit = hit[hit["hadm_id"].isin(wanted)]
        if len(hit):
            frames.append(hit)

    if not frames:
        return pd.DataFrame(columns=_NOTE_COLS)
    notes = pd.concat(frames, ignore_index=True)
    return notes.drop_duplicates(subset=["note_id"]).reset_index(drop=True)


def select_index_notes(notes: pd.DataFrame) -> pd.DataFrame:
    """Exactly one discharge summary per ``hadm_id``.

    Where an admission carries several, the lowest ``note_seq`` wins, with
    ``note_id`` as a deterministic tie-break. Picking arbitrarily would make the
    Task-C corpus depend on row order and stop it being reproducible.
    """
    if notes.empty:
        return notes
    ordered = notes.sort_values(["hadm_id", "note_seq", "note_id"])
    return ordered.drop_duplicates(subset=["hadm_id"], keep="first").reset_index(drop=True)


def note_stats(notes: pd.DataFrame) -> dict:
    """Corpus description for the QA report. Counts only; no text is emitted."""
    if notes.empty:
        return {"n_notes": 0, "n_admissions": 0}
    lengths = notes["text"].str.len()
    return {
        "n_notes": int(len(notes)),
        "n_admissions": int(notes["hadm_id"].nunique()),
        "chars_median": float(lengths.median()),
        "chars_p10": float(lengths.quantile(0.10)),
        "chars_p90": float(lengths.quantile(0.90)),
        "notes_with_deid_placeholder": int(
            notes["text"].str.contains("___", regex=False, na=False).sum()
        ),
    }


def silver_labels(profiles: pd.DataFrame) -> pd.DataFrame:
    """The Task-C silver standard, taken from the structured profile.

    Reads only structured columns. It cannot read note text -- ``profiles``
    does not carry any -- and that is enforced rather than merely intended:
    passing a frame with a ``text`` column raises, so a future edit cannot
    quietly make the label circular.
    """
    if "text" in profiles.columns:
        raise ValueError(
            "silver_labels() was handed a frame carrying note text. Silver "
            "labels must come from diagnoses_icd, labevents and medrecon only; "
            "deriving them from the note would score Task C against itself."
        )
    cols = ["subject_id", "hadm_id"] + [
        c for c in SILVER_FIELDS if c in profiles.columns
    ]
    out = profiles[cols].copy()
    out["silver_source"] = "structured: diagnoses_icd + labevents + medrecon"
    return out.reset_index(drop=True)


def build_text_cohort(
    profiles: pd.DataFrame,
    notes_path: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(one note per index admission, matching silver labels)."""
    src = config.NOTE / "discharge.csv.gz" if notes_path is None else notes_path
    notes = select_index_notes(
        load_discharge_notes(src, hadm_ids=set(profiles["hadm_id"].dropna()))
    )
    silver = silver_labels(profiles)
    silver = silver[silver["hadm_id"].isin(set(notes["hadm_id"]))]
    return notes, silver.reset_index(drop=True)


def main() -> int:
    """Build the Task-C text cohort from an existing primary profile table.

    The notes stay LOCAL. `data/` is git-ignored and nothing here is rendered,
    summarised to an external service, or committed -- MIMIC is credentialed,
    and the corpus is derived locally for a local run.

        python -m pipelines.mimic.notes [--absence prior_plus_index]
    """
    import argparse

    ap = argparse.ArgumentParser(description="Task-C note corpus + silver labels")
    ap.add_argument("--absence", default="prior_plus_index",
                    choices=["prior_only", "prior_plus_index"])
    args = ap.parse_args()

    src = config.PROCESSED / f"mimic_profiles_primary_{args.absence}.csv"
    if not src.exists():
        print(f"MISSING {src}\nRun: python -m pipelines.mimic.build_profiles "
              f"--absence {args.absence}")
        return 1

    profiles = pd.read_csv(src)
    for c in ("med_classes", "contraindications"):
        if c in profiles.columns:
            profiles[c] = profiles[c].map(
                lambda v: json.loads(v) if isinstance(v, str) else []
            )

    print(f"Building Task-C text cohort from {len(profiles):,} profiles "
          f"(absence reading = {args.absence})")
    print("  scanning note/discharge (chunked, hadm-filtered)...", flush=True)
    notes_df, silver = build_text_cohort(profiles)

    stats = note_stats(notes_df)
    print(f"  notes: {stats['n_notes']:,} over {stats['n_admissions']:,} admissions")
    print(f"  chars: median {stats.get('chars_median')}, "
          f"p10 {stats.get('chars_p10')}, p90 {stats.get('chars_p90')}")
    print(f"  notes containing a deid placeholder: "
          f"{stats.get('notes_with_deid_placeholder'):,}")

    notes_out = config.PROCESSED / f"mimic_taskc_notes_{args.absence}.csv"
    silver_out = config.PROCESSED / f"mimic_taskc_silver_{args.absence}.csv"
    # Anti-leakage discipline: the model-facing text and the hidden labels are
    # written to PHYSICALLY SEPARATE files, joined only by hadm_id. One file
    # carrying both would make an accidental leak a formatting mistake away.
    notes_df.to_csv(notes_out, index=False)
    for c in ("med_classes", "contraindications"):
        if c in silver.columns:
            silver[c] = silver[c].map(
                lambda v: json.dumps(v if isinstance(v, list) else [])
            )
    silver.to_csv(silver_out, index=False)
    print(f"  wrote {notes_out.name} and {silver_out.name} (separate files, "
          f"joined only by hadm_id)")

    qa_path = config.QA / f"mimic_taskc_{args.absence}.json"
    qa_path.write_text(json.dumps(
        {"absence_reading": args.absence,
         "silver_fields": list(SILVER_FIELDS),
         "silver_source": "structured: diagnoses_icd + labevents + medrecon",
         "framing": "extraction fidelity, NOT guideline concordance",
         **stats},
        indent=2,
    ))
    print(f"  QA -> {qa_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
