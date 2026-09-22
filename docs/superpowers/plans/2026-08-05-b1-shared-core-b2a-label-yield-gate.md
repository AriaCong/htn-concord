# B1 Shared-Core Extraction + B2a Label-Yield Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the source-agnostic derivation/QA/validation code into `pipelines/common/` with NHANES output provably unchanged, then extend the MIMIC feasibility gate to count ED linkage and project the decision-label yield — before any MIMIC profile is built.

**Architecture:** B1 is a *move, not a rewrite*: four modules relocate from `pipelines/nhanes/` to `pipelines/common/`, dropping their NHANES-`config` coupling in favour of importing `vocab` directly. Any behavioural change is a bug, enforced by a SHA-256 comparison of the emitted NHANES CSV before and after. B2a is *counting only* — it produces a JSON report and no profiles, so that a cohort which cannot yield decision labels is discovered before the profile emitter is written.

**Tech Stack:** Python 3.12, pandas 2.3.3, numpy 2.4.2, jsonschema 4.23.0, pytest 9.0.2. No new dependencies.

## Global Constraints

- **No new dependencies.** `requirements.txt` stays at pandas / numpy / jsonschema / pytest. DuckDB and polars were considered and rejected for this cycle.
- **All commands run from `htn-concord/`.** Tests import `engine.*`, `pipelines.*` and `vocab` as top-level modules, which only resolve from there.
- **Never quote a test count in prose, code comments, or commit messages.** Run `pytest -q`. Nine different counts have circulated and every one went stale.
- **Never add `--continue-on-collection-errors`** to any pytest invocation.
- **All test fixtures must be synthetic.** HC-56 records that `tests/test_mimic_omr_bp.py` already contains a verbatim credentialed MIMIC row, which blocks HC-90. Add no new instance.
- **`vocab` is the single source of truth** for BP thresholds, clinical cut-points, med classes, and ICD anchor sets. Never re-derive a threshold locally.
- **Missing means missing.** Never `fillna(False)` a clinical flag, never impute a clinical value, never clip an out-of-range value — reject to `NA`.
- **B2a produces no profiles and no labels.** It is a counting gate. If a step in B2a writes a `PatientProfile`, that step is wrong.
- Every commit message ends with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

## File Structure

**B1 — created:**

| File | Responsibility |
|---|---|
| `pipelines/common/__init__.py` | Package marker |
| `pipelines/common/prevent.py` | PREVENT 10-yr total-CVD model (moved verbatim from `nhanes/prevent.py`) |
| `pipelines/common/derive.py` | eGFR, BP stage, diabetes, CKD, contraindications, PREVENT column (moved from `nhanes/derive.py`; `config.*` → `vocab.*`) |
| `pipelines/common/qa.py` | Range gate + QA report writer (moved from `nhanes/qa.py`; ranges and output path become parameters) |
| `pipelines/common/validate.py` | `patient_profile.schema.json` enforcement (moved verbatim from `nhanes/validate.py`) |
| `scripts/verify_nhanes_unchanged.py` | Manual byte-identical gate — SHA-256 of the emitted CSV |

**B1 — deleted:** `pipelines/nhanes/{prevent,derive,qa,validate}.py`

**B1 — modified:** `pipelines/nhanes/build_profiles.py` (imports), `pipelines/nhanes/config.py` (keeps `RANGES`, drops nothing else), `tests/{test_derive,test_prevent,test_clean_and_qa}.py` (imports)

**B2a — created:**

| File | Responsibility |
|---|---|
| `pipelines/mimic/icd_sets.py` | ICD-9/10 code-set predicates for comorbidity, contraindication and smoking counting |
| `tests/test_mimic_icd_sets.py` | Predicate tests, synthetic codes only |
| `tests/test_mimic_feasibility.py` | ED-linkage and yield-projection tests on synthetic frames |

**B2a — modified:** `pipelines/mimic/config.py` (ED/NOTE paths, lab itemids), `pipelines/mimic/feasibility.py` (ED linkage + label-yield projection)

---

# Phase B1 — Shared-core extraction

### Task 1: Record the pre-refactor baseline

The refactor's acceptance gate is that NHANES output is unchanged. That gate needs a baseline recorded *before* any code moves.

**Files:**
- Create: `scripts/verify_nhanes_unchanged.py`
- Create: `scripts/nhanes_baseline_sha256.txt`

**Interfaces:**
- Produces: `scripts/verify_nhanes_unchanged.py` prints the SHA-256 of `data/nhanes/processed/nhanes_profiles_J.csv` and exits 0 if it matches `scripts/nhanes_baseline_sha256.txt`, 1 otherwise.

- [ ] **Step 1: Write the verification script**

Create `scripts/verify_nhanes_unchanged.py`:

```python
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
import sys
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
                    help="write the current digest as the baseline")
    args = ap.parse_args()

    if not CSV.exists():
        print(f"MISSING: {CSV}\nRun: python -m pipelines.nhanes.build_profiles")
        return 1

    digest = sha256(CSV)
    print(f"{CSV.name}: {digest}")

    if args.record:
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
```

- [ ] **Step 2: Rebuild NHANES from the raw files so the baseline reflects current code**

Run:
```bash
cd htn-concord
source .venv/bin/activate   # create with: python -m venv .venv && pip install -r requirements.txt
python -m pipelines.nhanes.build_profiles
```
Expected: prints the cohort line (`9254 -> 4806`), the schema line, the QA report path, and `wrote .../nhanes_profiles_J.csv`.

If the raw `.XPT` files are missing, run `python -m pipelines.nhanes.download` first.

- [ ] **Step 3: Record the baseline**

Run: `python scripts/verify_nhanes_unchanged.py --record`
Expected: prints a digest and `recorded -> .../nhanes_baseline_sha256.txt`

- [ ] **Step 4: Confirm the gate passes against itself**

Run: `python scripts/verify_nhanes_unchanged.py`
Expected: `MATCH — NHANES output is unchanged`, exit 0

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_nhanes_unchanged.py scripts/nhanes_baseline_sha256.txt
git commit -m "B1: record the pre-refactor NHANES output baseline

The shared-core extraction is a move, not a rewrite, so NHANES output must be
byte-identical afterwards. A manual gate rather than a pytest test because it
needs the raw .XPT files, which are not committed and absent in CI.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Create `pipelines/common/` and move `prevent.py`

`prevent.py` is a pure module with no NHANES coupling, so it moves verbatim. Doing it first proves the package wiring before anything harder moves.

**Files:**
- Create: `pipelines/common/__init__.py`
- Create: `pipelines/common/prevent.py` (moved content)
- Delete: `pipelines/nhanes/prevent.py`
- Modify: `tests/test_prevent.py:8`

**Interfaces:**
- Produces: `pipelines.common.prevent.PreventInputs` (dataclass) and `pipelines.common.prevent.prevent_10yr_cvd_risk(inputs) -> float | None`. Signatures are unchanged from the NHANES location.

- [ ] **Step 1: Repoint the existing test to the new location**

