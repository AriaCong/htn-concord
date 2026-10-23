"""Fetch NHANES .XPT files from CDC into data/nhanes/raw/.

Idempotent: skips files that already exist unless --force. This is the step that
unblocks the pipeline (the raw NHANES files are not in the repo).

    python -m pipelines.nhanes.download            # all registry files
    python -m pipelines.nhanes.download DEMO BPXO  # a subset
    NHANES_CYCLE=P_pre_pandemic python -m pipelines.nhanes.download
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

from . import config

_UA = "htn-concord/0.1 (research; contact: ariacong.dev@gmail.com)"


def _download(url: str, dest: Path, force: bool = False) -> bool:
    if dest.exists() and not force:
        print(f"  skip (exists): {dest.name}")
        return True
    print(f"  GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 (trusted CDC host)
            data = r.read()
    except Exception as exc:  # noqa: BLE001 - report and continue
        print(f"  !! FAILED {url}: {exc}", file=sys.stderr)
        return False
    # CDC returns an HTTP-200 HTML "Page Not Found" for dead paths; a naive save
    # would write that HTML as a .XPT and only fail later at read_sas. Reject
    # anything that is not a SAS XPORT file (must start with the LIBRARY HEADER).
    if not data.startswith(b"HEADER RECORD*******LIBRARY"):
        print(f"  !! NOT an XPORT file (got {data[:40]!r}); not saving {dest.name}",
              file=sys.stderr)
        return False
    dest.write_bytes(data)
    print(f"  saved {dest.name} ({len(data)/1e6:.1f} MB)")
    return True


def main(components: list[str] | None, force: bool) -> int:
    registry = config.file_registry()
    targets = components or list(registry)
    print(f"Cycle={config.CYCLE}  ->  {config.RAW}")
    ok = True
    for comp in targets:
        if comp not in registry:
            print(f"  ?? unknown component {comp!r}; known: {list(registry)}")
            ok = False
            continue
        dest = config.raw_path(comp)
        got = _download(registry[comp], dest, force)
        ok = ok and (got or comp in config.OPTIONAL)
    print("Note: NCHS linked-mortality (.dat) is fetched separately; see mortality.py TODO.")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("components", nargs="*", help="subset of components; default all")
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    args = ap.parse_args()
    raise SystemExit(main(args.components or None, args.force))
