# ========================================================================================
# 【实验 1：MIMIC 病历可行性检查】（2026-09-23，不调用任何大模型）
# 问题：真实出院小结里写的数值，和 MIMIC 结构化表对得上吗？缺血脂时，PREVENT 结论还能判定吗？
# 结论写在：cv-llm-risk-extraction/docs/feasibility_2026-09-23.md
# 运行顺序：01_sample.py → 01b_extract_subset.sh → 02_compare.py；03_determinability.py 独立运行
# 数据规则：MIMIC 派生数据（feasibility/out/）只能留在本机，不能上传、发给 API 或发布。
#
# 本文件：可判定性模拟（独立运行，不依赖 01/02）。
# 做什么：对全队列中能算出 PREVENT 的病人，假装不知道总胆固醇和 HDL，
#        让这两个值在 NHANES 第 1–99 百分位范围内变动（15×15 网格），求风险的最小值和最大值。
#        整个区间都在阈值 τ 同一侧 → 「可判定」；跨过 τ → 「无法判定」。
#        τ 取 5 / 7.5 / 10 / 15 / 20%。
# 这个方法后来也用在实验 2 的 B 部分（build_cases.py）。
# 输入：HTN-Concord 的 MIMIC 档案 + NHANES 档案（只用来定范围）
# 输出：打印各阈值下的可判定比例
# 原始位置：cv-llm-risk-extraction/feasibility/03_determinability.py
# ========================================================================================

"""If total cholesterol and HDL are unknown (as in ~94% of sampled discharge notes), how often
is the PREVENT >= tau decision still determined?

For every MIMIC cohort patient (ages 30-79) whose PREVENT is computable from structured data,
hide TC and HDL, sweep them over the NHANES 2017-18 1st-99th percentile box (TC > HDL), and
take the min/max 10-yr risk over the grid (the equation is not monotone everywhere, so the
extremes are searched, not read off corners). The decision is "determinable" at tau when the
whole interval lies on one side of tau. Also reports how often the hidden-value decision
agrees with the true one, which is a sanity check that the interval contains the truth.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "htn-concord-main/htn-concord"
sys.path.insert(0, str(REPO))
from pipelines.common.prevent import PreventInputs, prevent_10yr_cvd_risk  # noqa: E402

prof = pd.read_csv(REPO / "data/mimic/processed/mimic_profiles_primary_prior_plus_index.csv", low_memory=False)
nh = pd.read_csv(REPO / "data/nhanes/processed/nhanes_profiles_J.csv", low_memory=False)

# 血脂的「合理范围」= NHANES 人群的第 1–99 百分位
tc_lo, tc_hi = nh.total_chol.quantile([.01, .99])
hdl_lo, hdl_hi = nh.hdl.quantile([.01, .99])
TC = np.linspace(tc_lo, tc_hi, 15)
HDL = np.linspace(hdl_lo, hdl_hi, 15)
print(f"NHANES box: TC {tc_lo:.0f}-{tc_hi:.0f}, HDL {hdl_lo:.0f}-{hdl_hi:.0f} mg/dL")

p = prof[(prof.age >= 30) & (prof.age <= 79) & prof.prevent_10yr.notna()].copy()


def risk(r, tc, hdl):
    return prevent_10yr_cvd_risk(PreventInputs(
        age=r.age, sex=r.sex, total_chol_mgdl=tc, hdl_mgdl=hdl, sbp=r.sbp,
        on_bp_meds=bool(r.on_bp_meds), diabetes=bool(r.diabetes), current_smoker=bool(r.current_smoker),
        egfr=r.egfr, statin=bool(r.statin_use)))


# 对每个病人：真实风险 + 隐去血脂后在网格上的最小 / 最大风险
# （PREVENT 不是处处单调，所以要搜整个网格，不能只看四个角）
rows = []
for r in p.itertuples():
    true = risk(r, r.total_chol, r.hdl)
    vals = [risk(r, t, h) for t in TC for h in HDL if t > h]
    vals = [v for v in vals if v is not None]
    if true is None or not vals:
        continue
    rows.append((true, min(vals), max(vals)))
R = pd.DataFrame(rows, columns=["true", "lo", "hi"])
if R.true.max() <= 1:  # function returns a fraction; report in percent like the stored column
    R = R * 100
stored = p.prevent_10yr.values * (100 if p.prevent_10yr.max() <= 1 else 1)
print("patients:", len(R), "| mean |recomputed - stored| (pp):",
      round(float(abs(R.true.values - stored[:len(R)]).mean()), 3) if len(R) == len(p) else "n/a (row count differs)")
print("interval width (pp): median %.1f, IQR %.1f-%.1f" % (
    (R.hi - R.lo).median(), (R.hi - R.lo).quantile(.25), (R.hi - R.lo).quantile(.75)))
out = []
# 区间最小值 ≥ τ → 一定高；最大值 < τ → 一定低；否则无法判定
for tau in (5, 7.5, 10, 15, 20):
    above, below = (R.lo >= tau), (R.hi < tau)
    det = above | below
    out.append(dict(tau=tau, determinable=det.mean(), det_above=above.mean(), det_below=below.mean(),
                    true_above=(R.true >= tau).mean(),
                    contains_truth=((R.lo <= R.true) & (R.true <= R.hi)).mean()))
print(pd.DataFrame(out).round(3).to_string(index=False))
