"""Experiment drivers: the pilot (HC-80), and the full runs (HC-81) after it.

Kept apart from `runner/` on purpose. `runner/` is one call; this is the
orchestration around many calls — sampling, replicates, resume, and the
pre-registered kill criteria evaluated as code rather than as prose.
"""
from experiments.pilot import (
    DEFAULT_SPEC,
    CallRecord,
    PilotSpec,
    iter_planned_calls,
    load_records,
    run_pilot,
    select_patients,
    summarize,
)
from experiments.kill_criteria import KillVerdict, evaluate_criteria

__all__ = [
    "CallRecord",
    "DEFAULT_SPEC",
    "KillVerdict",
    "PilotSpec",
    "evaluate_criteria",
    "iter_planned_calls",
    "load_records",
    "run_pilot",
    "select_patients",
    "summarize",
]
