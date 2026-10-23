"""Audit present data, recompute risk, and evaluate lipid-box extrema; aggregate outputs only."""
from pathlib import Path
import dataclasses
import json
import sys
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # project root (PhD GenAI)
sys.path.insert(0, str(ROOT / '00_shared'))
from pipelines.common.prevent import PreventInputs, prevent_10yr_cvd_risk

FIELDS = ['age', 'sex', 'total_chol', 'hdl', 'sbp', 'on_bp_meds', 'diabetes',
          'current_smoker', 'egfr', 'statin_use']


def inputs(row):
    return PreventInputs(age=float(row.age), sex=row.sex,
        total_chol_mgdl=float(row.total_chol), hdl_mgdl=float(row.hdl),
        sbp=float(row.sbp), on_bp_meds=bool(row.on_bp_meds),
        diabetes=bool(row.diabetes), current_smoker=bool(row.current_smoker),
        egfr=float(row.egfr), statin=bool(row.statin_use))


def main():
    nh = pd.read_csv(ROOT / '_archive/htn-concord/htn-concord/data/nhanes/processed/nhanes_profiles_J.csv')
    mcq = pd.read_sas(ROOT / '01_data/raw/NHANES/MCQ_J.XPT', format='xport')
    items = ['MCQ160B', 'MCQ160C', 'MCQ160D', 'MCQ160E', 'MCQ160F']
    mcq['cvd_known'] = mcq[items].isin([1, 2]).all(axis=1)
    mcq['cvd_positive'] = (mcq[items] == 1).any(axis=1)
    nh = nh.merge(mcq[['SEQN', 'cvd_known', 'cvd_positive']], on='SEQN', how='left', validate='one_to_one')
    out = {}
    samples = [('NHANES_J', nh)]
    for name in ['prior_only', 'prior_plus_index']:
        samples.append(('MIMIC_' + name, pd.read_csv(ROOT / f'00_shared/data/mimic/processed/mimic_profiles_primary_{name}.csv')))
    tcbox = list(map(float, nh.total_chol.quantile([.01, .99])))
    hdlbox = list(map(float, nh.hdl.quantile([.01, .99])))
    # These boxes do not overlap, so TC > HDL holds throughout the rectangle.
    assert tcbox[0] > hdlbox[1]
    for name, df in samples:
        complete = df[FIELDS].notna().all(axis=1) & df.age.between(30, 79)
        sub = df[complete].copy()
        values = [prevent_10yr_cvd_risk(inputs(r)) for r in sub.itertuples()]
        sub['recomputed'] = values
        diffs = (sub.recomputed - sub.prevent_10yr).abs().dropna()
        bounds = dict(age=(30, 79), total_chol=(130, 320), hdl=(20, 100), sbp=(90, 200), egfr=(15, 140))
        inbounds = pd.Series(True, index=sub.index)
        for key, (lo, hi) in bounds.items():
            inbounds &= sub[key].between(lo, hi)
        if name == 'NHANES_J':
            no_cvd = sub.cvd_known.fillna(False) & ~sub.cvd_positive.fillna(True)
        else:
            no_cvd = sub.clinical_cvd.notna() & sub.clinical_cvd.eq(False)
        strict = sub[inbounds & no_cvd]
        result = dict(rows=len(df), complete_age_30_79=len(sub), stored_risk_nonmissing=int(df.prevent_10yr.notna().sum()),
            missing_inputs={k:int(df[k].isna().sum()) for k in FIELDS},
            max_abs_recompute_difference_pp=float(diffs.max()) if len(diffs) else None,
            complete_with_numeric_bounds=int(inbounds.sum()),
            complete_bounds_and_recorded_no_cvd=len(strict),
            numeric_bounds_used=bounds,
            note='Bounds are conservative calculator-style audit filters; not a full clinical eligibility determination')
        # At fixed age, sex, treatment and other inputs, the implemented linear
        # predictor is affine in TC and HDL. The logistic link is increasing.
        # Thus all extrema on this rectangle occur at its four corners.
        groups = {}
        for label, pool in [('complete_pool', sub), ('bounds_no_cvd_pool', strict)]:
            counts = {'above':0, 'below':0, 'undetermined':0}
            outside = 0
            for r in pool.itertuples():
                inp = inputs(r)
                corner = [prevent_10yr_cvd_risk(dataclasses.replace(inp, total_chol_mgdl=t, hdl_mgdl=h))
                          for t in tcbox for h in hdlbox]
                lo, hi = min(corner), max(corner)
                counts['above' if lo >= 7.5 else 'below' if hi < 7.5 else 'undetermined'] += 1
                outside += not (tcbox[0] <= r.total_chol <= tcbox[1] and hdlbox[0] <= r.hdl <= hdlbox[1])
            groups[label] = dict(n=len(pool), labels=counts, observed_lipids_outside_box=int(outside))
        result['lipid_box_determinability'] = groups
        # A second, explicitly defined audit domain matches the numeric lipid
        # filters above rather than the old empirical percentile box.
        counts = {'above': 0, 'below': 0, 'undetermined': 0}
        for r in strict.itertuples():
            inp = inputs(r)
            risks = [prevent_10yr_cvd_risk(dataclasses.replace(inp, total_chol_mgdl=t, hdl_mgdl=h))
                     for t in (130.0, 320.0) for h in (20.0, 100.0)]
            lo, hi = min(risks), max(risks)
            counts['above' if lo >= 7.5 else 'below' if hi < 7.5 else 'undetermined'] += 1
        result['explicit_lipid_domain_labels'] = dict(total_chol=[130,320], hdl=[20,100],
            threshold=7.5, n=len(strict), labels=counts)
        out[name] = result
    sample = dict(age=50, total_chol_mgdl=200, hdl_mgdl=45, sbp=160, on_bp_meds=True,
                  diabetes=True, current_smoker=False, egfr=90, statin=False)
    examples = {s: prevent_10yr_cvd_risk(PreventInputs(sex=s, **sample)) for s in ['female','male']}
    assert abs(examples['female'] - 14.683939) < 1e-4
    assert abs(examples['male'] - 16.317056) < 1e-4
    out['published_example_checks'] = examples
    out['lipid_domain'] = dict(total_chol=tcbox, hdl=hdlbox,
        extrema_method='Exact four-corner evaluation for fixed other inputs and the implemented affine lipid predictor; ordinary floating-point tolerance applies',
        restriction='Empirical domain, not guaranteed coverage of all clinically possible missing values')
    (HERE / 'calculability-audit.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