In `tests/test_prevent.py`, change line 8 from:
```python
from pipelines.nhanes import prevent
```
to:
```python
from pipelines.common import prevent
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_prevent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipelines.common'`

- [ ] **Step 3: Create the package and move the module**

```bash
mkdir -p pipelines/common
printf '"""Source-agnostic pipeline code shared by NHANES, MIMIC-IV and eICU."""\n' > pipelines/common/__init__.py
git mv pipelines/nhanes/prevent.py pipelines/common/prevent.py
```

Do not edit the contents of `prevent.py`. It has no relative imports to fix — confirm with:
```bash
grep -n "^from \.\|^from pipelines" pipelines/common/prevent.py
```
Expected: no output.

- [ ] **Step 4: Fix the one importer**

`pipelines/nhanes/derive.py:13` currently reads:
```python
from . import config, prevent
```
Change to:
```python
from pipelines.common import prevent

from . import config
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_prevent.py tests/test_derive.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pipelines/common pipelines/nhanes/derive.py tests/test_prevent.py
git commit -m "B1: move prevent.py to pipelines/common

PREVENT is source-agnostic and has no NHANES coupling, so it moves verbatim.
First of four moves; proves the package wiring before harder ones.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Move `derive.py`, replacing `config.*` constants with `vocab.*`

`derive.py`'s only NHANES coupling is five constants that `pipelines/nhanes/config.py:139-143` already re-exports verbatim from `vocab`. Importing `vocab` directly removes the coupling with no behavioural change.

**Files:**
- Create: `pipelines/common/derive.py` (moved, with import changes)
- Delete: `pipelines/nhanes/derive.py`
- Modify: `tests/test_derive.py:6`, `pipelines/nhanes/build_profiles.py:15`

**Interfaces:**
- Consumes: `pipelines.common.prevent` from Task 2.
- Produces: `pipelines.common.derive` with unchanged signatures —
  `egfr_ckdepi_2021(creatinine: pd.Series, age: pd.Series, sex: pd.Series) -> pd.Series`,
  `bp_stage(sbp: pd.Series, dbp: pd.Series) -> pd.Series`,
  `resolve_diabetes(df: pd.DataFrame) -> pd.Series`,
  `ckd_albuminuria(egfr: pd.Series, uacr: pd.Series) -> pd.Series`,
  `contraindications(df: pd.DataFrame) -> pd.Series`,
  `prevent_10yr(df: pd.DataFrame) -> pd.Series`.

- [ ] **Step 1: Repoint the existing test**

In `tests/test_derive.py`, change line 6 from:
```python
from pipelines.nhanes import derive
```
to:
```python
from pipelines.common import derive
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_derive.py -q`
Expected: FAIL — `ImportError: cannot import name 'derive' from 'pipelines.common'`

- [ ] **Step 3: Move the module**

```bash
git mv pipelines/nhanes/derive.py pipelines/common/derive.py
```

- [ ] **Step 4: Replace the config coupling with vocab**

In `pipelines/common/derive.py`, replace the import block (currently lines 10-13 after Task 2's edit):

```python
import numpy as np
import pandas as pd

from pipelines.common import prevent

from . import config
```

with:

```python
import numpy as np
import pandas as pd

import vocab

from . import prevent
```

Then replace each constant reference. There are exactly six call sites:

| Line (approx) | From | To |
|---|---|---|
| in `bp_stage` | `t = config.BP_THRESHOLDS` | `t = vocab.BP_THRESHOLDS` |
| in `resolve_diabetes` | `config.HBA1C_DIABETES` | `vocab.HBA1C_DIABETES` |
| in `ckd_albuminuria` | `config.EGFR_CKD` | `vocab.EGFR_CKD` |
| in `ckd_albuminuria` | `config.UACR_ALBUMINURIA` | `vocab.UACR_ALBUMINURIA` |
| in `contraindications` | `config.K_HYPERKALEMIA` | `vocab.K_HYPERKALEMIA` |

Verify none remain:
```bash
grep -n "config\." pipelines/common/derive.py
```
Expected: no output.

Also update the module docstring's second paragraph to drop the "(see DATA dict §6)" reference to a NHANES-specific doc section, replacing the first line with:

```python
"""Derived clinical variables shared across all sources.

These turn cleaned columns into engine inputs: eGFR (CKD-EPI 2021 race-free),
BP stage, diabetes resolution, CKD/albuminuria, contraindication flags, and the
PREVENT 10-year risk score. Computing them here (not per-source) keeps the
PatientProfile schema identical across NHANES / MIMIC / eICU. Thresholds come
from ``vocab``, which is the single source of truth for both this module and
``engine/``.
"""
```

- [ ] **Step 5: Repoint `build_profiles.py`**

In `pipelines/nhanes/build_profiles.py`, change line 15 from:
```python
from . import clean, config, derive, drug_class, io_xpt, qa, validate
```
to:
```python
from pipelines.common import derive

from . import clean, config, drug_class, io_xpt, qa, validate
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_derive.py tests/test_prevent.py -q`
Expected: PASS

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS, no collection errors.

- [ ] **Step 8: Commit**

```bash
git add pipelines/common/derive.py pipelines/nhanes/build_profiles.py tests/test_derive.py
git commit -m "B1: move derive.py to pipelines/common, sourcing thresholds from vocab

derive.py's only NHANES coupling was five constants that nhanes/config.py
re-exports verbatim from vocab. Importing vocab directly removes the coupling
with no behavioural change, and removes the possibility of the two drifting --
the failure class that silently mis-staged 56 rows in HC-8.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Move `qa.py`, parameterizing ranges and output path

`qa.py` genuinely depends on NHANES specifics: `config.RANGES`, `config.CYCLE`, and `config.QA` (the output directory). Those become parameters so MIMIC and eICU can supply their own.

**Files:**
- Create: `pipelines/common/qa.py`
- Delete: `pipelines/nhanes/qa.py`
- Modify: `pipelines/nhanes/build_profiles.py`, `tests/test_clean_and_qa.py:5`

**Interfaces:**
- Produces:
  - `pipelines.common.qa.Range` — frozen dataclass with `lo: float`, `hi: float`
  - `apply_ranges(df: pd.DataFrame, ranges: dict[str, Range]) -> tuple[pd.DataFrame, list[dict]]`
  - `write_report(df, violations, row_counts, out_path: Path, extra: dict | None = None) -> Path`
- **Breaking change:** both functions gain a required parameter. `apply_ranges(df)` becomes `apply_ranges(df, ranges)`; `write_report(df, violations, row_counts)` becomes `write_report(df, violations, row_counts, out_path)`.

- [ ] **Step 1: Write the failing test for the parameterized API**

Add to `tests/test_clean_and_qa.py`:

