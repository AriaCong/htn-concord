"""Vignette renderer (HC-50) — PatientProfile -> facts-only clinical prose.

Deterministic and templated; the only stage that turns a hidden structured row
into model-facing text. See `render.py` for the difficulty-level contract.
"""
from renderer.render import LEVELS, Level, render

__all__ = ["render", "LEVELS", "Level"]
