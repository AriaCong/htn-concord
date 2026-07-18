"""Tests for the guideline citation registry."""
import pytest

from engine.citations import CITATIONS, cite


def test_cite_returns_matching_citation():
    c = cite("AHA-ACC-2025:stage2-initiate")
    assert c.anchor == "AHA-ACC-2025:stage2-initiate"
    assert "Stage 2" in c.text


def test_cite_unknown_anchor_raises():
    with pytest.raises(KeyError):
        cite("AHA-ACC-2025:does-not-exist")


def test_registry_keys_match_citation_anchors():
    for anchor, c in CITATIONS.items():
        assert c.anchor == anchor


def test_required_anchors_present():
    required = {
        "AHA-ACC-2025:bp-categories",
        "AHA-ACC-2025:stage2-initiate",
        "AHA-ACC-2025:stage1-high-risk-initiate",
        "AHA-ACC-2025:stage1-lowrisk-lifestyle",
        "AHA-ACC-2025:elevated-lifestyle",
        "AHA-ACC-2025:normal-lifestyle",
        "AHA-ACC-2025:bp-goal-130-80",
        "AHA-ACC-2025:acute-context-not-encoded",
        "HTN-CONCORD:abstain-insufficient-data",
    }
    assert required <= set(CITATIONS)
