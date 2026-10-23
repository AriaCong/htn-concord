from pathlib import Path
import sys,json,hashlib,struct,math
import numpy as np
import pandas as pd
import openpyxl
ROOT=Path(__file__).resolve().parents[3]; BASE=ROOT/'01_data/nhanes_IJ'; DST=Path(__file__).parent
sys.path.insert(0,str(BASE/'scripts'))
import compute_prevent
TOKEN='__SOURCE_MISSING__'
def read(p): return pd.read_csv(p,keep_default_na=False,na_values=[TOKEN],float_precision='round_trip',low_memory=False)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def check(n,c,**details):
 checks.append(dict(check=n,passed=bool(c),**details))
# Decode IBM hexadecimal floating point directly from file bytes, without pandas numeric decoding.
def binary_xpt(p):
 b=p.read_bytes(); width=int(b[240:320][-5:-2]); count=int(b[560:640][54:58]); fields=[]
 for i in range(count):
  f=struct.unpack('>hhhh8s40s8shhh2s8shhl52s',b[640+i*width:640+(i+1)*width].ljust(140,b' '))
  fields.append((f[4].decode().strip(),f[0],f[2],f[14]))
 start=640+math.ceil(width*count/80)*80+80; reclen=sum(f[2] for f in fields); payload=b[start:]; n=len(payload)//reclen
 while n and payload[(n-1)*reclen:n*reclen].strip(b' ')==b'': n-=1
 data={}; tiny=0; special={}
 for name,typ,size,pos in fields:
  values=[]
  for i in range(n):
   v=payload[i*reclen+pos:i*reclen+pos+size]
   if typ==2: values.append(v.decode('utf-8').rstrip(' ')); continue
   v=v.ljust(8,b'\0')
   if v[0] in b'._ABCDEFGHIJKLMNOPQRSTUVWXYZ' and not any(v[1:]):
    special[chr(v[0])]=special.get(chr(v[0]),0)+1; values.append(float('nan')); continue
   mant=int.from_bytes(v[1:],'big'); value=(-1 if v[0]&128 else 1)*mant*2.0**(4*((v[0]&127)-64)-56)
   if value!=0 and abs(value)<1e-70: tiny+=1
   values.append(value)
  data[name]=values
 return pd.DataFrame(data),tiny,special
allorig=read(BASE/'output/nhanes_IJ_original_values_all_columns.csv'); orig=read(BASE/'output/nhanes_IJ_original_values.csv'); d=read(BASE/'output/nhanes_IJ_derived.csv'); rx=read(BASE/'output/rxq_rx_IJ_original_rows.csv')
manifest=[]; binary=[]; rawframes={}
for cyc,folder in [('I','NHANES_I'),('J','NHANES')]:
 folder=ROOT/'01_data/raw'/folder
 for line in (folder/'SHA256SUMS.txt').read_text().splitlines():
  if not line.strip(): continue
  digest,name=line.split(maxsplit=1); p=folder/name.lstrip('*')
  manifest.append(dict(file=str(p.relative_to(ROOT)),exists=p.exists(),match=p.exists() and sha(p)==digest))
 for p in sorted(folder.glob('*.XPT')):
  f,tiny,special=binary_xpt(p); rawframes[(cyc,p.stem)]=f
  binary.append(dict(cycle=cyc,file=p.name,rows=len(f),columns=len(f.columns),real_nonzero_tiny=tiny,special_missing_codes=json.dumps(special)))
  pf=pd.read_sas(p,format='xport',encoding='utf-8')
  check('binary row count '+cyc+' '+p.stem,len(f)==len(pf))
  for c in f:
   if pd.api.types.is_numeric_dtype(f[c]):
    vals=pf[c].mask(pf[c].abs().lt(1e-70)&pf[c].ne(0),0)
    check('binary vs pandas '+cyc+' '+p.stem+' '+c,np.array_equal(f[c],vals,equal_nan=True))
  table=p.stem.removesuffix('_'+cyc)
  if table in ['RXQ_RX','RXQ_DRUG']:
   out=rx.loc[rx.cycle.eq(cyc),f.columns].reset_index(drop=True) if table=='RXQ_RX' else read(BASE/'output/rxq_drug_original_rows.csv')
  elif any(x.startswith(table+'__') for x in allorig):
   out=allorig[allorig.cycle.eq(cyc)].set_index('SEQN')
   f=f.set_index('SEQN').reindex(out.index)
   out=out[[table+'__'+c for c in f]].rename(columns=lambda c:c.split('__',1)[1])
  else: continue
  check('export shape '+cyc+' '+p.stem,f.shape==out.shape)
  for c in f:
   a=f[c].reset_index(drop=True); z=out[c].reset_index(drop=True)
   same=np.array_equal(a,z,equal_nan=True) if pd.api.types.is_numeric_dtype(a) else a.fillna('').eq(z.fillna('')).all()
   check('binary vs export '+cyc+' '+p.stem+' '+c,same)
