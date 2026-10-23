"""Result types shared by every guideline rule (HC-32/33 and later rules).

Pure data. A rule returns an EngineDecision; staging returns a StagingResult so its
abstention reason can propagate to the caller. All frozen so decisions are immutable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    INITIATE_PHARMACOTHERAPY = "initiate_pharmacotherapy"    # untreated: Stage 2, or high-risk Stage 1
    INTENSIFY_PHARMACOTHERAPY = "intensify_pharmacotherapy"  # on meds, still above goal (<130/80)
    LIFESTYLE_ONLY = "lifestyle_only"                        # normal/elevated, or low-risk Stage 1, untreated
    AT_GOAL_CONTINUE = "at_goal_continue"                    # on meds, at goal (<130/80)
    ABSTAIN = "abstain"                                      # determinant unknown, or acute-context BP


@dataclass(frozen=True)
class Citation:
    """A guideline anchor backing a decision step."""
    anchor: str   # e.g. "AHA-ACC-2025:stage2-initiate"
    text: str     # short human-readable guideline statement


@dataclass(frozen=True)
class TraceStep:
    """One step of the engine's reasoning (feeds trace_concordance scoring, HC-39)."""
    rule: str                 # which rule fired, e.g. "bp_staging"
    detail: str               # human-readable reasoning
    citation: str | None = None   # anchor id backing this step


@dataclass(frozen=True)
class StagingResult:
    """Output of the staging rule (HC-32). stage is None when the engine must abstain."""
    stage: str | None
    abstain_reason: str | None   # e.g. "acute_context", "unknown_bp"; None when staged
    citation: Citation
    trace: TraceStep


@dataclass(frozen=True)
class EngineDecision:
    """The canonical, citation-linked, traced decision for one PatientProfile."""
    decision: Decision
    bp_stage: str | None
    triggers: tuple[str, ...]        # e.g. ("diabetes", "prevent_ge_7.5")
    abstain_reason: str | None       # not_encoded reason when decision == ABSTAIN
    citations: tuple[Citation, ...]  # guideline anchors backing the decision
    trace: tuple[TraceStep, ...]     # ordered reasoning steps
    guideline: str = "aha_acc_2025"  # (HC-43) which guideline module produced this; lets
                                     # an AHA-vs-ESC disagreement report be assembled without
                                     # out-of-band bookkeeping. Default keeps the AHA/ACC
                                     # primary path and prior positional construction working.
