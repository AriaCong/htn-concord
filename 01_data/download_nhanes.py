"""Download the NHANES files this project uses and verify each against nhanes_manifest.csv.

Raw data is not stored in the repository. This script rebuilds 01_data/raw/ from the
CDC/NCHS servers and checks every file's SHA256 against the hash recorded when the
analysis was run, so the cleaning pipeline reproduces the published outputs exactly.

Usage (from the project root):
    python 01_data/download_nhanes.py            # cycles I and J (needed by nhanes_IJ)
    python 01_data/download_nhanes.py --all      # also cycle L (kept separate)
Standard library only. Existing files with a matching hash are skipped.
"""
import argparse
import csv
import hashlib
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'nhanes_manifest.csv'


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def fetch(url, dest):
    """urllib first; some Python builds ship without CA certificates, so fall back to curl."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp, dest.open('wb') as out:
            out.write(resp.read())
    except urllib.error.URLError:
        subprocess.run(['curl', '-sSfL', '--retry', '3', '-o', str(dest), url], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true', help='also download cycle L')
    args = ap.parse_args()
    rows = list(csv.DictReader(MANIFEST.open()))
    if not args.all:
        rows = [r for r in rows if r['required_for_IJ_pipeline'] == 'True']
    failed = []
    for r in rows:
        dest = HERE / r['path']
        if dest.exists() and sha256(dest) == r['sha256']:
            print(f'ok (cached)  {r["path"]}')
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + '.part')
        fetch(r['url'], tmp)
        # CDC returns an HTML "Page Not Found" with HTTP 200 for dead paths, so the
        # hash check is the only reliable test that the right file arrived.
        got = sha256(tmp)
        if got != r['sha256']:
            tmp.unlink()
            failed.append(r['path'])
            print(f'HASH MISMATCH  {r["path"]}  (CDC may have re-released this file)')
            continue
        tmp.replace(dest)
        print(f'downloaded   {r["path"]}')
    if failed:
        sys.exit(f'{len(failed)} file(s) did not match the recorded SHA256: {failed}')
    print(f'All {len(rows)} files present and verified.')


if __name__ == '__main__':
    main()
