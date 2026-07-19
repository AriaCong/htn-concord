"""HC-53 — Task B builder: leakage gate, physical separation, frozen splits."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from engine.evaluate import evaluate
from renderer import LEVELS
from tasks import task_b
from tasks.profiles import load_profiles_csv
from tasks.splits import DEFAULT_SALT, SPLITS, assert_disjoint, assign_split, split_counts

_PROFILES_CSV = Path(__file__).resolve().parents[1] / "data" / "nhanes" / "processed" / "nhanes_profiles_J.csv"


def _profile(seqn: str, **over):
    base = {
        "SEQN": seqn, "source": "nhanes", "age": 68.0, "sex": "female",
        "sbp": 154.0, "dbp": 91.0, "bp_stage": "stage2", "bp_context": "chronic",
        "bp_n_readings": 3.0, "creatinine": 1.3, "egfr": 42.0, "potassium": 4.8,
        "uacr": 55.0, "ckd_albuminuria": True, "diabetes": True, "clinical_cvd": None,
        "hba1c": 7.4, "total_chol": 190.0, "hdl": 48.0, "bmi": 29.2,
        "current_smoker": False, "told_hypertension": True, "on_bp_meds": True,
        "med_classes": ["dhp_ccb"], "statin_use": True, "prevent_10yr": 18.3,
        "contraindications": [],
    }
    base.update(over)
    return base


@pytest.fixture
def profiles():
    return [_profile(str(1000 + i), age=50.0 + i, sbp=120.0 + i) for i in range(12)]


# --- Structure -------------------------------------------------------------
def test_one_case_per_profile_per_level(profiles):
    inputs, labels = task_b.build_cases(profiles)
    assert len(inputs) == len(profiles) * len(LEVELS)
    assert len(labels) == len(inputs)


def test_inputs_carry_no_label_columns(profiles):
    """Physical separation: nothing answer-shaped on a model-facing record."""
    inputs, _ = task_b.build_cases(profiles)
    for record in inputs:
        assert not task_b._LABEL_KEYS.intersection(record), record.keys()
        assert "vignette" in record


def test_labels_carry_the_engine_decision(profiles):
    _, labels = task_b.build_cases(profiles)
    for record in labels:
        assert record["decision"]
        assert "citations" in record and "trace" in record


def test_inputs_and_labels_join_on_case_id(profiles):
    inputs, labels = task_b.build_cases(profiles)
    assert {r["case_id"] for r in inputs} == {r["case_id"] for r in labels}


def test_all_levels_of_a_patient_share_one_label(profiles):
    """The label is a property of the hidden row, so it cannot vary by level."""
    _, labels = task_b.build_cases(profiles)
    by_patient: dict[str, set[str]] = {}
    for record in labels:
        by_patient.setdefault(record["patient_id"], set()).add(record["decision"])
    assert all(len(v) == 1 for v in by_patient.values())


# --- Determinism -----------------------------------------------------------
def test_build_is_deterministic(profiles):
    a = task_b.build_cases(profiles, seed=5)
    b = task_b.build_cases(profiles, seed=5)
    assert a == b


# --- Splits ----------------------------------------------------------------
def test_split_is_patient_level_not_case_level(profiles):
    inputs, _ = task_b.build_cases(profiles)
    by_patient: dict[str, set[str]] = {}
    for record in inputs:
        by_patient.setdefault(record["patient_id"], set()).add(record["split"])
    assert all(len(v) == 1 for v in by_patient.values()), \
        "a patient's levels must not straddle splits"
    assert_disjoint(inputs)


def test_assign_split_is_stable_across_calls():
    first = [assign_split(str(i)) for i in range(200)]
    second = [assign_split(str(i)) for i in range(200)]
    assert first == second
    assert set(first) <= set(SPLITS)


def test_split_assignment_is_growth_stable():
    """Adding patients must not move existing ones between splits."""
    small = {str(i): assign_split(str(i)) for i in range(50)}
    large = {str(i): assign_split(str(i)) for i in range(500)}
    assert all(large[k] == v for k, v in small.items())


def test_splits_are_roughly_the_intended_proportions():
    counts = split_counts([str(i) for i in range(4000)])
    total = sum(counts.values())
    assert total == 4000
    assert 0.55 < counts["train"] / total < 0.65
    assert 0.15 < counts["dev"] / total < 0.25
    assert 0.15 < counts["test"] / total < 0.25


def test_different_salt_gives_a_different_partition():
    a = [assign_split(str(i), salt="a") for i in range(300)]
    b = [assign_split(str(i), salt="b") for i in range(300)]
    assert a != b


def test_assert_disjoint_catches_a_straddling_patient():
    with pytest.raises(AssertionError, match="both"):
        assert_disjoint([{"patient_id": "1", "split": "train"},
                         {"patient_id": "1", "split": "test"}])


# --- Audit -----------------------------------------------------------------
def test_audit_passes_on_a_clean_corpus(profiles):
    inputs, labels = task_b.build_cases(profiles)
    report = task_b.audit(inputs, labels)
    assert report.ok, report.findings
    assert report.n_cases == len(inputs)


def test_audit_catches_a_forbidden_token():
    bad = [{"case_id": "x", "vignette": "The patient has stage 2 hypertension."}]
    report = task_b.audit(bad)
    assert not report.ok
    assert report.n_token_hits >= 1


def test_audit_catches_a_leaked_label_column():
    bad = [{"case_id": "x", "vignette": "BP was 150/95 mmHg.", "bp_stage": "stage2"}]
    report = task_b.audit(bad)
    assert not report.ok
    assert report.n_label_key_hits == 1


def test_audit_catches_misaligned_inputs_and_labels():
    report = task_b.audit(
        [{"case_id": "a", "vignette": "BP was 150/95 mmHg."}],
        [{"case_id": "b"}],
    )
    assert not report.ok
    assert any("align" in f for f in report.findings)


# --- Build gate + freeze ---------------------------------------------------
def test_build_writes_separated_files_and_manifest(profiles, tmp_path):
    manifest = task_b.build(profiles, tmp_path, seed=3)

    inputs_path = tmp_path / task_b.INPUTS_FILE
    labels_path = tmp_path / task_b.LABELS_FILE
    assert inputs_path.exists() and labels_path.exists()
    assert (tmp_path / task_b.MANIFEST_FILE).exists()

    # The model-facing file must contain no answer, in any spelling.
    raw_inputs = inputs_path.read_text()
    assert "decision" not in raw_inputs
    assert "intensify_pharmacotherapy" not in raw_inputs

    assert manifest["leakage_audit"]["passed"] is True
    assert manifest["n_cases"] == len(profiles) * len(LEVELS)
    assert manifest["files"][task_b.INPUTS_FILE]["model_facing"] is True
    assert manifest["files"][task_b.LABELS_FILE]["model_facing"] is False


def test_build_refuses_to_write_a_leaking_corpus(profiles, tmp_path, monkeypatch):
    """The gate must block the write, not just report -- a leaked corpus on disk
    will eventually be used by something."""
    monkeypatch.setattr(task_b, "render",
                        lambda *a, **k: "The patient has stage 2 hypertension and should be started on therapy.")
    with pytest.raises(task_b.LeakageAuditFailed):
        task_b.build(profiles, tmp_path)
    assert not (tmp_path / task_b.INPUTS_FILE).exists(), "nothing may be written on failure"


def test_verify_accepts_a_freshly_built_corpus(profiles, tmp_path):
    built = task_b.build(profiles, tmp_path, seed=3)
    assert task_b.verify(tmp_path) == built


def test_verify_detects_tampering(profiles, tmp_path):
    task_b.build(profiles, tmp_path, seed=3)
    path = tmp_path / task_b.INPUTS_FILE
    path.write_text(path.read_text() + '{"case_id": "sneaky", "vignette": "extra"}\n')
    with pytest.raises(task_b.LeakageAuditFailed, match="checksum"):
        task_b.verify(tmp_path)


def test_build_is_reproducible_byte_for_byte(profiles, tmp_path):
    a = task_b.build(profiles, tmp_path / "a", seed=3)
    b = task_b.build(profiles, tmp_path / "b", seed=3)
    assert a["files"][task_b.INPUTS_FILE]["sha256"] == b["files"][task_b.INPUTS_FILE]["sha256"]
    assert a["files"][task_b.LABELS_FILE]["sha256"] == b["files"][task_b.LABELS_FILE]["sha256"]


def test_profile_without_identifier_is_rejected():
    with pytest.raises(KeyError, match="identifier"):
        task_b.build_cases([{"source": "nhanes", "sbp": 150.0, "dbp": 95.0,
                             "bp_context": "chronic", "on_bp_meds": False}])


# --- Real corpus -----------------------------------------------------------
@pytest.mark.skipif(not _PROFILES_CSV.exists(), reason="HC-10 profiles not built")
def test_real_nhanes_slice_builds_and_audits_clean(tmp_path):
    rows = load_profiles_csv(_PROFILES_CSV, limit=200)
    manifest = task_b.build(rows, tmp_path, seed=13)
    assert manifest["leakage_audit"]["passed"] is True
    assert manifest["n_cases"] == 200 * len(LEVELS)
    assert task_b.verify(tmp_path)


@pytest.mark.skipif(not _PROFILES_CSV.exists(), reason="HC-10 profiles not built")
def test_csv_loader_produces_engine_ready_types():
    """The CSV seam: strings in, typed profile out, engine runs without coercion."""
    rows = load_profiles_csv(_PROFILES_CSV, limit=20)
    assert len(rows) == 20
    for row in rows:
        assert row["sbp"] is None or isinstance(row["sbp"], float)
        assert row["med_classes"] == [] or isinstance(row["med_classes"], list)
        assert row["on_bp_meds"] in (True, False, None)
        assert evaluate(row).decision  # would raise TypeError on raw CSV strings
