"""Independent re-check of the outputs against the raw XPT files (logic §5).

Re-reads every raw file instead of trusting clean_nhanes_ij.py's in-memory state.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]  # project root (PhD GenAI)
OUT, AUDIT = BASE / 'output', BASE / 'audit'
TOKEN = '__SOURCE_MISSING__'
RESULTS = []


def ok(name, cond):
    RESULTS.append(dict(check=name, result='PASS' if cond else 'FAIL'))
    assert cond, name


def read(path):
    return pd.read_csv(path, keep_default_na=False, na_values=[TOKEN], float_precision='round_trip', low_memory=False)


def raw(folder, name):
    df = pd.read_sas(ROOT / folder / f'{name}.XPT', format='xport')
    num = df.select_dtypes('number').columns
    df[num] = df[num].mask(df[num].abs().lt(1e-70) & df[num].ne(0), 0.0)
    df['SEQN'] = df.SEQN.astype('int64')
    return df.set_index('SEQN')


def main():
    for r in json.loads((AUDIT / 'source_manifest.json').read_text()):
        ok(f"sha256 unchanged: {r['file']}", hashlib.sha256((ROOT / r['file']).read_bytes()).hexdigest() == r['sha256'])
    o = read(OUT / 'nhanes_IJ_original_values.csv')
    d = read(OUT / 'nhanes_IJ_derived.csv')
    ok('participants I=9971, J=9254', o.cycle.value_counts().to_dict() == {'I': 9971, 'J': 9254})
    ok('SEQN unique and aligned', o.SEQN.is_unique and o.SEQN.equals(d.SEQN) and o.cycle.equals(d.cycle))

    # Original values equal raw XPT, cell by cell, for every research field.
    folders = {'I': '01_data/raw/NHANES_I', 'J': '01_data/raw/NHANES'}
    for cyc, folder in folders.items():
        sub = o[o.cycle.eq(cyc)].set_index('SEQN')
        for col in o.columns[2:]:
            t, c = col.split('__')
            if t == 'BPXO' and cyc == 'I':
                ok('BPXO absent in I', sub[col].isna().all()); continue
            r = raw(folder, f'{t}_{cyc}')[c].reindex(sub.index)
            ok(f'original == raw: {cyc} {col}', np.array_equal(sub[col].to_numpy(float), r.to_numpy(float), equal_nan=True))
    num = o.select_dtypes('number')
    ok('no residual 5.4e-79 values', not (num.abs().lt(1e-70) & num.ne(0)).any().any())

    I, J = o.cycle.eq('I'), o.cycle.eq('J')
    scr = o['BIOPRO__LBXSCR']
    ok('creatinine: J unchanged', d.creatinine_J_scale[J].equals(scr[J]))
    ok('creatinine: I = 0.9515x + 0.06608', np.allclose(d.creatinine_J_scale[I], 0.9515 * scr[I] + 0.06608, equal_nan=True))
    ok('weights halved', np.array_equal(d.wtmec_pooled.to_numpy(), (o['DEMO__WTMEC2YR'] / 2).to_numpy()))
    total = {c: o.loc[o.cycle.eq(c), 'DEMO__WTINT2YR'].sum() for c in 'IJ'}
    ok('pooled population = mean of cycle totals', abs(d.wtint_pooled.sum() - (total['I'] + total['J']) / 2) < 1)
    ok('interview-only have MEC weight exactly 0', o.loc[o['DEMO__RIDSTATR'].eq(1), 'DEMO__WTMEC2YR'].eq(0).all())

    # Skip logic: direct answers never overwritten; inferred "no" only in the defined cases.
    q20, q40, q50 = o['BPQ__BPQ020'], o['BPQ__BPQ040A'], o['BPQ__BPQ050A']
    bp = d.on_bp_meds.map({True: True, False: False, 'True': True, 'False': False})
    ok('bp: direct yes kept', bp[q50.eq(1)].eq(True).all() and d.on_bp_meds_source[q50.eq(1)].eq('direct').all())
    ok('bp: direct no kept', bp[q50.eq(2)].eq(False).all())
    sk = d.on_bp_meds_source.eq('skip_logic')
    ok('bp: skip only when BPQ050A missing and (BPQ020=2 or BPQ040A=2)',
       (q50[sk].isna() & (q20[sk].eq(2) | (q20[sk].eq(1) & q40[sk].eq(2)))).all() and bp[sk].eq(False).all())
    ok('bp: refused/don\'t know stay unknown', bp[q50.isna() & (q20.isin([7, 9]) | q40.isin([7, 9]))].isna().all())
    s20, s40 = o['SMQ__SMQ020'], o['SMQ__SMQ040']
    sm = d.current_smoker.map({True: True, False: False, 'True': True, 'False': False})
    ok('smoke: direct answers kept', sm[s40.isin([1, 2])].eq(True).all() and sm[s40.eq(3)].eq(False).all())
    sk = d.current_smoker_source.eq('skip_logic')
    ok('smoke: skip only when SMQ040 missing and SMQ020=2', (s40[sk].isna() & s20[sk].eq(2)).all() and sm[sk].eq(False).all())
    ok('diabetes borderline stays unknown', d.diabetes[o['DIQ__DIQ010'].eq(3)].isna().all())

    status = pd.read_csv(AUDIT / 'row_status.csv')
    comp = read(OUT / 'analysis/complete_derived.csv')
    inc = read(OUT / 'analysis/incomplete_derived.csv')
    pool = status.in_analysis_pool
    ok('pool = complete + incomplete', pool.sum() == len(comp) + len(inc))
    ok('complete = pool & all known', len(comp) == int((pool & status.all_predictors_known).sum()))
    ok('every excluded row has a reason', status.loc[~pool, 'first_exclusion_reason'].fillna('').ne('').all())
    pd.DataFrame(RESULTS).to_csv(AUDIT / 'verification.csv', index=False)
    print(f'{len(RESULTS)} checks PASS')


if __name__ == '__main__':
    main()
