"""Forbidden-token scanner — the mechanical half of the leakage discipline (HC-53).

Master Plan principle 4: the structured row is the *hidden label*; the model may see
only raw facts. This module defines what "label-bearing" means as an executable list
and scans model-facing text for it. `renderer/` self-checks against it, the Task-B
builder (HC-53) gates its output on it, and HC-46 can wrap `scan` as a CLI lint.

Three families of forbidden token, each for a distinct reason:

* **Stage names** — `bp_stage` is a label column. A vignette saying "stage 2
  hypertension" hands over the staging sub-decision outright.
* **Decision verbs** — the `Decision` enum in prose form. "Should be started on"
  is the answer, not a fact.
* **Drug-class names** — the recommendation is a set of *classes*. A vignette must
  name a drug ("amlodipine"), never gloss its class ("a calcium channel blocker"),
  or the class-selection sub-decision leaks.

Matching is word-boundary anchored, which is load-bearing rather than cosmetic:
`hydrochlorothiazide` legitimately contains `thiazide`, and a substring scan would
reject every correctly-rendered vignette for a patient on HCTZ. `\\bthiazide\\b`
does not match inside `hydrochlorothiazide` because both neighbours are word
characters. See `test_leakage.py` for the pinned case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- Stage / severity labels -------------------------------------------------
_STAGE_TERMS: tuple[str, ...] = (
    r"stage\s*-?\s*[12]", r"stage1", r"stage2",
    r"elevated blood pressure", r"prehypertension", r"pre-hypertension",
    r"normotensive", r"hypertensive urgency", r"hypertensive emergency",
    r"uncontrolled hypertension", r"resistant hypertension",
)

# --- Decision verbs (the Decision enum, in prose) ----------------------------
_DECISION_TERMS: tuple[str, ...] = (
    # Stemmed, not exact: `\binitiate\b` misses "initiated"/"initiating", which is
    # the form a leaked decision would actually take in prose.
    r"initiat\w*", r"intensif\w*", r"escalat\w*", r"titrat\w*", r"up-?titrat\w*",
    r"add(?:ing)? a second agent",
    r"should (?:be )?(?:start|begin|receive|add|treat)\w*",
    r"needs? (?:treatment|therapy|medication)",
    r"start(?:ing)? (?:her|him|them|the patient) on",
    r"lifestyle only", r"lifestyle[- ]only",
    r"at goal", r"above goal", r"below goal", r"off goal",
    r"treatment goal", r"bp goal", r"blood pressure goal",
    r"abstain", r"abstention",
    r"first[- ]line", r"guideline[- ]concordant", r"guideline[- ]directed",
    r"contraindicat\w*",
)

# --- Drug-class names (the recommendation vocabulary) ------------------------
_CLASS_TERMS: tuple[str, ...] = (
    r"acei", r"arb", r"ace[- ]inhibitors?", r"angiotensin[- ]converting[- ]enzyme",
    r"angiotensin[- ]receptor[- ]blockers?", r"ras[- ]blockade", r"raas[- ]blockade",
    r"thiazide", r"diuretics?", r"ccbs?", r"calcium[- ]channel[- ]blockers?",
    r"dihydropyridine", r"non-?dihydropyridine",
    r"beta[- ]blockers?", r"β[- ]blockers?",
    r"mineralocorticoid[- ]receptor[- ]antagonists?", r"mras?",
    r"alpha[- ]blockers?", r"antihypertensives?", r"anti-?hypertensive therapy",
)

FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = tuple(
    [("stage_label", t) for t in _STAGE_TERMS]
    + [("decision_verb", t) for t in _DECISION_TERMS]
    + [("drug_class", t) for t in _CLASS_TERMS]
)

_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(rf"\b{pat}\b", re.IGNORECASE)) for kind, pat in FORBIDDEN_PATTERNS
)


@dataclass(frozen=True)
class LeakageHit:
    """One forbidden token found in model-facing text."""
    kind: str        # stage_label | decision_verb | drug_class
    matched: str     # the exact text that matched
    start: int       # character offset, so the audit can quote context
    context: str     # surrounding characters, for the audit report

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"[{self.kind}] {self.matched!r} at {self.start}: ...{self.context}..."


def scan(text: str) -> list[LeakageHit]:
    """Every forbidden token in `text`, ordered by position.

    Empty list == the text is clear. This is the predicate HC-53's acceptance
    gate asserts on for every Task-B input.
    """
    hits: list[LeakageHit] = []
    for kind, pattern in _COMPILED:
        for m in pattern.finditer(text):
            lo, hi = max(0, m.start() - 40), min(len(text), m.end() + 40)
            hits.append(LeakageHit(kind, m.group(0), m.start(), text[lo:hi]))
    return sorted(hits, key=lambda h: h.start)


def is_clean(text: str) -> bool:
    """True when no forbidden token appears."""
    return not scan(text)


class LeakageError(AssertionError):
    """Model-facing text carried a label-bearing token."""

    def __init__(self, hits: list[LeakageHit], where: str = "text") -> None:
        detail = "; ".join(str(h) for h in hits[:5])
        super().__init__(f"{len(hits)} leakage hit(s) in {where}: {detail}")
        self.hits = hits


def assert_clean(text: str, where: str = "text") -> None:
    """Raise LeakageError if `text` carries any label-bearing token."""
    hits = scan(text)
    if hits:
        raise LeakageError(hits, where)
