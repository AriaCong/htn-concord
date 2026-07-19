"""Frozen benchmark splits (HC-53).

Assignment is a pure function of the *patient* identity and a salt -- no RNG state,
no ordering dependence, no stored assignment table to drift out of sync.

Two properties this buys, both load-bearing:

* **Patient-level, not case-level.** One patient yields three cases (simple /
  moderate / hard) built from one structured row. Splitting per case would put the
  same patient's simple vignette in train and hard vignette in test, so a model
  memorizing patients would score as generalizing. Splitting on the patient keeps
  all their cases together.
* **Growth-stable.** Because assignment is `hash(patient) < threshold` rather than
  a shuffle-and-slice, adding NHANES cycles or the MIMIC cohort later leaves every
  existing patient in the split it was already in. A shuffle would silently
  reassign the whole benchmark the first time N changed, invalidating any result
  already reported against it.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Mapping

DEFAULT_SALT = "htn-concord-v1"

# Fractions are cumulative thresholds over a uniform hash in [0, 1).
DEFAULT_FRACTIONS: tuple[tuple[str, float], ...] = (
    ("train", 0.60),
    ("dev", 0.20),
    ("test", 0.20),
)

SPLITS: tuple[str, ...] = tuple(name for name, _ in DEFAULT_FRACTIONS)


def _unit_hash(key: str, salt: str) -> float:
    """Map a key to a uniform value in [0, 1) via SHA-256.

    SHA-256 rather than `hash()`: Python salts string hashing per process, so
    `hash()` would reassign the entire benchmark on every interpreter restart.
    """
    digest = hashlib.sha256(f"{salt}|{key}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(1 << 64)


def assign_split(patient_id: str, salt: str = DEFAULT_SALT,
                 fractions: tuple[tuple[str, float], ...] = DEFAULT_FRACTIONS) -> str:
    """The frozen split for one patient. Deterministic across processes and runs."""
    value = _unit_hash(str(patient_id), salt)
    cumulative = 0.0
    for name, fraction in fractions:
        cumulative += fraction
        if value < cumulative:
            return name
    return fractions[-1][0]  # float-rounding tail


def split_counts(patient_ids: Iterable[str], salt: str = DEFAULT_SALT) -> dict[str, int]:
    """Patients per split — reported in the manifest as a sanity check."""
    counts: dict[str, int] = {name: 0 for name in SPLITS}
    for pid in patient_ids:
        counts[assign_split(pid, salt)] += 1
    return counts


def assert_disjoint(cases: Iterable[Mapping[str, str]]) -> None:
    """No patient may appear in two splits.

    Cheap to check, catastrophic to miss: a patient straddling train and test is
    exactly the leakage the split exists to prevent, and it would inflate every
    reported number without producing any visible error.
    """
    seen: dict[str, str] = {}
    for case in cases:
        pid, split = str(case["patient_id"]), str(case["split"])
        if seen.setdefault(pid, split) != split:
            raise AssertionError(
                f"patient {pid} appears in both {seen[pid]!r} and {split!r}")
