"""HC-14 — MIMIC-IV OMR blood-pressure parser + context flag.

Turns raw ``hosp/omr`` "Blood Pressure" rows into clean, plausibility-checked,
posture-tagged readings. It does NOT window against the index encounter, apply the
>=2-distinct-dates rule, take medians, or join the anchor cohort -- those belong to
the cohort builder (HC-18). This module's single job is trustworthy per-reading rows.

Leakage-relevant detail: OMR is outpatient, so every reading is tagged
``bp_context="office"``. The engine stages office/chronic BP normally and abstains
only on ``admission`` (ED/ICU) BP, so tagging here keeps chronic staging honest.

    from pipelines.mimic.omr_bp import load_omr_bp, summarize
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

import vocab

# result_value is "SBP/DBP": exactly two 2-3 digit groups around a single slash.
_BP_VALUE_RE = re.compile(r"^\s*(\d{2,3})\s*/\s*(\d{2,3})\s*$")


def _parse(raw: Any) -> tuple[str, tuple[int, int] | None]:
    """Classify one result_value: ('ok', (sbp, dbp)) | ('malformed'|'out_of_range', None).

    Range gate uses the shared vocab plausibility bounds; a reversed reading
    (sbp <= dbp) is treated as out-of-range rather than silently kept.
    """
    if not isinstance(raw, str):
        return ("malformed", None)
    m = _BP_VALUE_RE.match(raw)
    if not m:
        return ("malformed", None)
    sbp, dbp = int(m.group(1)), int(m.group(2))
    if not (vocab.SBP_MIN <= sbp <= vocab.SBP_MAX):
        return ("out_of_range", None)
    if not (vocab.DBP_MIN <= dbp <= vocab.DBP_MAX):
        return ("out_of_range", None)
    if sbp <= dbp:
        return ("out_of_range", None)
    return ("ok", (sbp, dbp))


def parse_bp_value(raw: Any) -> tuple[int, int] | None:
    """Parse a "SBP/DBP" string to (sbp, dbp) ints, or None if malformed/implausible."""
    return _parse(raw)[1]


def normalize_posture(result_name: Any) -> str:
    """Map an OMR BP result_name to a posture: unspecified | sitting | standing | lying.

    Bare "Blood Pressure" (the ~2.8 M primary rows) -> "unspecified"; the positional
    variants ("... Sitting" / "... Standing (1 min)" / "... Lying") get their posture,
    so the cohort builder can use the primary set and treat postures as a sensitivity.
    """
    n = (result_name or "").strip().lower() if isinstance(result_name, str) else ""
    if "lying" in n:
        return "lying"
    if "standing" in n:
        return "standing"
    if "sitting" in n:
        return "sitting"
    return "unspecified"


def _read_bp_rows(path_or_buf: Any) -> pd.DataFrame:
    """Load only the OMR rows whose result_name starts with 'Blood Pressure'."""
    omr = pd.read_csv(
        path_or_buf,
        usecols=["subject_id", "chartdate", "result_name", "result_value"],
        dtype={"result_name": "string", "result_value": "string"},
        parse_dates=["chartdate"],
    )
    return omr[omr["result_name"].str.startswith("Blood Pressure", na=False)].copy()


def load_omr_bp(path_or_buf: Any) -> pd.DataFrame:
    """Clean OMR BP readings: [subject_id, chartdate, sbp, dbp, posture, bp_context].

    Malformed / out-of-range readings are dropped (see ``summarize`` for the counts);
    every surviving row is outpatient, so ``bp_context`` is "office".
    """
    bp = _read_bp_rows(path_or_buf)
    parsed = bp["result_value"].map(parse_bp_value)
    keep = parsed.notna()
    bp = bp.loc[keep].copy()
    bp[["sbp", "dbp"]] = pd.DataFrame(parsed.loc[keep].tolist(), index=bp.index)
    bp["posture"] = bp["result_name"].map(normalize_posture)
    bp["bp_context"] = "office"
    return bp[["subject_id", "chartdate", "sbp", "dbp", "posture", "bp_context"]].reset_index(drop=True)


def summarize(path_or_buf: Any) -> dict:
    """QA counts over the BP-labeled OMR rows: totals, drop reasons, posture mix."""
    bp = _read_bp_rows(path_or_buf)
    status = bp["result_value"].map(lambda v: _parse(v)[0])
    ok = bp.loc[status == "ok"].copy()
    ok["posture"] = ok["result_name"].map(normalize_posture)
    per_subject = ok.groupby("subject_id").size()
    return {
        "bp_rows": int(len(bp)),
        "parsed_ok": int((status == "ok").sum()),
        "dropped_malformed": int((status == "malformed").sum()),
        "dropped_out_of_range": int((status == "out_of_range").sum()),
        "posture_ok": ok["posture"].value_counts().to_dict(),
        "subjects_with_ok_reading": int(per_subject.size),
        "readings_per_subject_median": float(per_subject.median()) if per_subject.size else 0.0,
    }
