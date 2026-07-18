"""Tests for HC-32 BP staging rule."""
import pytest

from engine.rules.aha_acc_2025.staging import stage_bp


@pytest.mark.parametrize("sbp,dbp,expected", [
    (118, 78, "normal"),
    (120, 79, "elevated"),
    (129, 79, "elevated"),
    (130, 79, "stage1"),   # isolated systolic boundary
    (118, 82, "stage1"),   # isolated diastolic
    (139, 89, "stage1"),
    (140, 85, "stage2"),   # systolic drives
    (135, 90, "stage2"),   # diastolic drives
])
def test_stage_bp_boundaries(sbp, dbp, expected):
    r = stage_bp({"sbp": sbp, "dbp": dbp, "bp_context": "chronic"})
    assert r.stage == expected
    assert r.abstain_reason is None
    assert r.citation.anchor == "AHA-ACC-2025:bp-categories"
    assert r.trace.rule == "bp_staging"


def test_office_context_stages_normally():
    r = stage_bp({"sbp": 145, "dbp": 92, "bp_context": "office"})
    assert r.stage == "stage2"


def test_admission_context_abstains():
    r = stage_bp({"sbp": 180, "dbp": 100, "bp_context": "admission"})
    assert r.stage is None
    assert r.abstain_reason == "acute_context"
    assert r.citation.anchor == "AHA-ACC-2025:acute-context-not-encoded"


def test_missing_bp_abstains():
    r = stage_bp({"sbp": None, "dbp": None, "bp_context": "chronic"})
    assert r.stage is None
    assert r.abstain_reason == "unknown_bp"
