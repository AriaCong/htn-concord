# ========================================================================================
# 【实验 2：先导实验 A + B】（2026-09-23 至 09-25）
# 问题 A：明确给出 2025 新规则（PREVENT ≥ 7.5%）时，模型照新规则办，还是退回 2017 旧规则（PCE ≥ 10%）？
# 问题 B：藏起胆固醇后，模型能否分辨「一定开药 / 一定不开 / 无法判断」？
# 数据：NHANES 2017–18 公开数据（可以发给 API）。
# 结果：cv-llm-rulebench/docs/pilot_2026-09-23.md；通俗版网页 artifacts/pilot_results.html
# 运行顺序：build_cases.py → run_pilot.py（每个模型一次）→ analyze.py；具体命令见 run_commands.sh
#
# 本文件：第 1 步，生成病例和标准答案（全部由程序计算，不需要人工）。
# A 部分：40–79 岁、1 期高血压、无心血管病 / 糖尿病 / 慢性肾病、未服降压药 → 244 人。
#        旧规则 old = PCE ≥ 10%，新规则 new = PREVENT ≥ 7.5%；两者不同的是「冲突病人」（只有 14 人）。
#        为了够测，在真人基础上扰动年龄、血脂、血压、吸烟，补到 50 个冲突病人（合成的 SEQN 从 9000001 起）。
#        另抽 30 个一致病人。
# B 部分：30–79 岁，隐去 TC 和 HDL，用和实验 1 相同的区间方法定答案，三类各抽 20 人。
# 输入：HTN-Concord 的 nhanes_profiles_J.csv；pilot/data/MCQ_J.xpt（从 CDC 下载，补心血管病史）
# 输出：out/cases.jsonl（140 个病例）、out/cohort_summary.json、out/pilot_seqns.txt（正式实验要排除这些人）
# 运行：htn-concord 的 .venv/bin/python build_cases.py
# 原始位置：cv-llm-rulebench/pilot/build_cases.py
# ========================================================================================

