from pathlib import Path
import sys,json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[3]; BASE=ROOT/'01_data/nhanes_IJ'; DST=Path(__file__).parent
sys.path.insert(0,str(ROOT/'00_shared'))
from pipelines.common.prevent import PreventInputs,prevent_10yr_cvd_risk
kw=dict(keep_default_na=False,na_values=['__SOURCE_MISSING__'],float_precision='round_trip',low_memory=False)
t=pd.read_csv(BASE/'model_input/nhanes_IJ_model_input.csv',**kw); o=pd.read_csv(BASE/'output/nhanes_IJ_original_values.csv',**kw).set_index('SEQN').loc[t.SEQN].reset_index(); risk=pd.read_csv(BASE/'model_input/nhanes_IJ_prevent.csv',**kw).prevent_10yr_total_cvd_pct
sm=pd.read_csv(DST/'smoking_discordance.csv'); cases=[]; summary={}
scenarios={'hba1c_positive':{'diabetes':np.maximum(t.diabetes,o['GHB__LBXGH'].ge(6.5))},'recent_cigarettes_positive':{'current_smoker':np.maximum(t.current_smoker,t.SEQN.isin(sm.SEQN))}}
bp=o[[f'BPX__BPXSY{i}' for i in range(2,5)]].copy(); alt=bp.where(bp>0).mean(axis=1).fillna(t.sbp_mean); scenarios['BP_excluding_first_if_others_available']={'sbp_mean':alt}
for label,updates in scenarios.items():
 z=t.copy()
 for c,v in updates.items(): z[c]=v
 vals=[]
 for r in z.itertuples(index=False): vals.append(prevent_10yr_cvd_risk(PreventInputs(age=r.age_years,sex=r.sex,total_chol_mgdl=r.total_chol_mgdl,hdl_mgdl=r.hdl_mgdl,sbp=r.sbp_mean,on_bp_meds=bool(r.on_bp_meds),diabetes=bool(r.diabetes),current_smoker=bool(r.current_smoker),egfr=r.egfr,statin=bool(r.statin))))
 vals=np.array(vals); changed=np.zeros(len(t),dtype=bool)
 for c in updates: changed|=z[c].to_numpy()!=t[c].to_numpy()
 summary[label]=dict(input_changed=int(changed.sum()),cross_up_7_5=int(((risk<7.5)&(vals>=7.5)).sum()),cross_down_7_5=int(((risk>=7.5)&(vals<7.5)).sum()),max_risk_change_pct_points=float(abs(vals-risk).max()))
 pd.DataFrame(dict(SEQN=t.SEQN,cycle=t.cycle,input_changed=changed,original_risk_pct=risk,scenario_risk_pct=vals)).loc[changed].to_csv(DST/(label+'.csv'),index=False)
l=ROOT/'01_data/raw/NHANES_L_separate/data'; demo=pd.read_sas(l/'DEMO_L.XPT',format='xport'); rx=pd.read_sas(l/'RXQ_RX_L.XPT',format='xport'); j=demo.merge(rx,on='SEQN'); summary['L_aged_30_79_no_prescription_medication']=int((j.RIDAGEYR.between(30,79)&j.RXQ033.eq(2)).sum())
(DST/'sensitivity_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
