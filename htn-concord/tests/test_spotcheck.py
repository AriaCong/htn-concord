"""HC-53 — the human spot-check sheet is generated correctly and leaks nothing extra."""
from __future__ import annotations

import pytest

import leakage
from tasks import task_b
from tasks.spotcheck import build_spotcheck


@pytest.fixture
def corpus(tmp_path):
    profiles = []
    for i in range(24):
        profiles.append({
            "SEQN": str(2000 + i), "source": "nhanes", "age": 40.0 + i,
            "sex": "female" if i % 2 else "male",
            # spread across stages so several decisions appear
            "sbp": 110.0 + 4 * i, "dbp": 60.0 + 2 * i, "bp_context": "chronic",
            "bp_n_readings": 3.0, "creatinine": 1.0, "egfr": 70.0, "potassium": 4.2,
            "uacr": 10.0, "ckd_albuminuria": False, "diabetes": i % 3 == 0,
            "clinical_cvd": None, "hba1c": 5.5, "total_chol": 180.0, "hdl": 50.0,
            "bmi": 27.0, "current_smoker": False, "told_hypertension": True,
            "on_bp_meds": i % 2 == 0, "med_classes": ["acei"] if i % 2 == 0 else [],
            "statin_use": False, "prevent_10yr": 5.0, "contraindications": [],
        })
    task_b.build(profiles, tmp_path, seed=1)
    return tmp_path


def test_spotcheck_is_generated_and_stratified(corpus):
    text = build_spotcheck(corpus, per_decision=2, seed=4)
    assert "facts-only spot-check" in text
    assert "### simple" in text and "### moderate" in text and "### hard" in text
    assert "hidden label" in text


def test_spotcheck_is_deterministic(corpus):
    assert build_spotcheck(corpus, seed=4) == build_spotcheck(corpus, seed=4)


def test_spotcheck_writes_a_file(corpus, tmp_path):
    out = tmp_path / "sheet.md"
    build_spotcheck(corpus, out, per_decision=2)
    assert out.exists() and out.read_text().startswith("# Task B")


def test_spotcheck_vignettes_are_still_leakage_clean(corpus):
    """The sheet quotes the real vignettes; those must pass the scanner.

    The reviewer-facing label headings are exempt by construction -- they are the
    answer key, and this sheet is the one artifact that deliberately shows both
    sides. Only the quoted vignette blocks are scanned.
    """
    text = build_spotcheck(corpus, per_decision=2)
    blocks = []
    for chunk in text.split("### ")[1:]:
        body = chunk.split("\n", 1)[1].split("\n---")[0]
        blocks.append(body.split("\n## ")[0])
    assert blocks
    for block in blocks:
        leakage.assert_clean(block, where="spot-check vignette block")
