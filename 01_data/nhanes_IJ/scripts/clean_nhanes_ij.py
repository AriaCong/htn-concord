"""Clean NHANES cycles I (2015-2016) and J (2017-2018) per ../CLEANING_LOGIC.md.

Three layers that never overwrite each other:
  output/nhanes_IJ_original_values.csv   source values (XPORT zero decoding restored only)
  output/nhanes_IJ_derived.csv           calibration, means, weights, skip-logic answers
  output/analysis/{complete,incomplete}_*.csv  filtered analysis sets
Raw files are read-only; every check below raises on failure.
"""
from pathlib import Path
import hashlib
import json
import platform

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]  # project root (PhD GenAI)
RAW = {'I': ROOT / '01_data/raw/NHANES_I', 'J': ROOT / '01_data/raw/NHANES'}
OUT = BASE / 'output'
AUDIT = BASE / 'audit'
TOKEN = '__SOURCE_MISSING__'
CYCLES = ['I', 'J']

# One-row-per-person tables (logic §2). BPXO was fielded only in J.
TABLES = ['DEMO','BPX','BPXO','BIOPRO','TCHOL','HDL','GHB','ALB_CR','BMX','BPQ','DIQ','SMQ','MCQ']
FIELDED = {'BPXO': {'J'}}
RESEARCH = {
    'DEMO': ['RIDSTATR','RIDAGEYR','RIAGENDR','RIDRETH3','RIDEXPRG','WTINT2YR','WTMEC2YR','SDMVPSU','SDMVSTRA'],
    'BPX': [f'BPXSY{i}' for i in range(1,5)]+[f'BPXDI{i}' for i in range(1,5)],
    'BPXO': [f'BPXOSY{i}' for i in range(1,4)]+[f'BPXODI{i}' for i in range(1,4)],
    'BIOPRO': ['LBXSCR','LBXSKSI'], 'TCHOL': ['LBXTC'], 'HDL': ['LBDHDD'], 'GHB': ['LBXGH'],
    'ALB_CR': ['URDACT'], 'BMX': ['BMXBMI'],
    'BPQ': ['BPQ020','BPQ030','BPQ040A','BPQ050A'],
    'DIQ': ['DIQ010','DIQ050','DIQ070'],
    'SMQ': ['SMQ020','SMQ040'],
    'MCQ': ['MCQ160B','MCQ160C','MCQ160D','MCQ160E','MCQ160F'],
}
SCR_I_TO_J = (0.9515, 0.06608)  # CDC BIOPRO_J analytic notes, non-weighted Deming
STATINS = {'atorvastatin','fluvastatin','lovastatin','pitavastatin','pravastatin','rosuvastatin','simvastatin'}
PREDICTORS = ['age_years','sex','total_chol_mgdl','hdl_mgdl','sbp_mean','egfr',
              'diabetes','on_bp_meds','current_smoker','statin']

MANIFEST, ZERO, CHECKS, FLOW, METHODS = [], [], [], [], []


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def check(name, ok, **detail):
    CHECKS.append(dict(check=name, result='PASS' if ok else 'FAIL', **detail))
    assert ok, (name, detail)


def method(field, inputs, rule, unknown_when):
    METHODS.append(dict(field=field, inputs=inputs, rule=rule, unknown_when=unknown_when))


# ---------- §1 reading ----------

def read_xpt(cycle, name):
    path = RAW[cycle] / f'{name}.XPT'
    MANIFEST.append(dict(cycle=cycle, file=str(path.relative_to(ROOT)), sha256=sha(path), bytes=path.stat().st_size))
    df = pd.read_sas(path, format='xport', encoding='utf-8')
    # pandas decodes a SAS XPORT 0 as 5.397605346934028e-79; restore the source 0.
    for c in df.select_dtypes('number'):
        tiny = df[c].abs().lt(1e-70) & df[c].ne(0)
        if tiny.any():
            df.loc[tiny, c] = 0.0
            ZERO.append(dict(cycle=cycle, table=name, column=c, cells_restored_to_zero=int(tiny.sum())))
    if 'SEQN' in df: df['SEQN'] = df.SEQN.astype('int64')  # RXQ_DRUG is keyed by RXDDRGID
    return df