```python
def test_apply_ranges_takes_an_explicit_range_map(tmp_path):
    """Ranges are a parameter, not a NHANES import, so MIMIC can supply its own."""
    from pipelines.common import qa as cqa

    df = pd.DataFrame({"sbp": [120.0, 350.0, 90.0]})
    ranges = {"sbp": cqa.Range(60, 290)}
    out, log = cqa.apply_ranges(df, ranges)

    assert pd.isna(out.loc[1, "sbp"]), "350 mmHg is out of range and must be nulled"
    assert out.loc[0, "sbp"] == 120.0
    assert log == [{"column": "sbp", "lo": 60, "hi": 290, "n_nulled": 1}]


def test_write_report_takes_an_explicit_out_path(tmp_path):
    """The report path is a parameter so each source writes its own QA file."""
    from pipelines.common import qa as cqa

    df = pd.DataFrame({"bp_stage": ["stage1", "normal"], "sbp": [134.0, 110.0]})
    out = tmp_path / "some_qa.json"
    written = cqa.write_report(df, [], {"DEMO": 2}, out)

    assert written == out
    payload = json.loads(out.read_text())
    assert payload["n_profiles"] == 2
    assert payload["bp_stage_distribution"] == {"stage1": 1, "normal": 1}
    assert payload["source_row_counts"] == {"DEMO": 2}
```

