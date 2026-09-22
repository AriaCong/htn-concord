"""Input checksum manifest for the MIMIC-IV arm (reproducibility principle 5).

Records, for every file this pipeline consumes: size, SHA-256, and whether that
digest **matches the checksum PhysioNet shipped with the dataset**. The last
part is the point. Recomputing our own hash and storing it proves only that the
file did not change between two of our runs; comparing against the distributed
SHA256SUMS proves we are working from the dataset as published, which is what a
reproduction attempt actually needs to know.

No patient data is read -- only file bytes are hashed, and only digests and
counts are written out.

    python scripts/mimic_input_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.mimic import config  # noqa: E402

# (label, absolute path, dataset root that ships the SHA256SUMS)
def _inputs() -> list[tuple[str, Path, Path]]:
    hosp_root = config.HOSP.parent
    ed_root = config.ED.parent
    note_root = config.NOTE.parent
    return [
        ("hosp/admissions",    config.HOSP / "admissions.csv.gz",     hosp_root),
        ("hosp/patients",      config.HOSP / "patients.csv.gz",       hosp_root),
        ("hosp/diagnoses_icd", config.HOSP / "diagnoses_icd.csv.gz",  hosp_root),
        ("hosp/d_labitems",    config.HOSP / "d_labitems.csv.gz",     hosp_root),
        ("hosp/labevents",     config.HOSP / "labevents.csv.gz",      hosp_root),
        ("hosp/omr",           config.HOSP / "omr.csv.gz",            hosp_root),
        ("ed/edstays",         config.ED / "edstays.csv.gz",          ed_root),
        ("ed/medrecon",        config.ED / "medrecon.csv.gz",         ed_root),
        ("ed/triage",          config.ED / "triage.csv.gz",           ed_root),
        ("ed/vitalsign",       config.ED / "vitalsign.csv.gz",        ed_root),
        ("note/discharge",     config.NOTE / "discharge.csv.gz",      note_root),
    ]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _published(root: Path) -> dict[str, str]:
    """Parse the dataset's shipped SHA256SUMS into {relative path: digest}."""
    sums = root / "SHA256SUMS.txt"
    if not sums.exists():
        return {}
    out = {}
    for line in sums.read_text().splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            out[parts[1].strip()] = parts[0].strip()
    return out


def main() -> int:
    manifest: dict[str, dict] = {}
    mismatches: list[str] = []
    missing: list[str] = []

    print(f"{'input':<20} {'size':>14}  {'published':<10} sha256")
    print("-" * 92)
    for label, path, root in _inputs():
        if not path.exists():
            missing.append(label)
            print(f"{label:<20} {'-- ABSENT --':>14}")
            manifest[label] = {"present": False, "path": str(path)}
            continue

        digest = sha256(path)
        rel = str(path.relative_to(root))
        expected = _published(root).get(rel)
        if expected is None:
            state = "not listed"
        elif expected == digest:
            state = "MATCH"
        else:
            state = "MISMATCH"
            mismatches.append(label)

        manifest[label] = {
            "present": True,
            "path_relative_to_dataset": rel,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "published_sha256": expected,
            "matches_published": expected == digest if expected else None,
        }
        print(f"{label:<20} {path.stat().st_size:>14,}  {state:<10} {digest[:16]}...")

    report = {
        "generated": "2026-09-20",
        "datasets": {
            "mimic_iv": str(config.HOSP.parent.name),
            "mimic_iv_ed": str(config.ED.parent.name),
            "mimic_iv_note": str(config.NOTE.parent.name),
        },
        "inputs": manifest,
        "all_published_checksums_match": not mismatches and not missing,
    }
    out = config.QA / "input_manifest.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nsaved -> {out}")

    if missing:
        print(f"\nABSENT: {missing}")
    if mismatches:
        print(f"\nCHECKSUM MISMATCH: {mismatches}")
        print("The local file differs from the published dataset. Do not build "
              "a benchmark on it until this is explained.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