"""Build the pilot case sets from NHANES 2017-18 (public data).

A: rule-update conflict. Stage 1 BP, age 40-79, no clinical CVD / diabetes / CKD, not on BP
   meds, inputs inside PCE ranges. old = PCE >= 10%, new = PREVENT >= 7.5%.
B: determinability. Age 30-79, complete PREVENT inputs, TC and HDL hidden; the PREVENT
   interval over the NHANES 1st-99th percentile box decides DEFINITELY_ABOVE / BELOW /
   UNDETERMINED at tau = 7.5%.

The pilot SEQNs are written out so the formal study can exclude them.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT / "htn-concord-main/htn-concord"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from pipelines.common.prevent import PreventInputs, prevent_10yr_cvd_risk  # noqa: E402
from pce import pce_10yr, check  # noqa: E402

check()
rng = np.random.default_rng(20260923)
nh = pd.read_csv(REPO / "data/nhanes/processed/nhanes_profiles_J.csv")
# HTN-Concord 档案里 clinical_cvd 一列全空，所以从 NHANES 问卷 MCQ_J 补：
# 心衰、冠心病、心绞痛、心梗、卒中任一为「是」→ 有心血管病；任一项缺失 / 拒答 → 排除
mcq = pd.read_sas(HERE / "data/MCQ_J.xpt", format="xport")
# CHF, CHD, angina, heart attack, stroke; 1 = yes. Missing/refused/don't know -> excluded.
cvd_items = ["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]
mcq["cvd_known"] = mcq[cvd_items].isin([1, 2]).all(axis=1)
mcq["cvd"] = (mcq[cvd_items] == 1).any(axis=1)
nh = nh.merge(mcq[["SEQN", "cvd_known", "cvd"]], on="SEQN", how="left")
# PCE 只有白人和非裔两套系数：NHANES 种族码 4（非西语裔黑人）用非裔，其余用白人
nh["race"] = np.where(nh.race_eth == 4, "black", "white")  # PCE has only these two


# 计算 PREVENT；传入 tc / hdl 时用传入值（B 部分在网格上搜索时用）
def prevent(r, tc=None, hdl=None):
    v = prevent_10yr_cvd_risk(PreventInputs(
        age=r.age, sex=r.sex, total_chol_mgdl=r.total_chol if tc is None else tc,
        hdl_mgdl=r.hdl if hdl is None else hdl, sbp=r.sbp, on_bp_meds=bool(r.on_bp_meds),
        diabetes=bool(r.diabetes), current_smoker=bool(r.current_smoker), egfr=r.egfr,
        statin=bool(r.statin_use)))
    return v  # already in percent (prevent.py returns 100 / (1 + e^-lp))


def case_dict(r):
    return dict(seqn=int(r.SEQN), age=int(r.age), sex=r.sex, race=r.race,
                race_eth=int(r.race_eth), sbp=round(r.sbp), dbp=round(r.dbp),
                total_chol=round(r.total_chol), hdl=round(r.hdl), egfr=round(r.egfr),
                smoker=bool(r.current_smoker), diabetes=bool(r.diabetes),
                statin=bool(r.statin_use), on_bp_meds=bool(r.on_bp_meds))


# 以下为 A 部分：入组条件 → 两个公式各算一遍 → 标出冲突病人
# ---------- A ----------
need = ["age", "sex", "sbp", "dbp", "total_chol", "hdl", "egfr", "current_smoker", "diabetes",
        "statin_use", "on_bp_meds"]
a = nh.dropna(subset=need)
a = a[(a.age >= 40) & (a.age <= 79) & (a.bp_stage == "stage1") & a.cvd_known.fillna(False)
      & ~a.cvd.fillna(True) & ~a.diabetes.astype(bool) & (a.egfr >= 60)
      & ~a.ckd_albuminuria.fillna(False).astype(bool) & ~a.on_bp_meds.astype(bool)
      & a.total_chol.between(130, 320) & a.hdl.between(20, 100) & a.sbp.between(90, 200)]
a = a.copy()
a["pce"] = [pce_10yr(r.age, r.sex, r.race, r.total_chol, r.hdl, r.sbp, False,
                     bool(r.current_smoker), False) for r in a.itertuples()]
a["prevent"] = [prevent(r) for r in a.itertuples()]
a = a.dropna(subset=["prevent"])
a["old"] = a.pce >= 10
a["new"] = a.prevent >= 7.5
a["conflict"] = a.old != a.new
summary = dict(
    eligible=len(a), conflict=int(a.conflict.sum()), conflict_share=round(a.conflict.mean(), 3),
    old_yes_new_no=int((a.old & ~a.new).sum()), old_no_new_yes=int((~a.old & a.new).sum()),
    median_pce_over_prevent=round(float((a.pce / a.prevent).median()), 2))
print("A:", summary)

conf = a[a.conflict].sample(min(60, int(a.conflict.sum())), random_state=1)
agree = a[~a.conflict].sample(30, random_state=1)
A_cases = []
for grp, df in (("conflict", conf), ("agree", agree)):
    for r in df.itertuples():
        d = case_dict(r)
        d.update(set="A", group=grp, source="nhanes", pce=round(r.pce, 2),
                 prevent=round(r.prevent, 2), old=bool(r.old), new=bool(r.new))
        A_cases.append(d)

# Real conflicts are rare, so top the conflict set up to 50 with perturbed copies of eligible
# participants (age, lipids, SBP inside stage 1, smoking). They measure model behaviour only;
# population shares are reported from the real cohort above.
synth_seqn = 9_000_000
base = a[~a.SEQN.isin(conf.SEQN) & ~a.SEQN.isin(agree.SEQN)]
while sum(c["group"] == "conflict" for c in A_cases) < 50:
    r = base.iloc[rng.integers(len(base))].copy()
    r["age"] = float(rng.integers(40, 80))
    r["total_chol"] = float(rng.integers(150, 280))
    r["hdl"] = float(rng.integers(30, 80))
    r["sbp"] = float(rng.integers(130, 140))
    r["current_smoker"] = bool(rng.random() < 0.3)
    p_old = pce_10yr(r.age, r.sex, r.race, r.total_chol, r.hdl, r.sbp, False,
                     r.current_smoker, False)
    p_new = prevent(r)
    if p_new is None or (p_old >= 10) == (p_new >= 7.5):
        continue
    synth_seqn += 1
    r["SEQN"] = synth_seqn
    d = case_dict(r)
    d.update(set="A", group="conflict", source="synthetic", pce=round(p_old, 2),
             prevent=round(p_new, 2), old=bool(p_old >= 10), new=bool(p_new >= 7.5))
    A_cases.append(d)

# 以下为 B 部分：与 A 不重叠；隐去血脂后用区间运算定「一定开 / 一定不开 / 无法判断」
# ---------- B ----------
b = nh.dropna(subset=need)
b = b[(b.age >= 30) & (b.age <= 79)].copy()
b = b[~b.SEQN.isin(a.SEQN)]  # keep the two pilot sets disjoint
tc_lo, tc_hi = nh.total_chol.quantile([.01, .99])
hdl_lo, hdl_hi = nh.hdl.quantile([.01, .99])
TC, HDL = np.linspace(tc_lo, tc_hi, 15), np.linspace(hdl_lo, hdl_hi, 15)
b = b.sample(900, random_state=2)
rows = []
for r in b.itertuples():
    true = prevent(r)
    vals = [prevent(r, t, h) for t in TC for h in HDL if t > h]
    vals = [v for v in vals if v is not None]
    if true is None or not vals:
        continue
    lo, hi = min(vals), max(vals)
    label = "START" if lo >= 7.5 else "DO_NOT_START" if hi < 7.5 else "CANNOT_DETERMINE"
    d = case_dict(r)
    d.update(set="B", prevent=round(true, 2), lo=round(lo, 2), hi=round(hi, 2), label=label,
             dist=round(min(abs(lo - 7.5), abs(hi - 7.5)), 2))
    rows.append(d)
Bdf = pd.DataFrame(rows)
print("B label mix in sampled pool:", Bdf.label.value_counts().to_dict())
B_cases = (Bdf.groupby("label", group_keys=False)
           .apply(lambda g: g.sample(min(20, len(g)), random_state=3))
           .to_dict("records"))
print(f"B box: TC {tc_lo:.0f}-{tc_hi:.0f}, HDL {hdl_lo:.0f}-{hdl_hi:.0f}")

out = HERE / "out"
out.mkdir(exist_ok=True)
with open(out / "cases.jsonl", "w") as f:
    for c in A_cases + B_cases:
        f.write(json.dumps(c) + "\n")
json.dump(dict(A=summary, B_pool=Bdf.label.value_counts().to_dict(),
               B_box=dict(tc=[tc_lo, tc_hi], hdl=[hdl_lo, hdl_hi])),
          open(out / "cohort_summary.json", "w"), indent=2)
(out / "pilot_seqns.txt").write_text("\n".join(str(c["seqn"]) for c in A_cases + B_cases
                                             if c["seqn"] < 9_000_000))
print("wrote", len(A_cases), "A cases and", len(B_cases), "B cases")