Add `import json` to the top of `tests/test_clean_and_qa.py` if not already present.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_clean_and_qa.py -q -k "explicit"`
Expected: FAIL — `ImportError: cannot import name 'qa' from 'pipelines.common'`

- [ ] **Step 3: Move the module and parameterize it**

```bash
git mv pipelines/nhanes/qa.py pipelines/common/qa.py
```

Replace the entire contents of `pipelines/common/qa.py` with:

```python
"""Range gating + QA reporting, shared across every source.

apply_ranges nulls out-of-range numeric values and records every violation.
write_report emits row counts + missingness so QA happens before any label run.

Ranges and the output path are parameters rather than imports: NHANES, MIMIC and
eICU each supply their own, while the gating semantics stay identical. The gate
REJECTS to NA and never clips -- a clipped 350 mmHg becomes a plausible-looking
290 that then produces a confident Stage-2 label from data known to be corrupt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Range:
    lo: float
    hi: float


def apply_ranges(
    df: pd.DataFrame, ranges: dict[str, Range]
) -> tuple[pd.DataFrame, list[dict]]:
    """Set values outside ``ranges`` to NA; return (df, violation log).

    Must run BEFORE derivation: deriving first would let an implausible
    creatinine produce an eGFR based on a value deleted a line later.
    """
    df = df.copy()
    log: list[dict] = []
    for col, rng in ranges.items():
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        bad = (vals < rng.lo) | (vals > rng.hi)
        n_bad = int(bad.fillna(False).sum())
        if n_bad:
            log.append({"column": col, "lo": rng.lo, "hi": rng.hi, "n_nulled": n_bad})
            df.loc[bad.fillna(False), col] = pd.NA
    return df, log


def write_report(
    df: pd.DataFrame,
    violations: list[dict],
    row_counts: dict[str, int],
    out_path: Path,
    extra: dict | None = None,
) -> Path:
    """Emit the per-source QA report. Written BEFORE any label run."""
    report = {
        "n_profiles": int(len(df)),
        "source_row_counts": row_counts,
        "range_violations": violations,
        "missingness": {
            c: round(float(df[c].isna().mean()), 4) for c in df.columns
        },
        "bp_stage_distribution": (
            df["bp_stage"].value_counts(dropna=False).to_dict()
            if "bp_stage" in df else {}
        ),
    }
    # value_counts keys may be NA/np types; coerce to str for JSON.
    report["bp_stage_distribution"] = {
        str(k): int(v) for k, v in report["bp_stage_distribution"].items()
    }
    if extra:
        report.update(extra)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"  QA report -> {out_path}")
    return out_path
```

- [ ] **Step 4: Point `nhanes/config.py` at the shared `Range`**

In `pipelines/nhanes/config.py`, delete the local `Range` dataclass (lines 115-119) and its now-unused `dataclass` import, then import the shared one. Change:

```python
from dataclasses import dataclass, field
```
to:
```python
from pipelines.common.qa import Range
```

and delete:
```python
@dataclass(frozen=True)
class Range:
    lo: float
    hi: float
```

`RANGES` itself stays in `pipelines/nhanes/config.py` — the *values* are NHANES's choice even though the *mechanism* is shared.

Verify nothing else in the file needs `dataclasses` before deleting the import:
```bash
grep -n "field(\|@dataclass" pipelines/nhanes/config.py
```
Expected: no output. If `field(` appears, keep `from dataclasses import field`; if another `@dataclass` appears, keep `from dataclasses import dataclass` as well.

There is no import cycle: `pipelines/common/qa.py` imports only `json`, `dataclasses`, `pathlib` and `pandas`.

- [ ] **Step 5: Repoint `build_profiles.py` to the new call signatures**

In `pipelines/nhanes/build_profiles.py`:

Change the import line to:
```python
from pipelines.common import derive, qa

from . import clean, config, drug_class, io_xpt, validate
```

Change the range-gate call from:
```python
    df, violations = qa.apply_ranges(df)
```
to:
```python
    df, violations = qa.apply_ranges(df, config.RANGES)
```

Change the report call from:
```python
    qa.write_report(df, violations, row_counts)
```
to:
```python
    qa.write_report(
        df, violations, row_counts,
        config.QA / f"nhanes_qa_{config.CYCLE}.json",
        extra={"cycle": config.CYCLE},
    )
```

- [ ] **Step 6: Repoint the existing test**

In `tests/test_clean_and_qa.py`, change line 5 from:
```python
from pipelines.nhanes import clean, qa
```
to:
```python
from pipelines.common import qa
from pipelines.nhanes import clean
```

Then update any existing call in that file from `qa.apply_ranges(df)` to `qa.apply_ranges(df, config.RANGES)`, adding `from pipelines.nhanes import config` to the imports. Find them with:
```bash
grep -n "qa.apply_ranges\|qa.write_report" tests/test_clean_and_qa.py
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/test_clean_and_qa.py -q`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: PASS, no collection errors.

- [ ] **Step 9: Commit**

```bash
git add pipelines/common/qa.py pipelines/nhanes/config.py pipelines/nhanes/build_profiles.py tests/test_clean_and_qa.py
git commit -m "B1: move qa.py to pipelines/common with ranges and report path as parameters

Range VALUES stay a per-source choice in nhanes/config.py; the gating MECHANISM
(reject to NA, never clip; run before derivation) is now shared. write_report
takes an explicit out_path so each source writes its own QA file.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Move `validate.py`

Pure module — its only dependency is the schema path, resolved relative to the repo root. The path depth is unchanged by the move (`parents[2]` from `pipelines/common/` is the same as from `pipelines/nhanes/`), so it moves verbatim.

**Files:**
- Create: `pipelines/common/validate.py`
- Delete: `pipelines/nhanes/validate.py`
- Modify: `pipelines/nhanes/build_profiles.py`

**Interfaces:**
- Produces: `pipelines.common.validate.validate_profiles(df: pd.DataFrame, sample: int | None = None) -> int`. Raises `ValueError` on the first schema violation, naming the offending row index.

- [ ] **Step 1: Write the failing test**

Create `tests/test_common_validate.py`:

```python
"""The canonical-contract gate is shared, so every source validates identically."""
import pandas as pd
import pytest

from pipelines.common import validate


def _valid_row() -> dict:
    return {
        "source": "mimic_iv", "age": 61.0, "sex": "male",
        "sbp": 142.0, "dbp": 88.0, "bp_stage": "stage2", "bp_context": "office",
        "med_classes": ["thiazide"], "contraindications": [],
    }


def test_accepts_a_valid_non_nhanes_row():
    df = pd.DataFrame([_valid_row()])
    assert validate.validate_profiles(df) == 1


def test_rejects_an_unknown_bp_stage():
    row = _valid_row() | {"bp_stage": "stage_1"}
    with pytest.raises(ValueError, match="violates schema"):
        validate.validate_profiles(pd.DataFrame([row]))


def test_rejects_an_unknown_source():
    row = _valid_row() | {"source": "not_a_source"}
    with pytest.raises(ValueError, match="violates schema"):
        validate.validate_profiles(pd.DataFrame([row]))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_common_validate.py -q`
Expected: FAIL — `ImportError: cannot import name 'validate' from 'pipelines.common'`

- [ ] **Step 3: Move the module**

```bash
git mv pipelines/nhanes/validate.py pipelines/common/validate.py
```

Confirm the schema path still resolves — `parents[2]` from `pipelines/common/validate.py` is `htn-concord/`:
```bash
python -c "from pipelines.common import validate; print(validate._SCHEMA_PATH, validate._SCHEMA_PATH.exists())"
```
Expected: the `schemas/patient_profile.schema.json` path and `True`.

- [ ] **Step 4: Repoint `build_profiles.py`**

Change the import line to:
```python
from pipelines.common import derive, qa, validate

from . import clean, config, drug_class, io_xpt
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_common_validate.py -q`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS, no collection errors.

- [ ] **Step 7: Commit**

```bash
git add pipelines/common/validate.py pipelines/nhanes/build_profiles.py tests/test_common_validate.py
git commit -m "B1: move validate.py to pipelines/common

The one-canonical-contract invariant is now enforced from a shared module, with
a test proving a non-NHANES source row validates against the same schema.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Prove NHANES output is unchanged

The acceptance gate for the whole of B1.

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: `scripts/verify_nhanes_unchanged.py` and the baseline from Task 1.

- [ ] **Step 1: Confirm no NHANES module still defines shared logic**

Run:
```bash
ls pipelines/nhanes/
```
Expected: `__init__.py  build_profiles.py  clean.py  config.py  derive.py`… — **`derive.py`, `qa.py`, `validate.py` and `prevent.py` must be ABSENT.** Remaining: `__init__.py`, `build_profiles.py`, `clean.py`, `config.py`, `download.py`, `drug_class.py`, `io_xpt.py`.

- [ ] **Step 2: Confirm nothing imports the old locations**

Run:
```bash
grep -rn "pipelines.nhanes import.*\(derive\|qa\|validate\|prevent\)\|from \.\(derive\|qa\|validate\|prevent\)" --include="*.py" .
```
Expected: no output.

- [ ] **Step 3: Rebuild NHANES**

Run: `python -m pipelines.nhanes.build_profiles`
Expected: same console output as Task 1 Step 2 — cohort `9254 -> 4806`.

- [ ] **Step 4: Run the byte-identical gate**

Run: `python scripts/verify_nhanes_unchanged.py`
Expected: `MATCH — NHANES output is unchanged`, exit 0.

**If this MISMATCHES, stop.** The refactor introduced a behavioural change. Do not proceed to B2a and do not adjust the baseline. Diff the old and new CSV to find the changed column:
```bash
git stash && python -m pipelines.nhanes.build_profiles && cp data/nhanes/processed/nhanes_profiles_J.csv /tmp/before.csv && git stash pop && python -m pipelines.nhanes.build_profiles && diff <(head -1 /tmp/before.csv) <(head -1 data/nhanes/processed/nhanes_profiles_J.csv)
```

- [ ] **Step 5: Run the full suite one final time**

Run: `pytest -q`
Expected: PASS, no collection errors.

- [ ] **Step 6: Commit the verification record**

```bash
git commit --allow-empty -m "B1 acceptance gate: NHANES output verified byte-identical after the refactor

pipelines/common/{prevent,derive,qa,validate}.py now serve every source.
nhanes/ retains only its source-specific code (clean, config, download,
drug_class, io_xpt, build_profiles). Full suite green; the emitted profile CSV
hashes identically to the pre-refactor baseline.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# Phase B2a — Label-yield gate (counting only)

> **B2a produces no profiles and no labels.** If a step here writes a `PatientProfile` row, that step is wrong. Its purpose is to discover *before* the profile emitter is built whether the MIMIC Primary cohort can yield decision labels at all — the failure that Experiment Design finding F2 caught on NHANES only *after* the corpus existed, where it invalidated a co-primary outcome.

### Task 7: Extend the MIMIC config with ED/NOTE paths and lab itemids

**Files:**
- Modify: `pipelines/mimic/config.py`

**Interfaces:**
- Produces: `config.ED` (Path), `config.NOTE` (Path), `config.LAB_ITEMIDS` (`dict[str, tuple[int, ...]]`), `config.LAB_LOOKBACK_DAYS` (int), `config.LAB_LOOKBACK_SENSITIVITY_DAYS` (int).

- [ ] **Step 1: Append the new configuration**

Add to the end of `pipelines/mimic/config.py`:

```python
# MIMIC-IV-ED 2.2 and MIMIC-IV-Note 2.2 ship as separate PhysioNet downloads and
# therefore separate directories. ED supplies medrecon -- the ONLY leakage-safe
# source of on_bp_meds. Note supplies the Task-C discharge summaries.
ED = Path(os.environ.get(
    "MIMIC_ED_DIR", MIMIC_DIR.parent / "mimic-iv-ed-2.2"
)) / "ed"
NOTE = Path(os.environ.get(
    "MIMIC_NOTE_DIR",
    MIMIC_DIR.parent / "mimic-iv-note-deidentified-free-text-clinical-notes-2.2",
)) / "note"

# labevents is 2.4 GB gzipped (~158M rows). ALWAYS filter by itemid inside a
# chunk loop; never load the table whole. Use `valuenum`, never `value`, which
# may hold the deid token "___".
#
# Multiple itemids per analyte because MIMIC carries duplicates across lab
# systems. O1: 51070 (UACR), 52546 and 52024 (creatinine) are UNVERIFIED --
# Task 8 confirms they exist and carry the expected units before any use.
LAB_ITEMIDS: dict[str, tuple[int, ...]] = {
    "creatinine": (50912, 52546, 52024),   # mg/dL
    "potassium":  (50971,),                # mmol/L
    "uacr":       (51070,),                # mg/g -- without it CKD collapses to the eGFR limb
    "hba1c":      (50852,),                # %
    "total_chol": (50907,),                # mg/dL -- PREVENT
    "hdl":        (50904,),                # mg/dL -- PREVENT
}

# Labs bind STRICTLY BEFORE admittime (HC-27). A bidirectional "nearest lab"
# rule would let a value drawn DURING the admission set egfr and the
# hyperkalemia flag -- post-index leakage. 365 d matches the BP window: a
# two-year-old potassium must not set a contraindication.
LAB_LOOKBACK_DAYS = 365
LAB_LOOKBACK_SENSITIVITY_DAYS = 730

# Chunk size for the heavy labevents pass. Chunked pandas rather than DuckDB:
# no new dependency, one idiom across the codebase, and the Parquet cache in
# data/mimic/interim/ absorbs the cost of the slow single-threaded pass.
LAB_CHUNK_ROWS = 5_000_000

INTERIM = ROOT / "data" / "mimic" / "interim"
INTERIM.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: Verify the paths resolve on this machine**

Run:
```bash
python -c "
from pipelines.mimic import config
for name in ('HOSP','ED','NOTE'):
    p = getattr(config, name)
    print(f'{name:5} {p.exists()}  {p}')
"
```
Expected: `True` for all three.

- [ ] **Step 3: Commit**

```bash
git add pipelines/mimic/config.py
git commit -m "B2a: add ED/NOTE paths, lab itemids and the HC-27 lookback window to MIMIC config

Labs bind strictly before admittime with a 365 d window matching BP; 730 d is
recorded as the pre-registered sensitivity. Three itemids are marked unverified
and are confirmed in the next task before any use.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Verify the unverified lab itemids

Open item O1 from the spec. A missing UACR itemid means MIMIC CKD collapses to the eGFR limb and under-fires — an under-treatment bias. Confirm before building anything on it.

**Files:**
- Create: `scripts/verify_mimic_itemids.py`

**Interfaces:**
- Produces: a console table and `data/mimic/qa/itemid_verification.json` recording, per configured itemid, whether it exists in `d_labitems`, its label, fluid, and the distinct `valueuom` values observed.

- [ ] **Step 1: Write the verification script**

Create `scripts/verify_mimic_itemids.py`:

```python
"""O1 -- confirm every configured lab itemid exists and carries expected units.