pd.DataFrame(manifest).to_csv(DST/'source_hash_checks.csv',index=False); check('all original SHA256SUMS match',all(x['match'] for x in manifest))
pd.DataFrame(binary).to_csv(DST/'binary_xpt_inventory.csv',index=False)
# Independently reconstruct measurements and selection, without importing cleaning functions.
sy=orig[[f'BPX__BPXSY{i}' for i in range(1,5)]]; dy=orig[[f'BPX__BPXDI{i}' for i in range(1,5)]]
check('SBP recomputation',np.allclose(sy.where(sy>0).mean(axis=1),d.sbp_mean,equal_nan=True))
scr=orig['BIOPRO__LBXSCR'].to_numpy().copy(); scr[orig.cycle.eq('I')]=scr[orig.cycle.eq('I')]*.9515+.06608
age=orig['DEMO__RIDAGEYR']; female=orig['DEMO__RIAGENDR'].eq(2); ratio=scr/np.where(female,.7,.9)
egfr=142*np.where(ratio<=1,ratio**np.where(female,-.241,-.302),ratio**-1.2)*.9938**age*np.where(female,1.012,1)
egfr=egfr.where(age.between(18,79)&(scr>0))
check('independent eGFR recomputation',np.allclose(egfr,d.egfr,equal_nan=True,rtol=1e-14))
mcq=orig[[f'MCQ__MCQ160{x}' for x in 'BCDEF']]; eligible=age.between(30,79)&mcq.eq(2).all(axis=1)&orig['DEMO__RIDEXPRG'].ne(1)
prebounds=eligible.copy()
for col,lo,hi in [('total_chol_mgdl',130,320),('hdl_mgdl',20,100),('sbp_mean',90,200),('egfr',15,150)]: eligible &= d[col].isna()|d[col].between(lo,hi)
pred=['age_years','sex','total_chol_mgdl','hdl_mgdl','sbp_mean','egfr','diabetes','on_bp_meds','current_smoker','statin']; complete=d[pred].notna().all(axis=1); pool=read(BASE/'audit/row_status.csv')
check('independent pool membership',np.array_equal(eligible,pool.in_analysis_pool))
t=read(BASE/'model_input/nhanes_IJ_model_input.csv'); risk=read(BASE/'model_input/nhanes_IJ_prevent.csv')
check('complete ids exactly match',np.array_equal(d.loc[eligible&complete,'SEQN'],t.SEQN))
check('risk ids exactly match',t.SEQN.equals(risk.SEQN) and t.cycle.equals(risk.cycle))
coeff_checks,example=compute_prevent.verify_coefficients()
# Features reconstructed as a separate matrix, coefficients read from original workbook.
w=list(openpyxl.load_workbook(compute_prevent.SUPPLEMENT,data_only=True)['Table S12A Base 10yr'].values)
start=next(i for i,r in enumerate(w) if r[0] and str(r[0]).startswith('Table. Beta coefficients'))
co={str(r[0]).strip():(r[2],r[3]) for r in w[start:] if r[0] and str(r[0]).strip() in compute_prevent.S12A_ROWS}
a=(t.age_years-55)/10; n=(t.total_chol_mgdl-t.hdl_mgdl)*.02586-3.5; h=(t.hdl_mgdl*.02586-1.3)/.3; slo=(np.minimum(t.sbp_mean,110)-110)/20; shi=(np.maximum(t.sbp_mean,110)-130)/20; elo=(60-np.minimum(t.egfr,60))/15; ehi=(90-np.maximum(t.egfr,60))/15
features=[a,n,h,slo,shi,t.diabetes,t.current_smoker,elo,ehi,t.on_bp_meds,t.statin,shi*t.on_bp_meds,n*t.statin,a*n,a*h,a*shi,a*t.diabetes,a*t.current_smoker,a*elo,np.ones(len(t))]
betas=np.array([co[label] for label in compute_prevent.S12A_ROWS]); selected=betas[:,t.sex.eq('male').astype(int)].T
F=np.column_stack(features)
def calc(F): return 100/(1+np.exp(-(F*selected).sum(axis=1)))
pct=calc(F); delta=abs(pct-risk.prevent_10yr_total_cvd_pct)
check('all participant PREVENT independent calculation',delta.max()<1e-11,max_abs_pct_points=float(delta.max()))
check('threshold flags',np.array_equal(pct>=7.5,risk.prevent_ge_7_5.astype(bool)))
# Quantify choices; these are sensitivity analyses, not changes to existing outputs.
Hb=orig['GHB__LBXGH']; dmno=orig['DIQ__DIQ010'].eq(2); insulin=orig['DIQ__DIQ050'].eq(1); pills=orig['DIQ__DIQ070'].eq(1)
newdm=(t.diabetes.eq(0).to_numpy() & (orig.set_index('SEQN').loc[t.SEQN,'GHB__LBXGH'].ge(6.5).to_numpy()))
F2=F.copy(); F2[newdm,5]=1; F2[newdm,16]=a.to_numpy()[newdm]; pct2=calc(F2)
change=pd.DataFrame({'SEQN':t.SEQN,'cycle':t.cycle,'current_risk_pct':pct,'hba1c_sensitivity_risk_pct':pct2,'changes_diabetes':newdm})
change.loc[newdm].to_csv(DST/'diabetes_sensitivity.csv',index=False)
unknown=d.loc[eligible&~complete,pred].isna().sum().to_dict()
profile=[]
for c in d:
 s=d[c]; row=dict(variable=c,type=str(s.dtype),rows=len(s),missing=int(s.isna().sum()),unique=int(s.nunique()))
 if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s): row.update(min=s.min(),max=s.max(),median=s.median())
 profile.append(row)
