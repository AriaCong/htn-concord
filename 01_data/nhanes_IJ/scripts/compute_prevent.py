"""PREVENT base 10-year total-CVD risk for the model-input table.

Uses the shared, validated implementation (00_shared/pipelines/common/prevent.py),
originally written for HTN-Concord. Before computing, it is re-checked against the original
source: every coefficient vs Khan 2024 Supplemental Table S12A, and the table's
worked example (Women 14.684%, Men 16.317%). Any mismatch stops the run.
"""
from pathlib import Path
import hashlib
import json
import sys

import openpyxl
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]  # project root (PhD GenAI)
SHARED = ROOT / '00_shared'
SUPPLEMENT = ROOT / '00_shared/references/NIHMS1953934-supplement-Supplemental_Tables.xlsx'
sys.path.insert(0, str(SHARED))
from pipelines.common import prevent  # noqa: E402

DST = BASE / 'model_input'
# S12A beta-table row label (Total CVD columns) -> prevent.py feature name.
# Every feature plus the constant has its own row, so all 20 are checked directly.
S12A_ROWS = {
    'Age per 10 years': 'cage', 'non-HDL-C per 1 mmol/L': 'non_hdl', 'HDL-C per 0.3 mmol/L': 'hdl',
    'SBP <110 per 20 mmHg': 'sbp_lt110', 'SBP ≥110 per 20 mmHg': 'sbp_ge110', 'Diabetes': 'diabetes',
    'Current smoking': 'smoker', 'eGFR <60, per -15 ml': 'egfr_lt60', 'eGFR 60+, per -15 ml': 'egfr_ge60',
    'Anti-hypertensive use': 'on_bp_meds', 'Statin use': 'statin',
    'Treated SBP ≥110 mm Hg per 20 mm Hg': 'sbp_ge110_x_bpmed', 'Treated non-HDL-C': 'non_hdl_x_statin',
    'Age per 10yr * non-HDL-C per 1 mmol/L': 'cage_x_non_hdl', 'Age per 10yr * HDL-C per 0.3 mml/L': 'cage_x_hdl',
    'Age per 10yr * SBP ≥110 mm Hg per 20 mmHg': 'cage_x_sbp_ge110', 'Age per 10yr * diabetes': 'cage_x_diabetes',
    'Age per 10yr * current smoking': 'cage_x_smoker', 'Age per 10yr * eGFR <60, per -15 ml': 'cage_x_egfr_lt60',
    'Constant': 'intercept',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# S12A worked example (Age 50, TC 200, HDL 45, SBP 160, DM, antiHTN, eGFR 90), risk in percent.
S12A_EXAMPLE = {'women': 14.683939095644824, 'men': 16.317056158151637}


def s12a_reference():
    """S12A coefficients: from the supplement when it is present locally (it is copyrighted
    and not in the repository), otherwise from the committed prevent_coefficient_check.csv,
    which was produced by reading that supplement."""
    if SUPPLEMENT.exists():
        rows = list(openpyxl.load_workbook(SUPPLEMENT, data_only=True)['Table S12A Base 10yr'].iter_rows(values_only=True))
        start = next(i for i, r in enumerate(rows) if r[0] and str(r[0]).startswith('Table. Beta coefficients'))
        beta = {S12A_ROWS[str(r[0]).strip()]: (r[2], r[3]) for r in rows[start:] if r[0] and str(r[0]).strip() in S12A_ROWS}
        risk_row = next(r for r in rows[:start] if r[0] == 'Risk')
        example = {'women': risk_row[2] * 100, 'men': risk_row[3] * 100}
        assert all(abs(example[k] - S12A_EXAMPLE[k]) < 1e-9 for k in example)
        return beta, example, 'supplement xlsx'
    ref = pd.read_csv(DST / 'prevent_coefficient_check.csv', float_precision='round_trip')
    beta = {r.feature: (r.s12a_women, r.s12a_men) for r in ref.itertuples()}
    return beta, S12A_EXAMPLE, 'committed prevent_coefficient_check.csv (supplement not present)'


def verify_coefficients():
    beta, example, source = s12a_reference()
    assert set(beta) == set(prevent.FEATURE_ORDER) | {'intercept'}, set(prevent.FEATURE_ORDER) ^ set(beta)
    checks = []
    for feat, (w, m) in beta.items():
        cw, cm = prevent.COEFFICIENTS['female'][feat], prevent.COEFFICIENTS['male'][feat]
        good = cw == w and cm == m
        checks.append(dict(feature=feat, s12a_women=w, s12a_men=m, prevent_py_women=cw, prevent_py_men=cm, exact_match=good))
        assert good, (feat, w, m, cw, cm)
    ex = dict(age=50, total_chol_mgdl=200, hdl_mgdl=45, sbp=160, on_bp_meds=True, diabetes=True,
              current_smoker=False, egfr=90, statin=False)
    women = prevent.prevent_10yr_cvd_risk(prevent.PreventInputs(sex='female', **ex))
    men = prevent.prevent_10yr_cvd_risk(prevent.PreventInputs(sex='male', **ex))
    assert abs(women - example['women']) < 1e-9 and abs(men - example['men']) < 1e-9
    return checks, dict(women=women, men=men, s12a_women=example['women'], s12a_men=example['men'], reference_source=source)


def main():
    checks, example = verify_coefficients()
    t = pd.read_csv(DST / 'nhanes_IJ_model_input.csv', float_precision='round_trip')
    risk = []
    for r in t.itertuples(index=False):
        risk.append(prevent.prevent_10yr_cvd_risk(prevent.PreventInputs(
            age=float(r.age_years), sex=r.sex, total_chol_mgdl=float(r.total_chol_mgdl),
            hdl_mgdl=float(r.hdl_mgdl), sbp=float(r.sbp_mean), on_bp_meds=bool(r.on_bp_meds),
            diabetes=bool(r.diabetes), current_smoker=bool(r.current_smoker),
            egfr=float(r.egfr), statin=bool(r.statin))))
    out = t[['SEQN', 'cycle']].copy()
    out['prevent_10yr_total_cvd_pct'] = risk
    assert out.prevent_10yr_total_cvd_pct.notna().all(), 'PREVENT returned None for a complete case'
    out['prevent_ge_7_5'] = out.prevent_10yr_total_cvd_pct.ge(7.5).astype('int8')
    out.to_csv(DST / 'nhanes_IJ_prevent.csv', index=False, float_format='%.17g')
    q = out.prevent_10yr_total_cvd_pct.describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_dict()
    by = out.groupby('cycle').prevent_10yr_total_cvd_pct.median().round(3).to_dict()
    summary = dict(model='PREVENT base 10-year total CVD (Khan 2024, Table S12A)', unit='percent',
                   implementation=str((SHARED / 'pipelines/common/prevent.py').relative_to(ROOT)),
                   implementation_sha256=sha(SHARED / 'pipelines/common/prevent.py'),
                   supplement_sha256=sha(SUPPLEMENT) if SUPPLEMENT.exists() else None,
                   coefficients_exactly_matching_s12a=len(checks),
                   worked_example=example, rows=len(out), distribution=q, median_by_cycle=by,
                   n_ge_7_5=int(out.prevent_ge_7_5.sum()),
                   note='Unweighted individual risks; survey weights are in the model-input table')
    pd.DataFrame(checks).to_csv(DST / 'prevent_coefficient_check.csv', index=False)
    (DST / 'prevent_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