d_labitems is small (a few thousand rows), so existence and labels are cheap.
Unit observation requires touching labevents, so it samples the first chunk
rather than scanning 158M rows: units are near-constant per itemid, and this is
a sanity check, not an audit.

    python scripts/verify_mimic_itemids.py
"""
from __future__ import annotations

import json

import pandas as pd

from pipelines.mimic import config

EXPECTED_UNITS = {
    "creatinine": "mg/dL",
    "potassium": "mEq/L",     # MIMIC records K+ as mEq/L; numerically == mmol/L
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

    report = {}
    print(f"{'analyte':<12} {'itemid':>7}  {'exists':<7} {'label':<38} units")
    print("-" * 96)
    for analyte, ids in config.LAB_ITEMIDS.items():
        for itemid in ids:
            exists = itemid in known.index
            label = str(known.loc[itemid, "label"]) if exists else "-- NOT IN d_labitems --"
            seen = sorted(units.get(itemid, set()))
            report[str(itemid)] = {
                "analyte": analyte, "exists": bool(exists),
                "label": label, "units_observed": seen,
                "unit_expected": EXPECTED_UNITS[analyte],
            }
            flag = " " if exists else "!"
            print(f"{flag}{analyte:<11} {itemid:>7}  {str(exists):<7} {label[:38]:<38} {seen}")

    out = config.QA / "itemid_verification.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nsaved -> {out}")

    missing = [k for k, v in report.items() if not v["exists"]]
    if missing:
        print(f"\nMISSING itemids: {missing}")
        print("Record the finding in the spec's O1 row before proceeding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it**

Run: `python scripts/verify_mimic_itemids.py`
Expected: a table with one row per configured itemid. This touches the 2.4 GB file's first chunk; allow several minutes.

- [ ] **Step 3: Record the outcome in the spec**

Open `docs/superpowers/specs/2026-08-05-mimic-eicu-data-pipeline-design.md` and update the **O1** row in §9 with the result: which itemids exist, which do not, and the observed units. If `51070` is absent, also update §4.1's `uacr` row and add an explicit note to §8 that MIMIC CKD is eGFR-limb-only, biasing toward under-treatment.

- [ ] **Step 4: Commit**

```bash
git add scripts/verify_mimic_itemids.py docs/superpowers/specs/2026-08-05-mimic-eicu-data-pipeline-design.md data/mimic/qa/itemid_verification.json
git commit -m "B2a: verify the configured MIMIC lab itemids and record the finding

Closes spec open item O1. A missing UACR itemid would collapse MIMIC CKD to the
eGFR limb and under-fire -- an under-treatment bias -- so it is confirmed before
anything is built on it rather than discovered downstream.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: ICD code-set predicates

Counting comorbidity, contraindication and smoking prevalence needs code-set predicates. `vocab` already owns the HTN anchor sets; these are the *other* sets, and they live in the MIMIC package because they exist to read `diagnoses_icd`.

**Files:**
- Create: `pipelines/mimic/icd_sets.py`
- Create: `tests/test_mimic_icd_sets.py`

**Interfaces:**
- Produces: `pipelines.mimic.icd_sets.classify(code: str, version: int | str) -> frozenset[str]` returning any of `{"diabetes", "clinical_cvd", "current_smoker", "angioedema_hx", "pregnancy"}`; and `FLAGS: tuple[str, ...]` naming those five in a fixed order.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mimic_icd_sets.py`:

```python
"""ICD-9/10 code-set predicates for MIMIC comorbidity/contraindication counting.