pd.DataFrame(profile).to_csv(DST/'derived_codebook.csv',index=False)
for cyc in ['I','J']:
 m=t.cycle.eq(cyc); check('complete MEC weights positive '+cyc,t.loc[m,'wtmec_pooled'].gt(0).all())
summary=dict(rows=len(d),pool=int(eligible.sum()),complete=int((eligible&complete).sum()),incomplete=int((eligible&~complete).sum()),unknown_predictors=unknown,source_hashes=len(manifest),checks=len(checks),failed=sum(not x['passed'] for x in checks),risk_max_absolute_error_pct_points=float(delta.max()),example=example,prebounds_nonpregnant_no_cvd=int(prebounds.sum()),complete_without_bounds=int((prebounds&complete).sum()),dm_self_no_hba1c_high_all=int((dmno&Hb.ge(6.5)).sum()),dm_self_no_hba1c_high_complete=int(newdm.sum()),dm_self_no_diabetes_meds_complete=int((eligible&complete&dmno&(insulin|pills)).sum()),dm_hba1c_sensitivity_crosses_7_5=int(((pct<7.5)&(pct2>=7.5)).sum()),borderline_in_pool=int((eligible&orig['DIQ__DIQ010'].eq(3)).sum()),borderline_only_missing=int((eligible&orig['DIQ__DIQ010'].eq(3)&d[[c for c in pred if c!='diabetes']].notna().all(axis=1)).sum()),dbp_zero_participants_complete=int((eligible&complete&dy.eq(0).any(axis=1)).sum()),cvd_unknown_age_eligible=int((age.between(30,79)&~mcq.eq(1).any(axis=1)&~mcq.eq(2).all(axis=1)).sum()),risk_distribution=risk.prevent_10yr_total_cvd_pct.describe().to_dict())
pd.DataFrame(checks).to_csv(DST/'independent_checks.csv',index=False); (DST/'summary.json').write_text(json.dumps(summary,indent=2,default=lambda x:float(x)))
print(json.dumps(summary,indent=2,default=lambda x:float(x)))
assert summary['failed']==0
