# ========================================================================================
# 【共用模块】PCE 公式（2017 年旧版指南用的 10 年 ASCVD 风险公式）
# 所属实验：实验 2（先导实验 A 部分）。build_cases.py 用它给每个病人算「旧规则」的风险。
# 原始位置：cv-llm-rulebench/pilot/pce.py
# 做什么：按 Goff 2013 Table A 的系数计算风险（百分数）。
# 验证：check() 复现原文算例（55 岁、TC 213、HDL 50、SBP 120）的四个结果 2.1 / 3.0 / 5.3 / 6.1%。
#       原文先把每一项取整再求和，所以精确计算有微小差异（白人男性 5.38% vs 原文 5.3%），
#       容差设为线性和 0.01、风险 0.1 个百分点。
# 单独运行：python pce.py   → 打印 "PCE published example reproduced: True"
# 待办：正式实验前需要另一个人对照原文 Table A 再核一遍系数。
# ========================================================================================

"""Pooled Cohort Equations (PCE): 10-year hard ASCVD risk.

Reference: Goff DC Jr et al., 2013 ACC/AHA Guideline on the Assessment of Cardiovascular
Risk, Circulation 2014;129(suppl 2):S49-S73, Table A (equation parameters) and its worked
example (age 55, TC 213, HDL 50, untreated SBP 120, non-smoker, no diabetes).
check() reproduces the four published example risks: 2.1 / 3.0 / 5.3 / 6.1 %.

PILOT CODE. Before the formal study, the coefficients must be re-checked against the
printed Table A by a second person (transcription only, no clinical judgement needed).

Race: the equations exist only for "white" and "African American". Following common
practice, every non-Black participant uses the white equations. This is a documented
limitation of the PCE itself, not a choice we make.
"""
from math import exp, log

# term name -> coefficient; terms are built in _terms()
# 四组系数：(性别, 种族)。PCE 只有白人和非裔两套，其他种族一律用白人那套。
# 某项为 0.0 表示该组公式里没有这一项。s0 = 基线生存率，mean = 线性和的均值。
COEF = {
    ("female", "white"): dict(
        ln_age=-29.799, ln_age_sq=4.884, ln_tc=13.540, ln_age_ln_tc=-3.114, ln_hdl=-13.578,
        ln_age_ln_hdl=3.149, ln_tsbp=2.019, ln_age_ln_tsbp=0.0, ln_usbp=1.957, ln_age_ln_usbp=0.0,
        smoker=7.574, ln_age_smoker=-1.665, diabetes=0.661, s0=0.9665, mean=-29.18),
    ("female", "black"): dict(
        ln_age=17.114, ln_age_sq=0.0, ln_tc=0.940, ln_age_ln_tc=0.0, ln_hdl=-18.920,
        ln_age_ln_hdl=4.475, ln_tsbp=29.291, ln_age_ln_tsbp=-6.432, ln_usbp=27.820,
        ln_age_ln_usbp=-6.087, smoker=0.691, ln_age_smoker=0.0, diabetes=0.874,
        s0=0.9533, mean=86.61),
    ("male", "white"): dict(
        ln_age=12.344, ln_age_sq=0.0, ln_tc=11.853, ln_age_ln_tc=-2.664, ln_hdl=-7.990,
        ln_age_ln_hdl=1.769, ln_tsbp=1.797, ln_age_ln_tsbp=0.0, ln_usbp=1.764, ln_age_ln_usbp=0.0,
        smoker=7.837, ln_age_smoker=-1.795, diabetes=0.658, s0=0.9144, mean=61.18),
    ("male", "black"): dict(
        ln_age=2.469, ln_age_sq=0.0, ln_tc=0.302, ln_age_ln_tc=0.0, ln_hdl=-0.307,
        ln_age_ln_hdl=0.0, ln_tsbp=1.916, ln_age_ln_tsbp=0.0, ln_usbp=1.809, ln_age_ln_usbp=0.0,
        smoker=0.549, ln_age_smoker=0.0, diabetes=0.645, s0=0.8954, mean=19.54),
}


# 线性预测值：各项 = 系数 × ln(变量)，以及与 ln(年龄) 的交互项。
# 血压按「是否服降压药」只取其中一套系数（treated / untreated）。
def _lp(age, sex, race, tc, hdl, sbp, treated, smoker, diabetes):
    c = COEF[(sex, race)]
    la, lt, lh, ls = log(age), log(tc), log(hdl), log(sbp)
    s = (c["ln_age"] * la + c["ln_age_sq"] * la * la + c["ln_tc"] * lt + c["ln_age_ln_tc"] * la * lt
         + c["ln_hdl"] * lh + c["ln_age_ln_hdl"] * la * lh + c["smoker"] * smoker
         + c["ln_age_smoker"] * la * smoker + c["diabetes"] * diabetes)
    if treated:
        s += c["ln_tsbp"] * ls + c["ln_age_ln_tsbp"] * la * ls
    else:
        s += c["ln_usbp"] * ls + c["ln_age_ln_usbp"] * la * ls
    return s


# 10 年风险 = 1 - s0 ^ exp(线性和 - 均值)，乘 100 转成百分数。
def pce_10yr(age, sex, race, tc, hdl, sbp, treated, smoker, diabetes):
    """Risk in percent. race is 'black' or 'white' (use 'white' for all non-Black)."""
    c = COEF[(sex, race)]
    lp = _lp(age, sex, race, tc, hdl, sbp, int(treated), int(smoker), int(diabetes))
    return 100 * (1 - c["s0"] ** exp(lp - c["mean"]))


def check():
    """Published sums of terms and risks for the worked example.

    The paper rounds each term to 2 dp before summing, so exact arithmetic differs slightly:
    white men give a sum of 60.6995 (paper 60.69) and 5.38% (paper 5.3%). The tolerance is
    0.01 on the sum and 0.1 pp on the risk.
    """
    ex = dict(age=55, tc=213, hdl=50, sbp=120, treated=False, smoker=False, diabetes=False)
    want = {("female", "white"): (-29.67, 2.1), ("female", "black"): (86.16, 3.0),
            ("male", "white"): (60.69, 5.3), ("male", "black"): (18.97, 6.1)}
    for (sex, race), (w_sum, w_risk) in want.items():
        s = _lp(sex=sex, race=race, **ex)
        r = pce_10yr(sex=sex, race=race, **ex)
        assert abs(s - w_sum) <= 0.0151, (sex, race, s, w_sum)
        assert abs(r - w_risk) <= 0.1, (sex, race, r, w_risk)
    return True


if __name__ == "__main__":
    print("PCE published example reproduced:", check())