Synthetic codes only -- no credentialed MIMIC rows (HC-56).
"""
import pytest

from pipelines.mimic import icd_sets


@pytest.mark.parametrize("code,version,flag", [
    ("E119",   10, "diabetes"),        # T2DM without complications
    ("E1065",  10, "diabetes"),        # T1DM with hyperglycemia
    ("25000",   9, "diabetes"),
    ("I2510",  10, "clinical_cvd"),    # atherosclerotic heart disease
    ("I509",   10, "clinical_cvd"),    # heart failure
    ("I639",   10, "clinical_cvd"),    # cerebral infarction
    ("41401",   9, "clinical_cvd"),
    ("4280",    9, "clinical_cvd"),
    ("F1721",  10, "current_smoker"),  # nicotine dependence, cigarettes
    ("Z87891", 10, "current_smoker"),  # personal history of nicotine dependence
    ("3051",    9, "current_smoker"),
    ("T783XXA",10, "angioedema_hx"),   # angioneurotic edema
    ("9951",    9, "angioedema_hx"),
    ("O139",   10, "pregnancy"),       # gestational hypertension
    ("Z3400",  10, "pregnancy"),       # supervision of normal pregnancy
])
def test_positive_classifications(code, version, flag):
    assert flag in icd_sets.classify(code, version)


@pytest.mark.parametrize("code,version", [
    ("I10",   10),   # essential HTN -- the anchor, never a comorbidity flag
    ("4019",   9),
    ("J189",  10),   # pneumonia
    ("",      10),
    ("E11",   10),   # 3-char stub is still diabetes, but see the next test
])
def test_hypertension_anchor_is_never_a_comorbidity_flag(code, version):
    """The anchor selects the encounter; it must never generate a label."""
    if code in ("I10", "4019"):
        assert icd_sets.classify(code, version) == frozenset()


def test_unknown_code_returns_empty_set():
    assert icd_sets.classify("ZZZZZ", 10) == frozenset()
    assert icd_sets.classify(None, 10) == frozenset()


def test_dots_and_case_are_normalised():
    assert "diabetes" in icd_sets.classify("e11.9", 10)
    assert "clinical_cvd" in icd_sets.classify("I25.10", 10)


def test_flags_tuple_is_the_full_vocabulary():
    assert set(icd_sets.FLAGS) == {
        "diabetes", "clinical_cvd", "current_smoker",
        "angioedema_hx", "pregnancy",
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_mimic_icd_sets.py -q`
Expected: FAIL — `ImportError: cannot import name 'icd_sets' from 'pipelines.mimic'`

- [ ] **Step 3: Write the implementation**

Create `pipelines/mimic/icd_sets.py`:

```python
"""ICD-9/10 code-set predicates for MIMIC comorbidity, contraindication and
smoking counting.

These are the sets `vocab` does NOT own. `vocab` owns the hypertension anchor
sets, because the anchor is a cohort-selection concept shared with the engine's
scope rules; these sets exist only to read `hosp/diagnoses_icd`, so they live
with the MIMIC pipeline.

DESIGN INVARIANT: an HTN anchor code selects the patient/encounter. It NEVER
generates a label. `classify` therefore returns an empty set for I10 / 401.x --
staging comes from OMR, never from a code.

