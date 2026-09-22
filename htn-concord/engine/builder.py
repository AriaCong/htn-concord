"""HC-42 — DecisionBuilder: the mutable composition seam for guideline rules.

Before this, each rule constructed a complete, frozen `EngineDecision` and returned it,
so a new rule (drug-class selection, contraindications, ...) had nowhere to add its
citations/trace without re-concatenating tuples in every module. A rule is now a
`(profile, builder) -> None` contribution that mutates a shared, mutable builder;
`evaluate()` freezes the builder exactly once into the immutable `EngineDecision`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.types import Citation, Decision, EngineDecision, TraceStep


@dataclass
class DecisionBuilder:
    """Mutable accumulator that each rule mutates in turn; frozen once by `build()`."""
    guideline: str
    decision: Decision | None = None
    bp_stage: str | None = None
    triggers: list[str] = field(default_factory=list)
    abstain_reason: str | None = None
    citations: list[Citation] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)

    def add(self, citation: Citation, step: TraceStep) -> "DecisionBuilder":
        """Append a citation and its trace step together (the common case). Chainable."""
        self.citations.append(citation)
        self.trace.append(step)
        return self

    def build(self) -> EngineDecision:
        """Freeze into the immutable EngineDecision. Raises if no rule set a decision."""
        if self.decision is None:
            raise ValueError(
                "DecisionBuilder.build() called before any rule set a decision; "
                "a contribution must set builder.decision"
            )
        return EngineDecision(
            decision=self.decision,
            bp_stage=self.bp_stage,
            triggers=tuple(self.triggers),
            abstain_reason=self.abstain_reason,
            citations=tuple(self.citations),
            trace=tuple(self.trace),
            guideline=self.guideline,
        )
