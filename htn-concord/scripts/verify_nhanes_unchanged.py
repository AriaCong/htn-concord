"""Byte-identical gate for the B1 shared-core refactor.

The refactor is a MOVE, not a rewrite: NHANES output must not change. This
script hashes the emitted profile CSV and compares it against the baseline
recorded before the refactor began.

This is a MANUAL gate, not a pytest test, because it requires the raw NHANES
.XPT files, which are not committed and are absent in CI.

    python scripts/verify_nhanes_unchanged.py --record   # before the refactor
    python scripts/verify_nhanes_unchanged.py            # after
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "nhanes" / "processed" / "nhanes_profiles_J.csv"
BASELINE = Path(__file__).resolve().parent / "nhanes_baseline_sha256.txt"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true",
                    help="write the current digest as the baseline (only if no baseline exists)")
    ap.add_argument("--force", action="store_true",
                    help="permit --record to overwrite an existing baseline")
    args = ap.parse_args()

    if not CSV.exists():
        print(f"MISSING: {CSV}\nRun: python -m pipelines.nhanes.build_profiles")
        return 1

    digest = sha256(CSV)
    print(f"{CSV.name}: {digest}")

    if args.record:
        if BASELINE.exists() and not args.force:
            existing = BASELINE.read_text().strip()
            print(f"BASELINE ALREADY EXISTS: {existing}")
            print(f"  To re-record intentionally, delete {BASELINE} or use --force")
            return 1
        BASELINE.write_text(digest + "\n")
        print(f"recorded -> {BASELINE}")
        return 0

    if not BASELINE.exists():
        print(f"NO BASELINE at {BASELINE}; run with --record first")
        return 1

    expected = BASELINE.read_text().strip()
    if digest == expected:
        print("MATCH — NHANES output is unchanged")
        return 0
    print(f"MISMATCH\n  expected {expected}\n  got      {digest}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
