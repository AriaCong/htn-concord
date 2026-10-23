"""O1 -- confirm every configured lab itemid exists and carries expected units.

d_labitems is small (a few thousand rows), so existence and labels are cheap.
Unit observation requires touching labevents, so it samples the first chunk
rather than scanning ~158M rows: units are near-constant per itemid, and this is
a sanity check, not an audit.

A missing UACR itemid is not cosmetic. Without it MIMIC's CKD flag collapses to
the eGFR limb alone and under-fires, which biases toward under-treatment -- the
unsafe direction. Confirm before anything is built on it.

    python scripts/verify_mimic_itemids.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# Run as `python scripts/verify_mimic_itemids.py` from htn-concord/: scripts/ is
# not a package, so the repo root has to go on the path before pipelines imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.mimic import config  # noqa: E402

# MIMIC records potassium as mEq/L, which is numerically identical to mmol/L for
# a monovalent ion. Recorded as the expectation so a real unit drift still fails.
EXPECTED_UNITS = {
    "creatinine": "mg/dL",
    "potassium": "mEq/L",
    "uacr": "mg/g",
    "hba1c": "%",
    "total_chol": "mg/dL",
    "hdl": "mg/dL",
}


def main() -> int:
    d = pd.read_csv(
        config.HOSP / "d_labitems.csv.gz",
        usecols=["itemid", "label", "fluid", "category"],
    )
    known = d.set_index("itemid")

    wanted = {i for ids in config.LAB_ITEMIDS.values() for i in ids}
    print(f"scanning first {config.LAB_CHUNK_ROWS:,} labevents rows for units\n")
    units: dict[int, set[str]] = {i: set() for i in wanted}
    counts: dict[int, int] = {i: 0 for i in wanted}
    reader = pd.read_csv(
        config.HOSP / "labevents.csv.gz",
        usecols=["itemid", "valuenum", "valueuom"],
        dtype={"itemid": "Int64", "valueuom": "string"},
        chunksize=config.LAB_CHUNK_ROWS,
    )
    first = next(reader)
    hit = first[first["itemid"].isin(wanted)]
    for itemid, grp in hit.groupby("itemid"):
        units[int(itemid)] = set(grp["valueuom"].dropna().unique())
        counts[int(itemid)] = int(len(grp))

    report = {}
    print(f"{'analyte':<12} {'itemid':>7}  {'exists':<7} {'rows':>8}  {'label':<38} units")
    print("-" * 104)
    for analyte, ids in config.LAB_ITEMIDS.items():
        for itemid in ids:
            exists = itemid in known.index
            label = str(known.loc[itemid, "label"]) if exists else "-- NOT IN d_labitems --"
            seen = sorted(units.get(itemid, set()))
            report[str(itemid)] = {
                "analyte": analyte,
                "exists": bool(exists),
                "label": label,
                "fluid": str(known.loc[itemid, "fluid"]) if exists else None,
                "rows_in_first_chunk": counts.get(itemid, 0),
                "units_observed": seen,
                "unit_expected": EXPECTED_UNITS[analyte],
            }
            flag = " " if exists else "!"
            print(f"{flag}{analyte:<11} {itemid:>7}  {str(exists):<7} "
                  f"{counts.get(itemid, 0):>8,}  {label[:38]:<38} {seen}")

    out = config.QA / "itemid_verification.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nsaved -> {out}")

    missing = [k for k, v in report.items() if not v["exists"]]
    if missing:
        print(f"\nMISSING itemids: {missing}")
        print("Record the finding against spec open item O1 before proceeding.")
    mismatched = [
        k for k, v in report.items()
        if v["exists"] and v["units_observed"]
        and v["unit_expected"] not in v["units_observed"]
    ]
    if mismatched:
        print(f"\nUNIT MISMATCH: {mismatched} -- do not use until reconciled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