def write_csv(df, path):
    """Write with an explicit NA token and prove the round trip is lossless."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for c in df.select_dtypes(include=['object', 'string']):
        assert not df[c].eq(TOKEN).any()
    df.to_csv(path, index=False, na_rep=TOKEN, float_format='%.17g')
    back = read_csv(path)
    ok = list(back.columns) == list(df.columns) and len(back) == len(df) and \
        np.array_equal(back.isna().to_numpy(), df.isna().to_numpy())
    for c in df:
        if not ok: break
        a, b = df[c], back[c]
        if pd.api.types.is_bool_dtype(a) or str(a.dtype) == 'boolean' or a.dtype == object:
            ok = a.dropna().astype(str).str.lower().reset_index(drop=True).equals(
                 b.dropna().astype(str).str.lower().reset_index(drop=True))
        else:
            ok = np.array_equal(a.to_numpy(float, na_value=np.nan), pd.to_numeric(b).to_numpy(float, na_value=np.nan), equal_nan=True)
    check('csv_round_trip_lossless', ok, file=str(path.relative_to(BASE)), rows=len(df), columns=df.shape[1])


def read_csv(path):
    return pd.read_csv(path, keep_default_na=False, na_values=[TOKEN], float_precision='round_trip', low_memory=False)


# ---------- §2 structure and merge ----------

def build_cycle(cycle):
    frames = {t: read_xpt(cycle, f'{t}_{cycle}') for t in TABLES if cycle in FIELDED.get(t, set(CYCLES))}
    for t, df in frames.items():
        check('seqn_unique_in_table', df.SEQN.is_unique, cycle=cycle, table=t)
    demo_ids = set(frames['DEMO'].SEQN)
    master = frames['DEMO'].add_prefix('DEMO__').rename(columns={'DEMO__SEQN': 'SEQN'})
    presence = pd.DataFrame({'SEQN': master.SEQN})
    for t, df in frames.items():
        presence[t] = presence.SEQN.isin(df.SEQN)
        if t == 'DEMO': continue
        check('table_seqn_subset_of_demo', set(df.SEQN) <= demo_ids, cycle=cycle, table=t)
        before = master.copy()
        master = master.merge(df.add_prefix(t + '__').rename(columns={t + '__SEQN': 'SEQN'}),
                              on='SEQN', how='left', validate='one_to_one')
        unchanged = master[before.columns].equals(before)
        check('left_join_preserves_rows_and_values', len(master) == len(before) and unchanged, cycle=cycle, table=t)
        FLOW.append(dict(stage='merge', cycle=cycle, table=t, rows=len(master), matched=int(presence[t].sum())))
    for t in TABLES:
        if t not in frames: presence[t] = pd.NA  # component not fielded in this cycle
    master.insert(1, 'cycle', cycle); presence.insert(1, 'cycle', cycle)
    rx = read_xpt(cycle, f'RXQ_RX_{cycle}')
    check('rx_seqn_subset_of_demo', set(rx.SEQN) <= demo_ids, cycle=cycle)
    rx.insert(1, 'cycle', cycle)
    return master, presence, rx


def stack():
    parts = {c: build_cycle(c) for c in CYCLES}
    ids = {c: set(p[0].SEQN) for c, p in parts.items()}
    check('seqn_disjoint_across_cycles', not ids['I'] & ids['J'])
    strata = {c: set(p[0]['DEMO__SDMVSTRA']) for c, p in parts.items()}
    check('variance_strata_disjoint_across_cycles', not strata['I'] & strata['J'])
    data = pd.concat([parts[c][0] for c in CYCLES], ignore_index=True, sort=False)
    for c in CYCLES:
        m = parts[c][0]
        same = data.loc[data.cycle.eq(c), list(m.columns)].reset_index(drop=True).equals(m.reset_index(drop=True))
        extra = data.loc[data.cycle.eq(c), [x for x in data if x not in m]].isna().all().all()
        check('stack_preserves_cycle_values', same and extra, cycle=c)
    presence = pd.concat([parts[c][1] for c in CYCLES], ignore_index=True)
    rx = pd.concat([parts[c][2] for c in CYCLES], ignore_index=True)
    drug = read_xpt('J', 'RXQ_DRUG')
    return data, presence, rx, drug


# ---------- §3 derived fields ----------

def tri(series_true, series_false, index):
    out = pd.Series(pd.NA, index=index, dtype='boolean')
    out[series_false.fillna(False)] = False
    out[series_true.fillna(False)] = True
    return out


def derive(d, rx):
    v = lambda t, c: d[f'{t}__{c}']
    out = pd.DataFrame({'SEQN': d.SEQN, 'cycle': d.cycle})
    out['age_years'] = v('DEMO', 'RIDAGEYR')
    out['sex'] = v('DEMO', 'RIAGENDR').map({1: 'male', 2: 'female'})
    method('sex', 'RIAGENDR', '1 male, 2 female', 'other codes')

    # §3.1 measurements
    sy = pd.concat([v('BPX', f'BPXSY{i}').where(v('BPX', f'BPXSY{i}').gt(0)) for i in range(1, 5)], axis=1)
    dy = pd.concat([v('BPX', f'BPXDI{i}').where(v('BPX', f'BPXDI{i}').gt(0)) for i in range(1, 5)], axis=1)
    out['sbp_mean'] = sy.mean(axis=1)
    out['sbp_readings'] = sy.notna().sum(axis=1)
    out['dbp_mean'] = dy.mean(axis=1)
    out['dbp_zero_readings'] = pd.concat([v('BPX', f'BPXDI{i}').eq(0) for i in range(1, 5)], axis=1).sum(axis=1)
    method('sbp_mean', 'BPXSY1-4 (auscultatory, both cycles)', 'mean of readings > 0; no rounding; reading 1 kept', 'no reading > 0')
    method('dbp_mean', 'BPXDI1-4', 'mean of readings > 0; recorded 0 kept in source, excluded from mean, counted in dbp_zero_readings', 'no reading > 0')
    so = pd.concat([v('BPXO', f'BPXOSY{i}').where(v('BPXO', f'BPXOSY{i}').gt(0)) for i in range(1, 4)], axis=1)
    out['sbp_mean_oscillometric_J_only'] = so.mean(axis=1)
    method('sbp_mean_oscillometric_J_only', 'BPXOSY1-3', 'J-only sensitivity measure, same rule', 'cycle I (not fielded)')
    scr = v('BIOPRO', 'LBXSCR')
    a, b = SCR_I_TO_J
    out['creatinine_J_scale'] = scr.where(d.cycle.eq('J'), a * scr + b)
    method('creatinine_J_scale', 'LBXSCR, cycle', f'J unchanged; I = {a} * LBXSCR + {b} (mg/dL)', 'LBXSCR missing')
    s, age = out.creatinine_J_scale, out.age_years
    fem = out.sex.eq('female')
    k = np.where(fem, .7, .9); al = np.where(fem, -.241, -.302)
    egfr = 142 * np.minimum(s / k, 1) ** al * np.maximum(s / k, 1) ** -1.2 * .9938 ** age * np.where(fem, 1.012, 1)
    out['egfr'] = pd.Series(egfr, index=d.index).where(s.gt(0) & age.between(18, 79) & out.sex.notna())
    method('egfr', 'creatinine_J_scale, age, sex', 'CKD-EPI 2021 creatinine (race-free), no rounding', 'creatinine missing/<=0, age <18 or 80 (top-code), sex missing')
    out['total_chol_mgdl'] = v('TCHOL', 'LBXTC')
    out['hdl_mgdl'] = v('HDL', 'LBDHDD')
    out['non_hdl_mgdl'] = out.total_chol_mgdl - out.hdl_mgdl
    method('non_hdl_mgdl', 'LBXTC, LBDHDD', 'TC - HDL', 'either missing')
    out['wtint_pooled'] = v('DEMO', 'WTINT2YR') / 2
    out['wtmec_pooled'] = v('DEMO', 'WTMEC2YR') / 2
    method('wtint_pooled, wtmec_pooled', 'WTINT2YR, WTMEC2YR', '2-year weight / 2 for the pooled 4-year analysis', 'never (0 stays 0)')

    # §3.2 questionnaire: direct answer first, then skip logic
    q20, q40, q50 = v('BPQ', 'BPQ020'), v('BPQ', 'BPQ040A'), v('BPQ', 'BPQ050A')
    direct = q50.isin([1, 2])
    skip_no = ~direct & (q20.eq(2) | (q20.eq(1) & q40.eq(2)))
    out['on_bp_meds'] = tri(q50.eq(1), q50.eq(2) | skip_no, d.index)
    out['on_bp_meds_source'] = np.select([direct, skip_no], ['direct', 'skip_logic'], 'unknown')
    method('on_bp_meds', 'BPQ050A, BPQ020, BPQ040A',
           'BPQ050A 1 yes / 2 no; else BPQ020=2 -> no (skip to BPQ080); else BPQ020=1 & BPQ040A=2 -> no (skip to BPQ080)',
           'BPQ020 or BPQ040A refused/don\'t know, or no BPQ record')
    s20, s40 = v('SMQ', 'SMQ020'), v('SMQ', 'SMQ040')
    direct = s40.isin([1, 2, 3])
    skip_no = ~direct & s20.eq(2)
    out['current_smoker'] = tri(s40.isin([1, 2]), s40.eq(3) | skip_no, d.index)
    out['current_smoker_source'] = np.select([direct, skip_no], ['direct', 'skip_logic'], 'unknown')
    method('current_smoker', 'SMQ040, SMQ020',
           'SMQ040 1/2 yes, 3 no; else SMQ020=2 -> no (skip past SMQ040)',
           'SMQ020 refused/don\'t know, or no SMQ record')

    # §3.3 other questionnaire and drug evidence (unchanged rules)
    d10 = v('DIQ', 'DIQ010')
    out['diabetes'] = tri(d10.eq(1), d10.eq(2), d.index)
    out['diabetes_borderline'] = d10.eq(3)
    out['hba1c_ge_6_5'] = tri(v('GHB', 'LBXGH').ge(6.5), v('GHB', 'LBXGH').lt(6.5), d.index)
    method('diabetes', 'DIQ010', '1 yes, 2 no; borderline (3) NOT recoded as no', '3, 7, 9 or missing')
    method('hba1c_ge_6_5', 'LBXGH', 'separate lab screening evidence, not merged into diabetes', 'LBXGH missing')
    mcq = pd.concat([v('MCQ', c) for c in RESEARCH['MCQ']], axis=1)
    out['cvd_history'] = tri(mcq.eq(1).any(axis=1), mcq.eq(2).all(axis=1), d.index)
    method('cvd_history', 'MCQ160B-F', 'any 1 -> yes; all five 2 -> no', 'otherwise')
    names = rx.RXDDRUG.fillna('').str.lower().str.strip()
    rx = rx.assign(_statin=names.str.findall(r'[a-z]+').apply(lambda w: bool(set(w) & STATINS)),
                   _unresolved=rx.RXDUSE.eq(1) & (names.isin(['', '55555', '77777', '99999']) | names.str.contains('unspecified')))
    rows = []
    for seqn, g in rx.groupby('SEQN'):
        use = set(g.RXDUSE.dropna())
        if g._statin.any(): val, why = True, 'named statin'
        elif use == {2}: val, why = False, 'no prescription medicine in past 30 days'
        elif use == {1} and not g._unresolved.any(): val, why = False, 'all drug names resolved, none a statin'
        else: val, why = pd.NA, 'unresolved drug name or prescription status'
        rows.append((seqn, val, why))
    st = pd.DataFrame(rows, columns=['SEQN', 'statin', 'statin_reason'])
    out = out.merge(st, on='SEQN', how='left', validate='one_to_one')
    out['statin'] = out.statin.astype('boolean')
    out['statin_reason'] = out.statin_reason.fillna('no RXQ_RX record')
    method('statin', 'RXDUSE, RXDDRUG', 'ingredient-word match to 7 statins; RXDUSE=2 -> no; all names resolved without statin -> no', 'unresolved name or status')
    return out


# ---------- §4 analysis set ----------

def select(d, x):
    keep = pd.Series(True, index=x.index)
    reason = pd.Series('', index=x.index)
    steps = [('age_30_79', x.age_years.between(30, 79)),
             ('no_cvd_history', x.cvd_history.eq(False).fillna(False)),
             ('tc_in_130_320_or_missing', x.total_chol_mgdl.isna() | x.total_chol_mgdl.between(130, 320)),
             ('hdl_in_20_100_or_missing', x.hdl_mgdl.isna() | x.hdl_mgdl.between(20, 100)),
             ('sbp_in_90_200_or_missing', x.sbp_mean.isna() | x.sbp_mean.between(90, 200)),
             ('egfr_in_15_150_or_missing', x.egfr.isna() | x.egfr.between(15, 150)),
             ('not_recorded_pregnant', ~d['DEMO__RIDEXPRG'].eq(1))]
    for name, cond in steps:
        out = keep & ~cond.astype(bool)
        reason[out] = name
        for c in CYCLES + ['IJ']:
            m = x.cycle.eq(c) if c != 'IJ' else pd.Series(True, index=x.index)
            FLOW.append(dict(stage='selection', cycle=c, step=name, before=int((keep & m).sum()),
                             excluded=int((out & m).sum()), remaining=int((keep & ~out & m).sum())))
        keep &= cond.astype(bool)
    complete = x[PREDICTORS].notna().all(axis=1)
    status = pd.DataFrame({'SEQN': x.SEQN, 'cycle': x.cycle, 'in_analysis_pool': keep,
                           'first_exclusion_reason': reason.where(~keep, ''),
                           'all_predictors_known': complete,
                           'unknown_predictors': x[PREDICTORS].isna().apply(lambda r: ';'.join(r.index[r]), axis=1)})
    return keep, complete, status


def main():
    for p in [OUT, AUDIT]: p.mkdir(parents=True, exist_ok=True)
    data, presence, rx, drug = stack()
    research = data[['SEQN', 'cycle'] + [f'{t}__{c}' for t, cs in RESEARCH.items() for c in cs]]
    write_csv(data, OUT / 'nhanes_IJ_original_values_all_columns.csv')
    write_csv(research, OUT / 'nhanes_IJ_original_values.csv')
    write_csv(rx, OUT / 'rxq_rx_IJ_original_rows.csv')
    write_csv(drug, OUT / 'rxq_drug_original_rows.csv')
    derived = derive(data, rx)
    check('derived_aligned_with_original', derived.SEQN.equals(data.SEQN))
    write_csv(derived, OUT / 'nhanes_IJ_derived.csv')

    # missing-reason counts for research fields (§2)
    miss = []
    for col in research.columns[2:]:
        t = col.split('__')[0]
        for c in CYCLES:
            m = research.cycle.eq(c)
            na = research.loc[m, col].isna()
            pres = presence.loc[presence.cycle.eq(c), t].reset_index(drop=True)
            na = na.reset_index(drop=True)
            if pres.isna().all():
                miss.append(dict(cycle=c, field=col, reason='component_not_fielded_in_cycle', count=int(na.sum())))
                continue
            pres = pres.astype(bool)
            miss.append(dict(cycle=c, field=col, reason='participant_absent_from_component', count=int((na & ~pres).sum())))
            miss.append(dict(cycle=c, field=col, reason='in_component_cell_missing_skip_or_nonresponse', count=int((na & pres).sum())))
    pd.DataFrame(miss).to_csv(AUDIT / 'missing_reason_counts.csv', index=False)

    x = derived
    keep, complete, status = select(data, x)
    status.to_csv(AUDIT / 'row_status.csv', index=False)
    for name, mask in [('complete', keep & complete), ('incomplete', keep & ~complete)]:
        write_csv(research[mask].reset_index(drop=True), OUT / f'analysis/{name}_original_values.csv')
        write_csv(derived[mask].reset_index(drop=True), OUT / f'analysis/{name}_derived.csv')
    check('complete_has_no_unknown_predictor', x.loc[keep & complete, PREDICTORS].notna().all().all())

    pd.DataFrame(FLOW).to_csv(AUDIT / 'flow.csv', index=False)
    pd.DataFrame(ZERO).to_csv(AUDIT / 'xport_zero_decoding.csv', index=False)
    pd.DataFrame(METHODS).to_csv(AUDIT / 'derived_field_methods.csv', index=False)
    for r in MANIFEST: check('raw_file_unchanged_after_run', sha(ROOT / r['file']) == r['sha256'], file=r['file'])
    (AUDIT / 'source_manifest.json').write_text(json.dumps(MANIFEST, indent=2))
    pd.DataFrame(CHECKS).to_csv(AUDIT / 'checks.csv', index=False)
    by = lambda m: x.loc[m, 'cycle'].value_counts().reindex(CYCLES, fill_value=0).to_dict()
    src = {f: x.loc[keep & complete, f + '_source'].value_counts().to_dict() for f in ['on_bp_meds', 'current_smoker']}
    summary = dict(date='2026-10-20', python=platform.python_version(), pandas=pd.__version__,
                   participants=by(pd.Series(True, index=x.index)), analysis_pool=by(keep),
                   complete=by(keep & complete), incomplete=by(keep & ~complete),
                   complete_answer_source=src,
                   xport_zero_cells_restored=int(sum(r['cells_restored_to_zero'] for r in ZERO)),
                   checks_passed=len(CHECKS), source_values_changed=0, missing_values_imputed=0, rows_deleted=0)
    (AUDIT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
