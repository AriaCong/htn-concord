"""Guideline citation registry — 2025 AHA/ACC hypertension guideline.

Reference: DOI 10.1161/HYP.0000000000000249. Anchors are stable symbolic ids; the exact
printed section numbers are filled by the citation linker (HC-38) against the source
document. The HTN-CONCORD:* anchor states the engine's own abstention principle.
"""
from __future__ import annotations

from engine.types import Citation

GUIDELINE_DOI = "10.1161/HYP.0000000000000249"

CITATIONS: dict[str, Citation] = {
    "AHA-ACC-2025:bp-categories": Citation(
        "AHA-ACC-2025:bp-categories",
        "BP categories: Normal <120/80; Elevated 120-129/<80; Stage 1 130-139/80-89; Stage 2 >=140/90.",
    ),
    "AHA-ACC-2025:stage2-initiate": Citation(
        "AHA-ACC-2025:stage2-initiate",
        "Stage 2 hypertension (>=140/90): initiate antihypertensive pharmacotherapy plus lifestyle "
        "modification, preferably 2 first-line agents of different classes, ideally as a single-pill "
        "combination.",
    ),
    "AHA-ACC-2025:stage1-high-risk-initiate": Citation(
        "AHA-ACC-2025:stage1-high-risk-initiate",
        "Stage 1 (130-139/80-89): initiate pharmacotherapy when clinical CVD, diabetes, CKD, or PREVENT "
        "10-year total CVD risk >=7.5%; otherwise a 3-6 month lifestyle trial first. Age alone is not a "
        "criterion.",
    ),
    "AHA-ACC-2025:stage1-lowrisk-lifestyle": Citation(
        "AHA-ACC-2025:stage1-lowrisk-lifestyle",
        "Stage 1 with PREVENT <7.5% and no clinical CVD/diabetes/CKD: 3-6 month trial of lifestyle "
        "intervention; initiate pharmacotherapy if BP remains >=130/80 thereafter.",
    ),
    "AHA-ACC-2025:elevated-lifestyle": Citation(
        "AHA-ACC-2025:elevated-lifestyle",
        "Elevated BP: lifestyle modification; no pharmacotherapy indicated.",
    ),
    "AHA-ACC-2025:normal-lifestyle": Citation(
        "AHA-ACC-2025:normal-lifestyle",
        "Normal BP: promote healthy lifestyle; no pharmacotherapy indicated.",
    ),
    "AHA-ACC-2025:bp-goal-130-80": Citation(
        "AHA-ACC-2025:bp-goal-130-80",
        "Treated BP goal <130/80 mmHg; intensify therapy when BP remains above goal.",
    ),
    "AHA-ACC-2025:acute-context-not-encoded": Citation(
        "AHA-ACC-2025:acute-context-not-encoded",
        "Acute-care (ED/ICU/admission) BP does not establish chronic staging; not encoded.",
    ),
    "HTN-CONCORD:abstain-insufficient-data": Citation(
        "HTN-CONCORD:abstain-insufficient-data",
        "Engine abstains (not_encoded) when a determinant required for the decision is unknown.",
    ),
    "HTN-CONCORD:abstain-out-of-scope": Citation(
        "HTN-CONCORD:abstain-out-of-scope",
        "Engine abstains (not_encoded) when the patient falls outside the encoded module's "
        "scope of adult primary hypertension in the non-pregnant adult. Distinct from "
        "insufficient data: more data would not make the encoded rules applicable.",
    ),
}


def cite(anchor: str) -> Citation:
    """Look up a Citation by anchor id; raise KeyError if it is not registered."""
    try:
        return CITATIONS[anchor]
    except KeyError as exc:
        raise KeyError(f"Unknown citation anchor {anchor!r}") from exc
