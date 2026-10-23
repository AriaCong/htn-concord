"""Top-level engine entry point: dispatch a PatientProfile to a guideline module.

evaluate() selects the guideline contribution from a registry, lets it mutate a
DecisionBuilder, and freezes the result exactly once (HC-42). Guidelines stay separate
(principle 6): a second module (ESC 2024, HC-41) registers here via `register()` without
editing the first, and every decision carries a `guideline` tag (HC-43) so an AHA-vs-ESC
disagreement report needs no out-of-band bookkeeping.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from engine.builder import DecisionBuilder
from engine.rules.aha_acc_2025 import initiation_intensification as _aha
from engine.types import EngineDecision

# A guideline contribution mutates the builder in place and returns None (HC-42).
Contribution = Callable[[Mapping[str, Any], DecisionBuilder], None]

_GUIDELINES: dict[str, Contribution] = {
    "aha_acc_2025": _aha.contribute,
}


def register(name: str, contribution: Contribution) -> None:
    """Register a guideline contribution under `name`. ESC 2024 (HC-41) lands here."""
    _GUIDELINES[name] = contribution


def evaluate(profile: Mapping[str, Any], guideline: str = "aha_acc_2025") -> EngineDecision:
    """Return the deterministic guideline decision for one PatientProfile.

    `guideline` names a registered module; an unregistered name raises KeyError rather than
    silently falling back, so a typo or a not-yet-built comparator fails loudly.
    """
    contribution = _GUIDELINES[guideline]
    builder = DecisionBuilder(guideline=guideline)
    contribution(profile, builder)
    return builder.build()
