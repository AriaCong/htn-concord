from pathlib import Path
import json,re,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]; BASE=ROOT/'01_data/nhanes_IJ'; DST=Path(__file__).parent
kw=dict(keep_default_na=False,na_values=['__SOURCE_MISSING__'],float_precision='round_trip',low_memory=False)
read=lambda p:pd.read_csv(BASE/p,**kw)
o=read('output/nhanes_IJ_original_values_all_columns.csv'); d=read('output/nhanes_IJ_derived.csv'); rx=read('output/rxq_rx_IJ_original_rows.csv'); status=read('audit/row_status.csv'); t=read('model_input/nhanes_IJ_model_input.csv')
checks=[]
def check(name,cond): checks.append(dict(check=name,passed=bool(cond)))
def tri(expected,actual):
 a=actual.map({True:1,False:0,'True':1,'False':0}); return np.array_equal(np.array(expected,float),a.to_numpy(float),equal_nan=True)
q=o['BPQ__BPQ050A']; q20=o['BPQ__BPQ020']; q40=o['BPQ__BPQ040A']; smoke=o['SMQ__SMQ040']; sm20=o['SMQ__SMQ020']
bp=np.select([q.eq(1),q.eq(2),q.isna()&(q20.eq(2)|(q20.eq(1)&q40.eq(2)))],[1,0,0],np.nan)
s=np.select([smoke.isin([1,2]),smoke.eq(3),smoke.isna()&sm20.eq(2)],[1,0,0],np.nan)
check('independent BP skips and direct answers',tri(bp,d.on_bp_meds)); check('independent smoking skips and direct answers',tri(s,d.current_smoker))
dm=np.select([o['DIQ__DIQ010'].eq(1),o['DIQ__DIQ010'].eq(2)],[1,0],np.nan); check('independent diabetes mapping',tri(dm,d.diabetes))
mc=o[[f'MCQ__MCQ160{x}' for x in 'BCDEF']]; cv=np.select([mc.eq(1).any(axis=1),mc.eq(2).all(axis=1)],[1,0],np.nan); check('independent CVD mapping',tri(cv,d.cvd_history))
statins=set('atorvastatin fluvastatin lovastatin pitavastatin pravastatin rosuvastatin simvastatin'.split()); expected={}
for seqn,g in rx.groupby('SEQN'):
 names=g.RXDDRUG.fillna('').str.lower(); known_statin=any(statins.intersection(re.findall('[a-z]+',n)) for n in names); unresolved=any((u==1 and (n.strip() in ['', '55555','77777','99999'] or 'unspecified' in n)) for u,n in zip(g.RXDUSE,names)); uses=set(g.RXDUSE.dropna())
 expected[seqn]=1 if known_statin else 0 if uses=={2} or (uses=={1} and not unresolved) else np.nan
check('independent statin mapping under stated rule',tri(d.SEQN.map(expected),d.statin))
for c in ['age_years','sex','total_chol_mgdl','hdl_mgdl','sbp_mean','egfr']:
 a=d.set_index('SEQN').loc[t.SEQN,c].reset_index(drop=True); b=t[c]
 check('model input source '+c,np.array_equal(a.to_numpy(),b.to_numpy()))
for c in ['diabetes','on_bp_meds','current_smoker','statin']:
 a=d.set_index('SEQN').loc[t.SEQN,c].map({True:1,False:0,'True':1,'False':0}).to_numpy(); check('binary model source '+c,np.array_equal(a,t[c]))
for c,source in [('wtmec_pooled','WTMEC2YR'),('wtint_pooled','WTINT2YR')]: check('weight '+c,np.array_equal(d[c],o['DEMO__'+source]/2))
flags=[]; recent=[]; missing=[]; inventory=[]
for cyc,folder in [('I','NHANES_I'),('J','NHANES')]:
 root=ROOT/'01_data/raw'/folder
 k=pd.read_sas(root/f'KIQ_U_{cyc}.XPT',format='xport'); k=k.loc[k.KIQ025.eq(1),['SEQN','KIQ022','KIQ025']]; z=k.merge(status,on='SEQN').merge(d[['SEQN','egfr']],on='SEQN'); flags.append(z)
 r=pd.read_sas(root/f'SMQRTU_{cyc}.XPT',format='xport'); z=t.merge(r[['SEQN','SMQ690A','SMQ710']],on='SEQN'); z=z[z.current_smoker.eq(0)&z.SMQ690A.eq(1)]; recent.append(z)
 for table,field in [('BIOPRO','egfr'),('TCHOL','total_chol_mgdl'),('HDL','hdl_mgdl'),('BPX','sbp_mean')]:
  raw=pd.read_sas(root/f'{table}_{cyc}.XPT',format='xport'); m=status.in_analysis_pool&d.cycle.eq(cyc)&d[field].isna(); ids=d.loc[m,'SEQN']; missing.append(dict(cycle=cyc,predictor=field,missing=len(ids),component_absent=int((~ids.isin(raw.SEQN)).sum()),component_present=int(ids.isin(raw.SEQN).sum()),interview_only=int((m&o['DEMO__RIDSTATR'].eq(1)).sum())))
for folder in ['NHANES_I','NHANES','NHANES_L_separate/data']:
 root=ROOT/'01_data/raw'/folder; fs=list(root.glob('*.XPT')); demo=next(root.glob('DEMO_*.XPT')); raw=pd.read_sas(demo,format='xport'); inventory.append(dict(folder=folder,xpt_files=len(fs),participants=len(raw),aged_30_79=int(raw.RIDAGEYR.between(30,79).sum())))
f=pd.concat(flags); r=pd.concat(recent); f.to_csv(DST/'dialysis_review.csv',index=False); r.to_csv(DST/'smoking_discordance.csv',index=False); pd.DataFrame(missing).to_csv(DST/'measurement_missingness.csv',index=False); pd.DataFrame(inventory).to_csv(DST/'local_cycle_inventory.csv',index=False)
# Potential improvements in statin identification without treating every unspecified class as a statin.
hmg=rx[rx.RXDDRUG.fillna('').str.contains('HMG-COA REDUCTASE INHIBITORS',regex=False)]; hmg.merge(status,on='SEQN').to_csv(DST/'statin_class_review.csv',index=False)
summary=dict(checks=len(checks),failed=sum(not x['passed'] for x in checks),dialysis_complete=int(f.all_predictors_known[f.in_analysis_pool].sum()),dialysis_pool=int(f.in_analysis_pool.sum()),recent_cigarettes_current_nonsmoker=len(r),recent_cigarettes_skip_logic=int(r.current_smoker_source.eq('skip_logic').sum()),statin_hmg_unresolved=len(hmg),local_cycles=inventory)
pd.DataFrame(checks).to_csv(DST/'semantic_checks.csv',index=False); (DST/'semantic_summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2)); assert summary['failed']==0
