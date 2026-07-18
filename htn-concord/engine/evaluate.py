"""Top-level engine entry point.

Composes the 2025 AHA/ACC rules into one decision for a PatientProfile. Thin for now
(staging -> initiation/intensification, both handled inside recommend()). As later rules
land (HC-34 drug-class selection, HC-36 contraindications), they compose here.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.rules.aha_acc_2025.initiation_intensification import recommend
from engine.types import EngineDecision


def evaluate(profile: Mapping[str, Any]) -> EngineDecision:
    """Return the deterministic guideline decision for one PatientProfile."""
    return recommend(profile)
