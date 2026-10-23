"""Synthetic examples using the existing local PREVENT base total-CVD implementation.

Run with Python 3.10 or newer. No third-party packages are required.
These are risk-threshold demonstrations, not clinical treatment recommendations.
"""
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / '00_shared'))
from pipelines.common.prevent import (
    COEFFICIENTS, FEATURE_ORDER, PreventInputs, _features, prevent_10yr_cvd_risk,
)


def lipid_range(inp):
    """Exact extrema for this fixed-input affine lipid predictor on this rectangle."""
    corners = []
    for tc in (130, 320):
        for hdl in (20, 100):
            risk = prevent_10yr_cvd_risk(replace(inp, total_chol_mgdl=tc, hdl_mgdl=hdl))
            if risk is None:
                raise ValueError('Example has incomplete or unsupported inputs')
            corners.append(dict(total_chol_mgdl=tc, hdl_mgdl=hdl, risk_percent=risk))
    lo = min(c['risk_percent'] for c in corners)
    hi = max(c['risk_percent'] for c in corners)
    label = 'ABOVE' if lo >= 7.5 else 'BELOW' if hi < 7.5 else 'UNDETERMINED'
    return dict(domain=dict(total_chol_mgdl=[130, 320], hdl_mgdl=[20, 100]),
                corners=corners, minimum_percent=lo, maximum_percent=hi,
                threshold_percent=7.5, label=label)


def main():
    examples = []
    for name, age, sex, sbp, egfr, smoker in [
        ('A', 40, 'female', 120, 100, False),
        ('B', 55, 'male', 135, 85, False),
        ('C', 70, 'male', 135, 65, True),
    ]:
        inp = PreventInputs(age=age, sex=sex, total_chol_mgdl=200,
            hdl_mgdl=50, sbp=sbp, on_bp_meds=False, diabetes=False,
            current_smoker=smoker, egfr=egfr, statin=False)
        examples.append(dict(name=name, synthetic=True, inputs=asdict(inp),
            complete_risk_percent=prevent_10yr_cvd_risk(inp),
            when_lipids_hidden=lipid_range(inp)))
    worked = PreventInputs(age=50, sex='female', total_chol_mgdl=200,
        hdl_mgdl=45, sbp=160, on_bp_meds=True, diabetes=True,
        current_smoker=False, egfr=90, statin=False)
    features = _features(worked)
    coefficients = COEFFICIENTS[worked.sex]
    terms = {key: features[key] * coefficients[key] for key in FEATURE_ORDER}
    output = dict(model='Existing local PREVENT base 10-year total-CVD implementation',
        examples=examples,
        worked_example=dict(inputs=asdict(worked), transformed_features=features,
            weighted_terms=terms, intercept=coefficients['intercept'],
            linear_predictor=coefficients['intercept'] + sum(terms.values()),
            risk_percent=prevent_10yr_cvd_risk(worked)))
    (HERE / 'calculation-examples.json').write_text(json.dumps(output, indent=2))
    for ex in examples:
        interval = ex['when_lipids_hidden']
        print(f"{ex['name']}: complete={ex['complete_risk_percent']:.6f}%; "
              f"hidden lipids=[{interval['minimum_percent']:.6f}%, "
              f"{interval['maximum_percent']:.6f}%]; {interval['label']}")
    print(f"Worked example: L={output['worked_example']['linear_predictor']:.9f}; "
          f"risk={output['worked_example']['risk_percent']:.6f}%")


if __name__ == '__main__':
    main()
