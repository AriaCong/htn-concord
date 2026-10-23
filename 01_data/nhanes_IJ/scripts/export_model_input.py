"""Export the 5,816 complete-case participants as one tidy model-input table.

Reads only output/analysis/complete_*.csv; writes model_input/nhanes_IJ_model_input.csv.
Binary predictors are written as 0/1; nothing is filled or recomputed.
"""
from pathlib import Path
import json

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / 'output/analysis'
DST = BASE / 'model_input'
TOKEN = '__SOURCE_MISSING__'

PREDICTORS = ['age_years', 'sex', 'total_chol_mgdl', 'hdl_mgdl', 'sbp_mean', 'egfr',
              'diabetes', 'on_bp_meds', 'current_smoker', 'statin']
BINARY = ['diabetes', 'on_bp_meds', 'current_smoker', 'statin']
# Kept beside the predictors: provenance of skip-logic answers, survey design,
# and supplementary measures (race for PCE, DBP, BMI, UACR, HbA1c).
EXTRA_DERIVED = ['on_bp_meds_source', 'current_smoker_source', 'non_hdl_mgdl', 'dbp_mean',
                 'creatinine_J_scale', 'wtmec_pooled', 'wtint_pooled']
EXTRA_ORIGINAL = {'DEMO__RIDRETH3': 'race_ethnicity_ridreth3', 'DEMO__SDMVPSU': 'sdmvpsu',
                  'DEMO__SDMVSTRA': 'sdmvstra', 'BMX__BMXBMI': 'bmi', 'ALB_CR__URDACT': 'uacr_mg_g',
                  'GHB__LBXGH': 'hba1c_pct'}


def read(path):
    return pd.read_csv(path, keep_default_na=False, na_values=[TOKEN], float_precision='round_trip', low_memory=False)


def main():
    d = read(SRC / 'complete_derived.csv')
    o = read(SRC / 'complete_original_values.csv')
    assert d.SEQN.equals(o.SEQN) and d.SEQN.is_unique
    t = d[['SEQN', 'cycle'] + PREDICTORS + EXTRA_DERIVED].copy()
    for c in BINARY:
        v = t[c].astype(str).str.lower().map({'true': 1, 'false': 0})
        assert v.notna().all(), c
        t[c] = v.astype('int8')
    for src, name in EXTRA_ORIGINAL.items():
        t[name] = o[src].to_numpy()
    assert len(t) == 5816 and t[PREDICTORS].notna().all().all()
    assert t.sex.isin(['male', 'female']).all() and t.age_years.between(30, 79).all()
    DST.mkdir(exist_ok=True)
    t.to_csv(DST / 'nhanes_IJ_model_input.csv', index=False, float_format='%.17g')
    back = pd.read_csv(DST / 'nhanes_IJ_model_input.csv', float_precision='round_trip')
    pd.testing.assert_frame_equal(back, t, check_dtype=False)
    summary = dict(rows=len(t), by_cycle=t.cycle.value_counts().to_dict(), predictors=PREDICTORS,
                   missing_in_predictors=0,
                   missing_in_extra_columns={c: int(t[c].isna().sum()) for c in t if t[c].isna().any()})
    (DST / 'export_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
