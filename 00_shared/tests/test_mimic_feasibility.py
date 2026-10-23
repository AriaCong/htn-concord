"""B2a label-yield gate. Synthetic frames only -- no credentialed rows (HC-56)."""
import pandas as pd

from pipelines.mimic import feasibility


def _flags(subject_ids, diabetes=None, cvd=None, prevent=None):
    n = len(subject_ids)
    return pd.DataFrame({
        "subject_id": subject_ids,
        "diabetes": diabetes if diabetes is not None else [False] * n,
        "clinical_cvd": cvd if cvd is not None else [False] * n,
        "prevent_computable": prevent if prevent is not None else [False] * n,
    })


def test_project_label_yield_counts_stage1_as_resolvable_only_with_a_trigger():
    """A Stage-1 patient with no high-risk trigger and no PREVENT abstains.

    This is the failure the gate exists to find: if it dominates, the Primary
    cohort cannot carry the Task-B real-EHR concordance claim.
    """
    primary = pd.DataFrame({
        "subject_id": [1, 2, 3, 4],
        "bp_stage":   ["stage1", "stage1", "stage2", "normal"],
        "on_bp_meds": [True, True, True, True],
    })
    flags = _flags([1, 2, 3, 4], diabetes=[True, False, False, False])

    out = feasibility.project_label_yield(primary, flags)

    # 1: stage1 + diabetes -> resolvable
    # 2: stage1, no trigger, no PREVENT -> stage1_risk_indeterminate
    # 3: stage2 -> resolvable regardless of triggers
    # 4: normal -> resolvable (at-goal / lifestyle branch)
    assert out["resolvable"] == 3
    assert out["abstain_stage1_risk_indeterminate"] == 1


def test_project_label_yield_abstains_when_med_status_unknown():
    """on_bp_meds is the variable separating initiate from intensify."""
    primary = pd.DataFrame({
        "subject_id": [1], "bp_stage": ["stage2"], "on_bp_meds": [pd.NA],
    })
    flags = _flags([1], diabetes=[True], prevent=[True])

    out = feasibility.project_label_yield(primary, flags)

    assert out["resolvable"] == 0
    assert out["abstain_med_status_unknown"] == 1


def test_a_computable_prevent_rescues_an_otherwise_indeterminate_stage1():
    """PREVENT is the third Stage-1 trigger; without it MIMIC Stage-1 collapses."""
    primary = pd.DataFrame({
        "subject_id": [1], "bp_stage": ["stage1"], "on_bp_meds": [False],
    })
    assert feasibility.project_label_yield(primary, _flags([1]))["resolvable"] == 0
    rescued = feasibility.project_label_yield(primary, _flags([1], prevent=[True]))
    assert rescued["resolvable"] == 1


def test_unknown_staging_is_its_own_abstention_reason():
    primary = pd.DataFrame({
        "subject_id": [1], "bp_stage": [None], "on_bp_meds": [True],
    })
    out = feasibility.project_label_yield(primary, _flags([1]))
    assert out["abstain_staging_indeterminate"] == 1
    assert out["resolvable"] == 0


def test_gates_are_counted_once_each_so_the_reasons_sum_to_the_abstentions():
    """A row failing two gates must not be double-counted, or abstain_share and
    the reason breakdown disagree and the gate's headline number is wrong."""
    primary = pd.DataFrame({
        "subject_id": [1, 2], "bp_stage": [None, "stage1"], "on_bp_meds": [pd.NA, True],
    })
    out = feasibility.project_label_yield(primary, _flags([1, 2]))
    reasons = (out["abstain_med_status_unknown"]
               + out["abstain_staging_indeterminate"]
               + out["abstain_stage1_risk_indeterminate"])
    assert reasons == out["n"] - out["resolvable"]


def test_project_label_yield_reports_the_abstain_share():
    primary = pd.DataFrame({
        "subject_id": [1, 2], "bp_stage": ["stage1", "stage2"], "on_bp_meds": [True, True],
    })
    flags = _flags([1, 2], prevent=[False, True])

    out = feasibility.project_label_yield(primary, flags)

    assert out["n"] == 2
    assert out["resolvable"] == 1
    assert out["abstain_share"] == 0.5


def test_a_missing_flag_row_does_not_read_as_a_trigger():
    """A subject absent from the flags frame has unknown comorbidity, which must
    not resolve a Stage-1 case. Missing is not False-then-True."""
    primary = pd.DataFrame({
        "subject_id": [1], "bp_stage": ["stage1"], "on_bp_meds": [True],
    })
    out = feasibility.project_label_yield(primary, _flags([99]))
    assert out["abstain_stage1_risk_indeterminate"] == 1


def test_empty_cohort_does_not_divide_by_zero():
    empty = pd.DataFrame({"subject_id": [], "bp_stage": [], "on_bp_meds": []})
    out = feasibility.project_label_yield(empty, _flags([]))
    assert out["n"] == 0 and out["abstain_share"] == 0.0