Smoking is here because MIMIC has no structured smoking field anywhere, and
PREVENT requires it. Without an ICD limb, prevent_10yr is null for every MIMIC
row and every Stage-1 patient without diabetes/CKD/clinical-CVD abstains.
Extracting smoking from the discharge note is rejected: that note is Task-C
model-facing input, so the label would be circular.
"""
from __future__ import annotations

FLAGS: tuple[str, ...] = (
    "diabetes", "clinical_cvd", "current_smoker", "angioedema_hx", "pregnancy",
)


def _norm(code: str | None) -> str:
    """Uppercase, strip dots and whitespace -- MIMIC stores codes undotted."""
    if not isinstance(code, str):
        return ""
    return code.replace(".", "").replace(" ", "").upper()


# --- ICD-10 prefix sets -----------------------------------------------------
_I10_DIABETES = ("E08", "E09", "E10", "E11", "E13")
_I10_CVD = (
    "I20", "I21", "I22", "I23", "I24", "I25",   # ischaemic heart disease
    "I50",                                      # heart failure
    "I60", "I61", "I62", "I63",                 # cerebrovascular
    "I65", "I66", "I70", "I739",                # atherosclerosis / PAD
)
_I10_SMOKING = ("F17", "Z87891")
_I10_ANGIOEDEMA = ("T783",)
_I10_PREGNANCY = ("O",) + tuple(f"Z34{d}" for d in "0123456789") + ("Z33",)

# --- ICD-9 prefix sets ------------------------------------------------------
_I9_DIABETES = ("250",)
_I9_CVD = (
    "410", "411", "412", "413", "414",   # ischaemic heart disease
    "428",                               # heart failure
    "430", "431", "432", "433", "434",   # cerebrovascular
    "440", "443",                        # atherosclerosis / PAD
)
_I9_SMOKING = ("3051", "V1582")
_I9_ANGIOEDEMA = ("9951",)
_I9_PREGNANCY = ("64", "V22", "V23")     # 640-649 pregnancy complications


def classify(code: str | None, version: int | str) -> frozenset[str]:
    """Return the set of flags a single ICD code contributes. Empty if none.

    Never returns a flag for a hypertension anchor code -- staging comes from
    OMR, and letting a code generate the label would make the benchmark a
    coding-lookup test.
    """
    c = _norm(code)
    if not c:
        return frozenset()

    try:
        v = int(version)
    except (TypeError, ValueError):
        return frozenset()

    if v == 10:
        diabetes, cvd = _I10_DIABETES, _I10_CVD
        smoking, angio, preg = _I10_SMOKING, _I10_ANGIOEDEMA, _I10_PREGNANCY
    elif v == 9:
        diabetes, cvd = _I9_DIABETES, _I9_CVD
        smoking, angio, preg = _I9_SMOKING, _I9_ANGIOEDEMA, _I9_PREGNANCY
    else:
        return frozenset()

    out: set[str] = set()
    if c.startswith(diabetes):
        out.add("diabetes")
    if c.startswith(cvd):
        out.add("clinical_cvd")
    if c.startswith(smoking):
        out.add("current_smoker")
    if c.startswith(angio):
        out.add("angioedema_hx")
    if c.startswith(preg):
        out.add("pregnancy")
    return frozenset(out)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_mimic_icd_sets.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS, no collection errors.

- [ ] **Step 6: Commit**

```bash
git add pipelines/mimic/icd_sets.py tests/test_mimic_icd_sets.py
git commit -m "B2a: ICD-9/10 code-set predicates for MIMIC flag counting

Includes the smoking limb, without which PREVENT is null for every MIMIC row and
every Stage-1 patient without diabetes/CKD/clinical-CVD abstains -- MIMIC has no
structured smoking field anywhere. Deriving smoking from the discharge note is
rejected as circular: that note is Task-C model-facing input.

classify() returns empty for HTN anchor codes, enforcing the design invariant
that the anchor selects the encounter and never generates the label.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: ED linkage and label-yield projection

The gate itself. Extends `feasibility.py` from a BP-only waterfall to one that also counts ED linkage (HC-26) and projects how many Primary-cohort patients could receive a non-ABSTAIN decision label.

**Files:**
- Modify: `pipelines/mimic/feasibility.py`
- Create: `tests/test_mimic_feasibility.py`

**Interfaces:**
- Consumes: `pipelines.mimic.icd_sets.classify` (Task 9), `config.ED` (Task 7), `pipelines.mimic.omr_bp.load_omr_bp`.
- Produces:
  - `_earliest_anchor_admit() -> pd.DataFrame` — **signature change:** now returns columns `[subject_id, hadm_id, index_admit]` (previously dropped `hadm_id`).
  - `ed_linked_hadms() -> set[int]` — `hadm_id`s appearing in `ed/edstays.csv.gz`.
  - `project_label_yield(primary: pd.DataFrame, flags: pd.DataFrame) -> dict` — counts by projected decision-resolvability.
  - `build_waterfall() -> dict` — extended with `PRIMARY_ed_linked` and a `label_yield` block.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mimic_feasibility.py`:

```python
"""B2a label-yield gate. Synthetic frames only -- no credentialed rows (HC-56)."""
import pandas as pd

from pipelines.mimic import feasibility


def test_project_label_yield_counts_stage1_as_resolvable_only_with_a_trigger():
    """A Stage-1 patient with no high-risk trigger and no PREVENT abstains.

    This is the failure the gate exists to find: if it dominates, the Primary
    cohort cannot carry the Task-B real-EHR concordance claim.
    """
    primary = pd.DataFrame({
        "subject_id": [1, 2, 3, 4],
        "bp_stage":   ["stage1", "stage1", "stage2", "normal"],
        "on_bp_meds": [True, True, True, True],
    })
    flags = pd.DataFrame({
        "subject_id":   [1, 2, 3, 4],
        "diabetes":     [True, False, False, False],
        "clinical_cvd": [False, False, False, False],
        "prevent_computable": [False, False, False, False],
    })

    out = feasibility.project_label_yield(primary, flags)

    # subject 1: stage1 + diabetes -> resolvable
    # subject 2: stage1, no trigger, no PREVENT -> stage1_risk_indeterminate
    # subject 3: stage2 -> resolvable regardless of triggers
    # subject 4: normal -> resolvable (lifestyle/at-goal branch)
    assert out["resolvable"] == 3
    assert out["abstain_stage1_risk_indeterminate"] == 1


def test_project_label_yield_abstains_when_med_status_unknown():
    """on_bp_meds is the variable separating initiate from intensify."""
    primary = pd.DataFrame({
        "subject_id": [1],
        "bp_stage":   ["stage2"],
        "on_bp_meds": [pd.NA],
    })
    flags = pd.DataFrame({
        "subject_id": [1], "diabetes": [True],
        "clinical_cvd": [False], "prevent_computable": [True],
    })

    out = feasibility.project_label_yield(primary, flags)

    assert out["resolvable"] == 0
    assert out["abstain_med_status_unknown"] == 1


def test_project_label_yield_reports_the_abstain_share():
    primary = pd.DataFrame({
        "subject_id": [1, 2],
        "bp_stage":   ["stage1", "stage2"],
        "on_bp_meds": [True, True],
    })
    flags = pd.DataFrame({
        "subject_id": [1, 2],
        "diabetes": [False, False], "clinical_cvd": [False, False],
        "prevent_computable": [False, True],
    })

    out = feasibility.project_label_yield(primary, flags)

    assert out["n"] == 2
    assert out["resolvable"] == 1
    assert out["abstain_share"] == 0.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_mimic_feasibility.py -q`
Expected: FAIL — `AttributeError: module 'pipelines.mimic.feasibility' has no attribute 'project_label_yield'`

- [ ] **Step 3: Add the projection function**

Add to `pipelines/mimic/feasibility.py`, after `_omr_bp`:

```python
def project_label_yield(primary: pd.DataFrame, flags: pd.DataFrame) -> dict:
    """Project how many Primary-cohort subjects could receive a NON-ABSTAIN label.

    This is a PROJECTION, not an engine run: it reproduces only the three
    abstention gates that dominate, using columns available at counting time.
    It exists to answer one question before the profile emitter is built --
    can this cohort yield decision labels at all?

    Gates modelled, in the engine's order:
      1. on_bp_meds unknown  -> med_status_unknown (initiate vs intensify
         is undecidable; medrecon is the only leakage-safe source)
      2. bp_stage unknown    -> staging_indeterminate
      3. stage1 with no high-risk trigger and no computable PREVENT
                             -> stage1_risk_indeterminate

    Pregnancy is NOT modelled here: it is a scope gate that precedes staging and
    its MIMIC prevalence is counted separately in build_waterfall.
    """
    df = primary.merge(flags, on="subject_id", how="left")

    med_unknown = df["on_bp_meds"].isna()
    stage_unknown = df["bp_stage"].isna() & ~med_unknown

    trigger = (
        df["diabetes"].fillna(False).astype(bool)
        | df["clinical_cvd"].fillna(False).astype(bool)
        | df["prevent_computable"].fillna(False).astype(bool)
    )
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_mimic_feasibility.py -q`
Expected: PASS

- [ ] **Step 5: Add the ED-linkage helper and carry `hadm_id` through**

In `pipelines/mimic/feasibility.py`, replace `_earliest_anchor_admit` with:

```python
def _earliest_anchor_admit() -> pd.DataFrame:
    """Per subject: the earliest anchor encounter, with its hadm_id retained.

    hadm_id is required for the ED-linkage join (HC-26). The previous version
    dropped it, which is why the ED-linked count had to be established outside
    this module.
    """
    anchor = _anchor_subject_hadms()
    adm = pd.read_csv(
        config.HOSP / "admissions.csv.gz",
        usecols=["subject_id", "hadm_id", "admittime"],
        parse_dates=["admittime"],
    )
    merged = anchor.merge(adm, on=["subject_id", "hadm_id"], how="inner")
    idx = merged.loc[merged.groupby("subject_id")["admittime"].idxmin()]
    return (
        idx[["subject_id", "hadm_id", "admittime"]]
        .rename(columns={"admittime": "index_admit"})
        .reset_index(drop=True)
    )


def ed_linked_hadms() -> set[int]:
    """hadm_ids that have an ED stay -- the precondition for medrecon.

    medrecon is the ONLY leakage-safe source of on_bp_meds, and on_bp_meds is
    the variable separating initiate from intensify. An encounter without ED
    linkage cannot receive the primary decision label (HC-26).
    """
    ed = pd.read_csv(
        config.ED / "edstays.csv.gz",
        usecols=["subject_id", "hadm_id"],
        dtype={"hadm_id": "Int64"},
    )
    return set(ed["hadm_id"].dropna().astype(int).tolist())
```

**Note:** other call sites in this module use only `subject_id` and `index_admit`, both still present, so no further changes are needed there.

- [ ] **Step 6: Wire ED linkage into the waterfall**

In `build_waterfall`, after the existing `n_primary` / `n_fallback` computation, add:

```python
    # --- HC-26: ED linkage, the real decision-cohort constraint ---------------
    # PRIMARY counts subjects surviving the BP rules only. But on_bp_meds must
    # come from ed/medrecon (never discharge meds, which ARE the answer), so a
    # subject without an ED-linked index encounter cannot be labelled.
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
```

and add these two keys to the returned dict, immediately after `"PRIMARY_anchor_ge2_within_365d"`:

```python
        "PRIMARY_ed_linked_DECISION_COHORT": n_primary_ed,
        "PRIMARY_ed_linked_share": (
            round(n_primary_ed / n_primary, 4) if n_primary else 0.0
        ),
```

- [ ] **Step 7: Add the two new rows to the printed waterfall**

In `main()`, insert into the `order` list immediately after the PRIMARY row:

```python
        ("    PRIMARY + ED-linked = DECISION COHORT (HC-26)", "PRIMARY_ed_linked_DECISION_COHORT"),
```

- [ ] **Step 8: Run the gate**

Run: `python -m pipelines.mimic.feasibility`
Expected: the waterfall prints with the new decision-cohort row. Against the recorded HC-13 figures, `PRIMARY_anchor_ge2_within_365d` should reproduce **28,530** and the new ED-linked row should land near **8,921** (~31.3%).

**If `PRIMARY_anchor_ge2_within_365d` does not reproduce 28,530, stop** — the `_earliest_anchor_admit` change altered behaviour it should not have. The `idxmin` rewrite must select the same earliest admission per subject as the previous `groupby().min()`.

- [ ] **Step 9: Run the full suite**

Run: `pytest -q`
Expected: PASS, no collection errors.

- [ ] **Step 10: Commit**

```bash
git add pipelines/mimic/feasibility.py tests/test_mimic_feasibility.py
git commit -m "B2a: ED linkage in the waterfall + the label-yield projection

_earliest_anchor_admit now retains hadm_id so ED linkage can be joined; the
28,530 BP-only PRIMARY count is unchanged, with the ED-linked decision cohort
reported beside it (HC-26).

project_label_yield reproduces the three dominant abstention gates from columns
available at counting time. This is the gate: if Stage-1 risk-indeterminacy
dominates, the Primary cohort cannot carry the Task-B real-EHR concordance claim
and B2b onward must be redesigned. Finding F2 caught the equivalent problem on
NHANES only after the corpus existed, where it invalidated a co-primary outcome.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Run the gate end-to-end and record the verdict

**Files:**
- Modify: `docs/superpowers/specs/2026-08-05-mimic-eicu-data-pipeline-design.md` (§6.1 verdict, §9 open items)

- [ ] **Step 1: Produce the full projection**

The waterfall from Task 10 counts cohort membership. The yield projection additionally needs, for the decision cohort: `bp_stage` (from OMR medians), `on_bp_meds` (medrecon presence), and the flag columns. Run:

```bash
python - <<'PY'
import json
import pandas as pd
from pipelines.mimic import config, feasibility, icd_sets, omr_bp
from pipelines.common import derive

idx = feasibility._earliest_anchor_admit()
ed = feasibility.ed_linked_hadms()
idx = idx[idx["hadm_id"].isin(ed)]

bp = omr_bp.load_omr_bp(config.HOSP / "omr.csv.gz")
j = bp.merge(idx, on="subject_id", how="inner")
j = j[(j["index_admit"] - j["chartdate"]).dt.days.between(1, config.WINDOW_PRIMARY_DAYS)]
ok = j.groupby("subject_id")["chartdate"].nunique()
ok = ok[ok >= config.MIN_READINGS_PRIMARY].index
j = j[j["subject_id"].isin(ok)]

med = j.groupby("subject_id")[["sbp", "dbp"]].median().reset_index()
med["bp_stage"] = derive.bp_stage(med["sbp"], med["dbp"])

rec = pd.read_csv(config.ED / "medrecon.csv.gz", usecols=["subject_id"])
has_rec = set(rec["subject_id"].unique())
med["on_bp_meds"] = med["subject_id"].map(
    lambda s: True if s in has_rec else pd.NA
)

dx = pd.read_csv(config.HOSP / "diagnoses_icd.csv.gz",
                 usecols=["subject_id", "icd_code", "icd_version"],
                 dtype={"icd_code": "string", "icd_version": "Int64"})
dx = dx[dx["subject_id"].isin(med["subject_id"])]
pairs = dx[["icd_code", "icd_version"]].drop_duplicates()
pairs["flags"] = [icd_sets.classify(c, v) for c, v in
                  zip(pairs["icd_code"], pairs["icd_version"])]
dx = dx.merge(pairs, on=["icd_code", "icd_version"], how="left")

flags = pd.DataFrame({"subject_id": med["subject_id"]})
for f in icd_sets.FLAGS:
    pos = set(dx.loc[dx["flags"].apply(lambda s: f in s), "subject_id"])
    flags[f] = flags["subject_id"].isin(pos)
flags["prevent_computable"] = flags["current_smoker"]  # coarse proxy at gate time

out = feasibility.project_label_yield(
    med[["subject_id", "bp_stage", "on_bp_meds"]], flags)
out["flag_prevalence"] = {f: int(flags[f].sum()) for f in icd_sets.FLAGS}
out["bp_stage_distribution"] = {
    str(k): int(v) for k, v in med["bp_stage"].value_counts(dropna=False).items()}

p = config.QA / "label_yield_projection.json"
p.write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
print(f"\nsaved -> {p}")
PY
```

Expected: a JSON block reporting `n`, `resolvable`, the three abstention counts, `abstain_share`, per-flag prevalence, and the BP-stage distribution.

- [ ] **Step 2: Record the verdict in the spec**

Add a new subsection **§6.3 Gate result** to the spec, stating the date, the decision-cohort N, the projected `abstain_share`, the dominant abstention reason, and one of two verdicts:

- **PASS** — `abstain_share` leaves a usable decision cohort. Proceed to B2b.
- **FAIL** — Stage-1 risk-indeterminacy dominates. Do not proceed to B2b; re-open §3.2 and consider whether the Primary cohort should be defined on Stage-2 patients only, or whether the ICD smoking limb needs widening.

Also record the observed `angioedema_hx` and `pregnancy` prevalence, since §1.2 claims MIMIC exercises engine rules NHANES cannot — that claim is now checkable and must be either confirmed with a number or withdrawn.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-05-mimic-eicu-data-pipeline-design.md data/mimic/qa/label_yield_projection.json
git commit -m "B2a gate result: record the MIMIC decision-cohort label yield

Records the projected abstention share and its dominant reason, plus the
observed angioedema and pregnancy prevalence, which makes the spec's claim that
MIMIC exercises two engine rules NHANES cannot either confirmed with a number or
withdrawn.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Definition of done

- [ ] `pipelines/common/{__init__,prevent,derive,qa,validate}.py` exist; the corresponding files are gone from `pipelines/nhanes/`
- [ ] `grep -rn "from \.\(derive\|qa\|validate\|prevent\)" --include="*.py" pipelines/` returns nothing
- [ ] `python scripts/verify_nhanes_unchanged.py` prints MATCH
- [ ] `pytest -q` passes with no collection errors
- [ ] `python -m pipelines.mimic.feasibility` prints the decision-cohort row and reproduces 28,530 for BP-only PRIMARY
- [ ] `data/mimic/qa/itemid_verification.json` and `data/mimic/qa/label_yield_projection.json` exist
- [ ] The spec's §6.3 records a PASS/FAIL verdict, and O1 is closed
- [ ] No test count appears in any prose, comment, or commit message
- [ ] No new dependency in `requirements.txt`

## Not in scope

- Any `PatientProfile` emission from MIMIC (that is B2b)
- `cohort.py`, `labs.py`, `meds.py`, `notes.py` (B2b–B4)
- The eICU probe (B5)
- The MIMIC walkthrough documentation (B6)
- Engine rules HC-34..39
