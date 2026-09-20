"""HC-53 — the human spot-check sheet is generated correctly and leaks nothing extra."""
from __future__ import annotations

import json
import re

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


@pytest.fixture
def wide_corpus(tmp_path):
    """A corpus exercising all three abstain mechanisms plus contraindication flags.

    The fixture above only ever produces `stage1_risk_indeterminate`, which is
    exactly the blind spot these tests exist to catch. Returns the corpus dir and
    the profiles it was built from, because contraindication flags live on the
    profile and are deliberately absent from the labels file.
    """
    def row(i, **over):
        base = {
            "SEQN": str(3000 + i), "source": "nhanes", "age": 40.0 + (i % 20),
            "sex": "female" if i % 2 else "male",
            "sbp": 112.0 + 3 * (i % 12), "dbp": 62.0 + 2 * (i % 9),
            "bp_context": "chronic", "bp_n_readings": 3.0, "creatinine": 1.0,
            "egfr": 70.0, "potassium": 4.2, "uacr": 10.0, "ckd_albuminuria": False,
            "diabetes": False, "clinical_cvd": None, "hba1c": 5.5,
            "total_chol": 180.0, "hdl": 50.0, "bmi": 27.0, "current_smoker": False,
            "told_hypertension": True, "on_bp_meds": False, "med_classes": [],
            "statin_use": False, "prevent_10yr": 5.0, "contraindications": [],
        }
        base.update(over)
        return base

    profiles = [row(i, on_bp_meds=i % 2 == 0,
                    med_classes=["acei"] if i % 2 == 0 else [],
                    diabetes=i % 3 == 0)
                for i in range(18)]
    # pregnancy -> scope gate -> pregnancy_management_out_of_scope
    profiles += [row(i, sex="female", contraindications=["pregnancy"])
                 for i in range(18, 21)]
    # unknown medication status -> med_status_unknown
    profiles += [row(i, on_bp_meds=None) for i in range(21, 24)]
    # untreated stage 1, risk determinant unknown -> stage1_risk_indeterminate
    profiles += [row(i, sbp=134.0, dbp=84.0, on_bp_meds=False, diabetes=None,
                     prevent_10yr=None) for i in range(24, 27)]
    # hyperkalemia: a contraindication that does NOT change the decision, so
    # decision stratification cannot see it
    profiles += [row(i, potassium=5.8, contraindications=["hyperkalemia"])
                 for i in range(27, 30)]

    task_b.build(profiles, tmp_path, seed=1)
    return tmp_path, profiles


def _abstain_reasons(corpus) -> set[str]:
    reasons = set()
    for line in (corpus / task_b.LABELS_FILE).read_text().splitlines():
        if line:
            reason = json.loads(line)["abstain_reason"]
            if reason:
                reasons.add(reason)
    return reasons


def _sheet_patients(text: str) -> set[str]:
    return set(re.findall(r"^## \d+\. patient (\S+)", text, flags=re.M))


def test_spotcheck_covers_every_abstain_mechanism(wide_corpus):
    """`abstain` is one word covering three rule paths that render different prose.

    The two rare ones -- the pregnancy scope gate and unknown medication status --
    produce sentences the common path never emits. A sheet showing only
    `stage1_risk_indeterminate` leaves that prose unread by the one gate that can
    catch a leak the token scanner was never told about.
    """
    corpus, profiles = wide_corpus
    present = _abstain_reasons(corpus)
    assert len(present) == 3, "fixture must exercise all three abstain mechanisms"

    text = build_spotcheck(corpus, per_decision=2, seed=4, profiles=profiles)
    for reason in present:
        assert reason in text, f"sheet never shows an {reason} vignette"


def test_spotcheck_includes_contraindication_positive_patients(wide_corpus):
    """Contraindication flags are not in the labels file, so nothing samples for them.

    Hyperkalemia does not change the engine's decision, so its carriers are
    indistinguishable from anyone else under decision stratification -- 9 of 4,806
    in the real corpus, which a 20-patient draw will essentially never show.
    """
    corpus, profiles = wide_corpus
    shown = _sheet_patients(build_spotcheck(corpus, per_decision=2, seed=4,
                                            profiles=profiles))
    for flag in ("pregnancy", "hyperkalemia"):
        carriers = {p["SEQN"] for p in profiles if flag in p["contraindications"]}
        assert carriers, f"fixture must contain a {flag} patient"
        assert shown & carriers, f"no {flag} patient reached the sheet"


def test_spotcheck_declares_when_contraindication_coverage_is_absent(wide_corpus):
    """Without profiles the sheet says so rather than implying it covered them."""
    corpus, _ = wide_corpus
    text = build_spotcheck(corpus, per_decision=2, seed=4, profiles=None)
    assert "contraindication coverage" in text.lower()


def test_spotcheck_supplementary_vignettes_are_leakage_clean(wide_corpus):
    """The added strata quote real vignettes too; the scanner still has to pass."""
    corpus, profiles = wide_corpus
    text = build_spotcheck(corpus, per_decision=2, seed=4, profiles=profiles)
    for chunk in text.split("### ")[1:]:
        body = chunk.split("\n", 1)[1].split("\n---")[0].split("\n## ")[0]
        leakage.assert_clean(body, where="spot-check supplementary block")


def test_spotcheck_stays_deterministic_with_supplementary_strata(wide_corpus):
    corpus, profiles = wide_corpus
    a = build_spotcheck(corpus, per_decision=2, seed=4, profiles=profiles)
    b = build_spotcheck(corpus, per_decision=2, seed=4, profiles=profiles)
    assert a == b
